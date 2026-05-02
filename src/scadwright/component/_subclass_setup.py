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
    auto-declare any Params introduced by names appearing in equations
    or constraints.

    Per the spec (collapse_eq.md, "Feature spec v2"), ``=`` and ``==``
    are identical: every bare-Name target of any equation is just a
    Param the user may supply (consistency-checked) or omit (filled in
    by the resolver). There is no "derivation target" category that
    forbids user supply. Every free name in any equation or constraint
    becomes a ``Param(float)`` if it isn't already declared.
    """
    raw_eqs = cls.__dict__.get("equations", None)
    if isinstance(raw_eqs, str):
        from scadwright.component.equations import _split_equations_text
        all_eq_strs = _split_equations_text(raw_eqs)
    elif raw_eqs:
        from scadwright.component.equations import _split_equations_text
        # List entries may themselves be multi-line strings — expand each
        # through the splitter. Single-line entries return ``[entry]`` so
        # pure list-form input is byte-identical to before.
        all_eq_strs = []
        for entry in raw_eqs:
            if isinstance(entry, str) and "\n" in entry:
                all_eq_strs.extend(_split_equations_text(entry))
            else:
                all_eq_strs.append(entry)
    else:
        all_eq_strs = []
    if not all_eq_strs:
        if not hasattr(cls, "_unified_equations"):
            cls._unified_equations = []
            cls._unified_constraints = []
            cls._override_names = frozenset()
        return

    from scadwright.component.equations import (
        _CURATED_BUILTINS, _CURATED_MATH,
    )
    from scadwright.component.resolver import (
        extract_per_param_validator,
        parse_equations_unified,
    )

    unified_eqs, unified_constraints, optional_names, typed_names = (
        parse_equations_unified(all_eq_strs, class_name=cls.__name__)
    )

    curated = set(_CURATED_BUILTINS) | set(_CURATED_MATH)

    reserved = optional_names & curated
    if reserved:
        name = sorted(reserved)[0]
        raise ValidationError(
            f"{cls.__name__}: optional marker `?{name}` collides with a "
            f"reserved name from the curated namespace. Pick a different "
            f"Param name."
        )

    # Reject equation targets (bare-Name on either side of any equation)
    # that collide with the curated namespace. An equation `pi = 3.14`
    # would shadow `math.pi` inside the curated eval namespace and is
    # almost certainly a mistake.
    eq_target_names: set[str] = {
        name
        for eq in unified_eqs
        for name, _ in equation_bare_targets(eq)
    }
    reserved_targets = eq_target_names & curated
    if reserved_targets:
        name = sorted(reserved_targets)[0]
        raise ValidationError(
            f"{cls.__name__}: equation target `{name}` collides with a "
            f"reserved name from the curated namespace."
        )

    def _declare_param(
        name: str, *, type_: type | None, default=_MISSING
    ) -> None:
        if default is _MISSING:
            p = Param(type_)
        else:
            p = Param(type_, default=default)
        p._auto_declared = True
        p.__set_name__(cls, name)
        setattr(cls, name, p)
        params[name] = p

    # Identify bare-Name equation targets whose every other side is
    # demonstrably numeric. Those get ``Param(float)``, preserving the
    # int->float coercion callers rely on (e.g. ``Tube(thk=1)`` accepts
    # an int). Anything else — comparisons (yield bool), comprehensions,
    # attribute access into namedtuples, ``tuple()``/``list()`` calls —
    # gets ``Param(None)`` so the eventual non-float value isn't forced
    # through ``float()`` coercion.
    target_is_numeric_only: dict[str, bool] = {}
    for eq in unified_eqs:
        for name, other_side in equation_bare_targets(eq):
            other_numeric = _yields_scalar_numeric(other_side)
            prev = target_is_numeric_only.get(name, True)
            target_is_numeric_only[name] = prev and other_numeric

    # Reject collisions between an inline `:type` tag and an explicit
    # `Param(...)` declaration on the class. One declaration site per
    # name; the inline form is for auto-declared Params only.
    from scadwright.component.equations import _INLINE_TYPE_ALLOWLIST
    for name in typed_names:
        existing = cls.__dict__.get(name)
        if isinstance(existing, Param):
            raise ValidationError(
                f"{cls.__name__}: name `{name}` has both an inline "
                f"`:{typed_names[name]}` type tag in `equations` and an "
                f"explicit `Param(...)` declaration. Use one or the "
                f"other."
            )

    # Auto-declare optional Params first so the auto-declare loop below
    # finds the existing default=None Param rather than creating a
    # required one. The `?` sigil makes the Param optional; an inline
    # type tag (if any) sets the type, otherwise float.
    for name in optional_names:
        if name in params:
            continue
        type_ = _INLINE_TYPE_ALLOWLIST.get(typed_names.get(name, ""), float)
        _declare_param(name, type_=type_, default=None)

    # Auto-declare every free name in any equation or any constraint
    # that isn't already a Param and isn't in the curated namespace.
    # This includes bare-Name targets of `=` lines (per spec, those are
    # just Params the user can supply) and bare-Name sides of `==` lines.
    free_names: set[str] = set()
    for eq in unified_eqs:
        free_names |= eq.referenced_names
    for c in unified_constraints:
        free_names |= c.referenced_names
    for name in free_names:
        if name in params:
            continue
        if name in curated:
            continue
        # Inline `:type` tag wins over the numeric/non-numeric inference.
        if name in typed_names:
            _declare_param(name, type_=_INLINE_TYPE_ALLOWLIST[typed_names[name]])
            continue
        # Default to float for constraint-only names and numeric targets.
        # Targets of non-numeric equations (tuples, comparisons, etc.)
        # auto-declare with no type coercion.
        if target_is_numeric_only.get(name, True):
            _declare_param(name, type_=float)
        else:
            _declare_param(name, type_=None)

    # Per-Param validators from numeric-RHS constraints. The same
    # constraint is also evaluated by the resolver; the per-Param
    # validator additionally fires on any direct Param.__set__ call.
    for c in unified_constraints:
        result = extract_per_param_validator(c)
        if result is None:
            continue
        name, validator = result
        if name not in params:
            continue
        params[name].validators = tuple(params[name].validators) + (validator,)

    # Optional names that are also bare-Name targets of an equation:
    # the equation provides the value when the user doesn't supply
    # one. The resolver skips applying the None default at startup
    # for these so the equation can fill them in via the existing
    # forward-eval path.
    eq_target_names_for_overrides: set[str] = {
        name
        for eq in unified_eqs
        for name, _ in equation_bare_targets(eq)
    }
    cls._override_names = frozenset(
        optional_names & eq_target_names_for_overrides
    )

    cls._unified_equations = unified_eqs
    cls._unified_constraints = unified_constraints


def _collect_anchor_defs(cls) -> dict:
    """Gather every ``AnchorDef`` declared at class scope across the MRO."""
    from scadwright.component.anchors import AnchorDef

    anchor_defs: dict = {}
    for base in reversed(cls.__mro__):
        for name, value in vars(base).items():
            if isinstance(value, AnchorDef):
                anchor_defs[name] = value
    return anchor_defs
