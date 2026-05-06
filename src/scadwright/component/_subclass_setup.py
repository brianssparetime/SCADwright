"""Subclass-time setup: collect Params, parse equations, auto-declare.

Every helper here runs once per Component subclass at class-definition
time, driven by ``Component.__init_subclass__``. Together they:

- Walk the MRO collecting ``Param`` descriptors (``_collect_params_from_mro``).
- Re-clone any inherited Param shadowed by a plain class attribute so
  validators still fire on the subclass (``_apply_class_attr_overrides``).
- Parse the ``equations`` block (string or list-of-strings), auto-
  declare every free name as a Param, attach per-Param validators
  extracted from numeric-RHS constraints, and stash the parsed
  representation on the class for the resolver to consume at instance
  time (``_register_equations``).
- Walk the MRO collecting ``AnchorDef`` declarations
  (``_collect_anchor_defs``).

The numeric-AST heuristic (``_yields_scalar_numeric``) lives here too —
it's used by the auto-declare loop in ``_register_equations`` to decide
whether a bare-Name target should auto-declare as ``Param(float)`` (so
``Tube(thk=1)`` with an int still works) or ``Param(None)`` (when the
equation's other side yields a tuple, namedtuple, etc.).
"""

from __future__ import annotations

import ast

from scadwright.component.equations import _NUMERIC_FUNCTION_NAMES
from scadwright.component.params import Param, _MISSING
from scadwright.component.resolver.types import equation_bare_targets
from scadwright.errors import ValidationError


def _yields_scalar_numeric(node: ast.AST) -> bool:
    """Heuristic: does ``node`` evaluate to a single int/float?

    Returns True for arithmetic, numeric-yielding calls (``sin``, ``min``),
    and a numeric ternary; False for comparisons (yield bool), boolean
    operations, attribute access (could be anything), comprehensions
    (yield containers), tuple/list/dict literals or constructors, and
    name references whose target type isn't known here.

    Conservative: a False result downgrades the auto-declared Param to
    typeless. False positives (returning True when the value is non-
    numeric) would corrupt user data; false negatives just lose the
    int->float convenience coercion.
    """
    if isinstance(node, ast.Constant):
        return type(node.value) in (int, float)
    if isinstance(node, ast.Name):
        # A bare Name might resolve to anything at runtime. Conservative
        # but practical: assume float if the name is a Param target — the
        # caller's auto-declare loop will sort it out by checking each
        # bare-Name target across all equations.
        return True
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return False
        return _yields_scalar_numeric(node.operand)
    if isinstance(node, ast.BinOp):
        return (
            _yields_scalar_numeric(node.left)
            and _yields_scalar_numeric(node.right)
        )
    if isinstance(node, ast.IfExp):
        return (
            _yields_scalar_numeric(node.body)
            and _yields_scalar_numeric(node.orelse)
        )
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id not in _NUMERIC_FUNCTION_NAMES:
            return False
        return all(_yields_scalar_numeric(a) for a in node.args)
    return False


# --- __init_subclass__ helpers ---


def _collect_params_from_mro(cls) -> dict[str, Param]:
    """Gather every ``Param`` descriptor from ``cls`` and its bases."""
    params: dict[str, Param] = {}
    for base in reversed(cls.__mro__):
        for name, value in vars(base).items():
            if isinstance(value, Param):
                params[name] = value
    return params


def _apply_class_attr_overrides(cls, params: dict[str, Param]) -> None:
    """Re-install any inherited Param that a concrete subclass has shadowed.

    When a subclass writes ``w = 20`` over an inherited ``w = Param(float)``,
    we clone the Param with the new default so instance assignment still
    runs the original validators — otherwise ``w = 20`` would just be a
    class attribute and no validation would fire on that subclass.
    """
    import copy as _copy

    for name in list(params.keys()):
        override = cls.__dict__.get(name, _MISSING)
        if override is _MISSING or isinstance(override, Param):
            continue
        cloned = _copy.copy(params[name])
        cloned.default = override
        params[name] = cloned
        setattr(cls, name, cloned)
        # copy.copy preserves _name; call __set_name__ defensively in case
        # a Param variant relies on it.
        if hasattr(cloned, "__set_name__"):
            cloned.__set_name__(cls, name)


