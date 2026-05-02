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
    """The three name-set views the glossary needs from the resolver.

    ``knowns`` is the resolver's full ``{name: value}`` snapshot.
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
    # vertically. The supplied/default entries don't carry an
    # expression, so for them the rhs is rendered as `value (tag)`
    # rather than `expr = value`.
    name_width = max(len(name) for name, _ in entries)
    lines: list[str] = []
    for name, rhs in entries:
        if rhs in ("(input)", "(default)"):
            value = _fmt_value(knowns[name])
            lines.append(f"  {name:<{name_width}} = {value}  {rhs}")
        else:
            lines.append(f"  {name:<{name_width}} = {rhs}")
    return lines
