"""Emit-time equation glossary for Components.

Produces the lines of the comment block that appears above each
Component's emitted SCAD subtree. The block lists every name the
Component's ``equations`` resolved, classified as caller-supplied,
Param-default-applied, or equation-derived, with both the resolved
value and (for derivations) the originating expression.

The comment is decorative; nothing in the SCAD geometry references
these names. The point is to give a reader a glossary mapping the
inlined literals in the geometry below back to the named, derived
quantities in the source ``equations`` block.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

from scadwright.component.resolver.types import equation_bare_targets
from scadwright.emit.format import _fmt_num


@dataclass(frozen=True)
class _GlossaryState:
    """The name-set views the glossary needs from the resolver.

    ``knowns`` is the resolver's full ``{name: value}`` post-adjust
    snapshot. ``pre_adjust_knowns`` is the snapshot taken right before
    adjustments were applied — used to display the starting value of
    an input or default that was subsequently adjusted (so the chain
    reads ``5 + 0.3 (overshoot) = 5.3`` rather than losing the 5).

    ``supplied`` and ``defaults`` are disjoint frozensets identifying
    which keys came from the caller and which fired a Param default;
    the third group (equation-derived) is implicit (knowns − supplied
    − defaults) and computed on demand by the formatter.

    Attached to the instance as a single attribute (``self._glossary``)
    so the auto-init writes one object instead of three sibling
    attrs and the formatter reads one object instead of three.
    """
    supplied: frozenset[str] = field(default_factory=frozenset)
    defaults: frozenset[str] = field(default_factory=frozenset)
    knowns: dict[str, Any] = field(default_factory=dict)
    pre_adjust_knowns: dict[str, Any] = field(default_factory=dict)


def _fmt_value(value: Any) -> str:
    """Format a resolved value for the glossary.

    Numerics flow through ``_fmt_num`` so the rendered form matches the
    literals appearing in the emitted SCAD geometry below — that's what
    makes the glossary useful as a name↔literal map. Tuples/lists
    render compactly. Other types fall back to ``repr``.
    """
    if isinstance(value, (int, float, bool)):
        return _fmt_num(value)
    if isinstance(value, (tuple, list)):
        if all(isinstance(x, (int, float, bool)) for x in value):
            return "[" + ", ".join(_fmt_num(x) for x in value) + "]"
    return repr(value)


def _build_adjustment_chain(
    name: str,
    applied_adjustments: list,
    parsed_adjustments: list,
) -> str:
    """Render the adjustment chain for ``name`` as inline glossary text.

    Returns a string like ``"+ 0.3 (printer overshoot) - 0.1 (cal)"``
    for additive chains or ``"* 1.05 (slop) / 2.0 (halve)"`` for
    multiplicative ones. The operators match what the user wrote so
    ``/= 2.0`` displays as ``/ 2.0``, not ``* 0.5``.

    ``applied_adjustments`` is the per-name list from the instance's
    ``_provenance`` dict; each entry is an :class:`Adjustment`
    namedtuple. ``parsed_adjustments`` is the class-level
    ``_unified_adjustments`` list. The two are paired by source line
    so the original op and RHS text can be recovered (``Adjustment``
    deliberately stores a normalized delta, which loses the original
    operator).

    Returns an empty string when ``applied_adjustments`` is empty.
    """
    if not applied_adjustments:
        return ""
    parsed_by_line = {
        pa.source_line_index + 1: pa
        for pa in parsed_adjustments
        if pa.name == name
    }
    parts: list[str] = []
    for adj in applied_adjustments:
        pa = parsed_by_line.get(adj.line)
        if pa is None:
            # Defensive — provenance and parsed lists should always pair
            # on (name, line). Fall back to delta-based rendering.
            sign = "+" if adj.delta >= 0 else "-"
            term = f"{sign} {abs(adj.delta)}"
        else:
            op_to_sym = {"+=": "+", "-=": "-", "*=": "*", "/=": "/"}
            sym = op_to_sym.get(pa.op, "+")
            try:
                rhs_text = ast.unparse(pa.rhs)
            except Exception:
                rhs_text = repr(adj.delta)
            term = f"{sym} {rhs_text}"
        if adj.comment:
            term += f" ({adj.comment})"
        parts.append(term)
    return " ".join(parts)


def _equation_target(eq) -> str | None:
    """Return the bare-Name target of an equation, or ``None``.

    Glossary lines correspond to lines of the form ``name = expr`` (the
    LHS is a bare Name that the equation derives). Lines like
    ``len(size) = 3`` or ``a + b = c`` aren't derivations of a single
    name and are skipped.
    """
    targets = equation_bare_targets(eq)
    return targets[0][0] if targets else None


def _equation_expression(eq, target: str) -> str:
    """Render the non-target side of the equation as Python source."""
    if isinstance(eq.lhs, ast.Name) and eq.lhs.id == target:
        return ast.unparse(eq.rhs)
    return ast.unparse(eq.lhs)


def format_glossary(component) -> list[str]:
    """Build the glossary comment lines for ``component``.

    Returns a list of plain strings (no ``//`` prefix, no leading
    indent — the caller adds those to fit the surrounding emit
    context). An empty list means the Component has no equations
    or no glossary-eligible names; the caller should fall back to
    whatever default header it would have emitted.
    """
    cls = type(component)
    equations = getattr(cls, "_unified_equations", []) or []
    parsed_adjustments = getattr(cls, "_unified_adjustments", []) or []
    state: _GlossaryState | None = getattr(component, "_glossary", None)
    if state is None:
        return []
    knowns = state.knowns
    if not equations and not knowns:
        return []
    if not knowns:
        return []

    supplied: frozenset[str] = state.supplied
    defaults: frozenset[str] = state.defaults
    overrides: frozenset[str] = getattr(cls, "_override_names", frozenset())
    pre_adjust = state.pre_adjust_knowns
    provenance = getattr(component, "_provenance", {}) or {}
    # Override-pattern fills (`?name = ?name or default`) act as defaults
    # from the caller's view — supplying the value or letting it default
    # produces the same resolved value. Classify them as (default) so
    # the glossary doesn't diverge between the two equivalent calls.
    override_defaults = {n for n in overrides if n not in supplied and n in knowns}

    # Map each equation-derived name to its source expression. Earlier
    # equations win — the first ``name = expr`` line registered for a
    # name is the one shown. Comma-broadcast siblings share a source
    # line and produce one entry per name.
    derivation_expr: dict[str, str] = {}
    for eq in equations:
        target = _equation_target(eq)
        if target is None or target.startswith("_"):
            continue
        if target not in knowns:
            continue
        if target in derivation_expr:
            continue
        derivation_expr[target] = _equation_expression(eq, target)

    # Build entries in a stable order: supplied first (as the user
    # wrote them in kwargs is not preserved, so use sorted), then
    # defaults, then derivations in equation declaration order.
    entries: list[tuple[str, str]] = []  # (name, rhs_text)

    seen: set[str] = set()

    for name in sorted(n for n in supplied if n in knowns and not n.startswith("_")):
        entries.append((name, "(input)"))
        seen.add(name)

    for name in sorted(n for n in defaults if n in knowns and not n.startswith("_")):
        if name in seen:
            continue
        entries.append((name, "(default)"))
        seen.add(name)

    for name in sorted(n for n in override_defaults if not n.startswith("_")):
        if name in seen:
            continue
        entries.append((name, "(default)"))
        seen.add(name)

    for eq in equations:
        target = _equation_target(eq)
        if target is None or target.startswith("_"):
            continue
        if target in seen:
            continue
        if target not in knowns:
            continue
        expr = derivation_expr.get(target, "")
        value = _fmt_value(knowns[target])
        entries.append((target, f"{expr} = {value}"))
        seen.add(target)

    if not entries:
        return []

    # Two-column layout: align the first ``=`` so values line up
    # vertically. Three rendering shapes:
    #   - derived: ``name = expr = value``
    #   - input/default: ``name = value  (tag)``
    #   - either of the above with adjustments: insert the chain and
    #     show the post-adjust value at the end:
    #       ``name = expr <chain> = value``
    #       ``name = pre_value <chain> = value  (tag)``
    name_width = max(len(name) for name, _ in entries)
    lines: list[str] = []
    for name, rhs in entries:
        chain = _build_adjustment_chain(
            name, provenance.get(name, []), parsed_adjustments,
        )
        if rhs in ("(input)", "(default)"):
            post_value = _fmt_value(knowns[name])
            if chain:
                pre_value = _fmt_value(
                    pre_adjust.get(name, knowns[name])
                )
                lines.append(
                    f"  {name:<{name_width}} = {pre_value} {chain} "
                    f"= {post_value}  {rhs}"
                )
            else:
                lines.append(
                    f"  {name:<{name_width}} = {post_value}  {rhs}"
                )
        else:
            # Derived. ``rhs`` is already ``expr = value`` for the
            # unadjusted case. With adjustments we re-render to
            # ``expr <chain> = post_value``.
            if chain:
                target = name
                expr = derivation_expr.get(target, "")
                post_value = _fmt_value(knowns[target])
                lines.append(
                    f"  {name:<{name_width}} = {expr} {chain} "
                    f"= {post_value}"
                )
            else:
                lines.append(f"  {name:<{name_width}} = {rhs}")
    return lines