def _register_equations(cls, params: dict[str, Param]) -> None:
    """Parse ``equations = [...]`` into the unified representation and
    auto-declare any Params introduced by names appearing in equations,
    constraints, or adjustments.

    Orchestrates a sequence of named passes — keep them in this order:

    1. Lift the raw ``equations`` attribute into a flat list of
       per-line strings paired with preceding-comment context.
    2. Parse via the resolver into a unified
       ``(equations, constraints, optionals, typed_names, adjustments)``
       shape.
    3. Reject reserved-name collisions (curated-namespace clashes).
    4. Reject inline-tag-vs-explicit-Param collisions.
    5. Infer which bare-Name equation targets are numeric-only
       (controls auto-declared Param type: ``float`` vs ``None``).
    6. Auto-declare every Param referenced in equations, constraints,
       or adjustments that isn't already declared.
    7. Attach per-Param validators extracted from numeric-RHS
       constraints.
    8. Verify every adjustment targets a name with a value source.
    9. Compute ``cls._override_names`` (optionals that are also
       bare-Name equation targets — the resolver pre-resolves these).
    10. Stash the parsed representation on the class for the auto-init
        to hand to the resolver.

    Per the spec, ``=`` and ``==`` are identical: every bare-Name
    target of any equation is just a Param the user may supply
    (consistency-checked) or omit (filled in by the resolver). Every
    free name in any equation, constraint, or adjustment becomes a
    ``Param(float)`` if it isn't already declared, except where the
    numeric-only heuristic (pass 5) downgrades it to ``Param(None)``.
    """
    eq_lines, preceding = _parse_or_get_equation_strings(cls)
    if not eq_lines:
        if not hasattr(cls, "_unified_equations"):
            cls._unified_equations = []
            cls._unified_constraints = []
            cls._unified_adjustments = []
            cls._override_names = frozenset()
            cls._optional_names = frozenset()
            cls._spec_value_names = frozenset(params)
        return

    from scadwright.component.equations import (
        _CURATED_BUILTINS, _CURATED_MATH,
    )
    from scadwright.component.resolver import parse_equations_unified

    (
        unified_eqs,
        unified_constraints,
        optional_names,
        typed_names,
        unified_adjustments,
    ) = parse_equations_unified(
        eq_lines,
        class_name=cls.__name__,
        preceding_comments=preceding,
    )
    curated = set(_CURATED_BUILTINS) | set(_CURATED_MATH)

    _check_reserved_collisions(
        cls.__name__, unified_eqs, optional_names, curated,
    )
    _check_inline_tag_param_collision(cls, typed_names)

    target_is_numeric_only = _infer_numeric_only_targets(unified_eqs)

    _auto_declare_params(
        cls, params,
        equations=unified_eqs,
        constraints=unified_constraints,
        adjustments=unified_adjustments,
        optional_names=optional_names,
        typed_names=typed_names,
        curated=curated,
        target_is_numeric_only=target_is_numeric_only,
    )

    _attach_per_param_validators(
        params, unified_constraints, unified_adjustments,
    )

    cls._override_names = _compute_override_names(unified_eqs, optional_names)
    cls._unified_equations = unified_eqs
    cls._unified_constraints = unified_constraints
    cls._unified_adjustments = unified_adjustments
    cls._optional_names = frozenset(optional_names)
    cls._spec_value_names = _compute_spec_value_names(
        params, unified_eqs, unified_adjustments,
    )


# --- _register_equations passes (in orchestration order) ---


def _parse_or_get_equation_strings(
    cls,
) -> tuple[list[str], list[str | None]]:
    """Lift ``cls.equations`` into a flat list of logical equation lines
    paired with their preceding-comment context.

    Returns ``(lines, preceding_comments)`` — two parallel lists.
    ``preceding_comments[i]`` is the immediately-preceding whole-line
    comment for ``lines[i]`` (with leading ``#`` stripped) or ``None``.

    Accepts a triple-quoted string (run through
    ``_split_equations_with_comments``), a list of strings (each entry
    may itself be multi-line and gets expanded through the same
    splitter), or nothing. Returns ``([], [])`` when no equations
    attribute is present or it's empty.
    """
    raw_eqs = cls.__dict__.get("equations", None)
    if isinstance(raw_eqs, str):
        from scadwright.component.equations import (
            _split_equations_with_comments,
        )
        pairs = _split_equations_with_comments(raw_eqs)
        return [p[0] for p in pairs], [p[1] for p in pairs]
    if raw_eqs:
        from scadwright.component.equations import (
            _split_equations_with_comments,
        )
        # List entries may themselves be multi-line strings — expand each
        # through the splitter. Single-line entries arrive without
        # preceding-comment context (the splitter only resolves preceding
        # comments inside one block of text, and a list entry is one
        # block).
        lines: list[str] = []
        preceding: list[str | None] = []
        for entry in raw_eqs:
            if isinstance(entry, str) and "\n" in entry:
                pairs = _split_equations_with_comments(entry)
                for line, pre in pairs:
                    lines.append(line)
                    preceding.append(pre)
            else:
                lines.append(entry)
                preceding.append(None)
        return lines, preceding
    return [], []


def _check_reserved_collisions(
    class_name: str,
    equations,
    optional_names: frozenset[str],
    curated: set[str],
) -> None:
    """Reject ``?`` sigils and equation-target names that collide with
    the curated namespace.

    Both checks would silently shadow a curated math/builtin name
    inside the eval namespace — almost always a user mistake. ``?pi``
    or ``pi = 3.14`` raises before the resolver ever runs.
    """
    reserved = optional_names & curated
    if reserved:
        name = sorted(reserved)[0]
        raise ValidationError(
            f"{class_name}: optional marker `?{name}` collides with a "
            f"reserved name from the curated namespace. Pick a different "
            f"Param name."
        )

    eq_target_names: set[str] = {
        name
        for eq in equations
        for name, _ in equation_bare_targets(eq)
    }
    reserved_targets = eq_target_names & curated
    if reserved_targets:
        name = sorted(reserved_targets)[0]
        raise ValidationError(
            f"{class_name}: equation target `{name}` collides with a "
            f"reserved name from the curated namespace."
        )


def _check_inline_tag_param_collision(
    cls, typed_names: dict[str, str],
) -> None:
    """Reject names declared both via inline ``:type`` tag and via
    explicit ``Param(...)``. One declaration site per name; the
    inline form is for auto-declared Params only.
    """
    for name in typed_names:
        existing = cls.__dict__.get(name)
        if isinstance(existing, Param):
            raise ValidationError(
                f"{cls.__name__}: name `{name}` has both an inline "
                f"`:{typed_names[name]}` type tag in `equations` and an "
                f"explicit `Param(...)` declaration. Use one or the "
                f"other."
            )


def _infer_numeric_only_targets(equations) -> dict[str, bool]:
    """For every bare-Name equation target, decide whether every other
    side it appears against is demonstrably numeric.

    Numeric-only targets get ``Param(float)``, preserving the
    int→float coercion callers rely on (``Tube(thk=1)`` accepts an
    int). Anything else — comparisons (yield bool), comprehensions,
    attribute access into namedtuples, ``tuple()``/``list()`` calls —
    gets ``Param(None)`` so the eventual non-float value isn't forced
    through ``float()`` coercion.
    """
    result: dict[str, bool] = {}
    for eq in equations:
        for name, other_side in equation_bare_targets(eq):
            other_numeric = _yields_scalar_numeric(other_side)
            prev = result.get(name, True)
            result[name] = prev and other_numeric
    return result


def _auto_declare_params(
    cls,
    params: dict[str, Param],
    *,
    equations,
    constraints,
    adjustments,
    optional_names: frozenset[str],
    typed_names: dict[str, str],
    curated: set[str],
    target_is_numeric_only: dict[str, bool],
) -> None:
    """Auto-declare every name referenced in equations, constraints, or
    adjustments that isn't already a Param and isn't in the curated
    namespace.

    Optionals are declared first so the free-name loop finds the
    existing ``default=None`` Param rather than creating a required
    one. Inline ``:type`` tags win over the numeric/non-numeric
    inference; un-tagged names get ``Param(float)`` when the
    numeric-only heuristic says yes, ``Param(None)`` otherwise.
    """
    from scadwright.component.equations import _INLINE_TYPE_ALLOWLIST

    def _declare(name: str, *, type_: type | None, default=_MISSING) -> None:
        if default is _MISSING:
            p = Param(type_)
        else:
            p = Param(type_, default=default)
        p._auto_declared = True
        p.__set_name__(cls, name)
        setattr(cls, name, p)
        params[name] = p

    # Optionals first — the `?` sigil makes the Param optional; an
    # inline type tag (if any) sets the type, otherwise float.
    for name in optional_names:
        if name in params:
            continue
        type_ = _INLINE_TYPE_ALLOWLIST.get(typed_names.get(name, ""), float)
        _declare(name, type_=type_, default=None)

    # Free names: every bare-Name target plus every constraint reference
    # plus every adjustment LHS and RHS reference. Adjusted names are
    # always numeric (the only meaningful types under +=/-=/*=//=), so
    # they default to float when the numeric heuristic doesn't have an
    # opinion.
    free_names: set[str] = set()
    for eq in equations:
        free_names |= eq.referenced_names
    for c in constraints:
        free_names |= c.referenced_names
    for adj in adjustments:
        free_names.add(adj.name)
        free_names |= adj.referenced_names

    for name in free_names:
        if name in params:
            continue
        if name in curated:
            continue
        if name in typed_names:
            _declare(name, type_=_INLINE_TYPE_ALLOWLIST[typed_names[name]])
            continue
        if target_is_numeric_only.get(name, True):
            _declare(name, type_=float)
        else:
            _declare(name, type_=None)


def _attach_per_param_validators(
    params: dict[str, Param], constraints, adjustments,
) -> None:
    """Attach per-Param validators extracted from ``name OP num`` constraints.

    The same constraint is also evaluated by the resolver at construction
    time; the per-Param validator additionally fires on any direct
    ``Param.__set__`` call (e.g., a bad value reassigned post-construction
    when freeze isn't engaged).

    Adjusted names are skipped: a constraint ``x > 5`` reads the
    pre-adjust value of ``x`` (the design-intent invariant), but
    ``Param.__set__`` on the auto-init's final write sees the post-
    adjust value. Attaching the validator would re-check the post-
    adjust value against a pre-adjust rule and surface a spurious
    failure. The resolver still evaluates the constraint at the
    correct moment (pre-adjust, before the apply step).
    """
    from scadwright.component.resolver import extract_per_param_validator

    adjusted_names = {adj.name for adj in adjustments}
    for c in constraints:
        result = extract_per_param_validator(c)
        if result is None:
            continue
        name, validator = result
        if name not in params:
            continue
        if name in adjusted_names:
            continue
        params[name].validators = tuple(params[name].validators) + (validator,)


def _compute_spec_value_names(
    params: dict[str, Param],
    equations,
    adjustments,
) -> frozenset[str]:
    """Closure of names the resolver writes into the post-resolve
    namespace.

    Equals every declared Param plus every bare-Name target of any
    equation plus every adjustment LHS — i.e., every name that could
    appear as a key in the instance/class ``_provenance`` dict, and
    therefore every name that ``adjustments_for`` should accept.
    Computed once at class-define time and cached on the class so
    introspection lookups don't recompute on each call.
    """
    names: set[str] = set(params)
    for eq in equations:
        for tgt, _ in equation_bare_targets(eq):
            names.add(tgt)
    for adj in adjustments:
        names.add(adj.name)
    return frozenset(names)


def _compute_override_names(
    equations, optional_names: frozenset[str],
) -> frozenset[str]:
    """Return the set of optional names that are also bare-Name targets
    of an equation.

    For these names the equation provides the value when the user
    doesn't supply one (the override-pattern path). The resolver skips
    applying the ``None`` default at startup for these names so the
    equation's RHS can fill them in via the pre-resolve path.
    """
    eq_target_names: set[str] = {
        name
        for eq in equations
        for name, _ in equation_bare_targets(eq)
    }
    return frozenset(optional_names & eq_target_names)


def _collect_anchor_defs(cls) -> dict:
    """Gather every ``AnchorDef`` declared at class scope across the MRO."""
    from scadwright.component.anchors import AnchorDef

    anchor_defs: dict = {}
    for base in reversed(cls.__mro__):
        for name, value in vars(base).items():
            if isinstance(value, AnchorDef):
                anchor_defs[name] = value
    return anchor_defs
