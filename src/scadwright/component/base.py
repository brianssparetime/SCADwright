"""Component base class.

A Component IS a Node (via inheritance) but is mutable, unlike the frozen
concrete AST dataclasses. Users subclass, set attributes in __init__, and
override build() to return an AST subtree.

Mutability is achieved by overriding __setattr__ on Component itself; this
bypasses the frozen-dataclass __setattr__ inherited from Node. Concrete AST
dataclasses (Cube, Translate, etc.) remain frozen because they declare their
own @dataclass(frozen=True) and don't override __setattr__.

Components can declare params declaratively via sc.Param descriptors.
__init_subclass__ collects Params into cls.__params__ and auto-generates a
kwargs-only __init__ if the subclass doesn't define one. Hand-written
__init__ (calling super().__init__(), then assigning self.x = ...) also
works.
"""

from __future__ import annotations

import inspect
import time
from typing import Any

from scadwright.ast.base import Node, SourceLocation
from scadwright.api.resolution import resolution as _resolution
from scadwright.component.params import Param, _MISSING
from scadwright.errors import BuildError, SCADwrightError, ValidationError
from scadwright._logging import get_logger

_log = get_logger("scadwright.component")


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


def _parse_params_string(cls, params: dict[str, Param]) -> None:
    """Auto-create ``Param(float)`` for each name listed in ``params = "..."``."""
    params_str = cls.__dict__.get("params", None)
    if not isinstance(params_str, str):
        return
    tokens = [n.strip() for n in params_str.replace(",", " ").split() if n.strip()]
    for tok in tokens:
        if tok not in params:
            p = Param(float)
            p.__set_name__(cls, tok)
            setattr(cls, tok, p)
            params[tok] = p


def _register_equations(cls, params: dict[str, Param]) -> None:
    """Parse ``equations = [...]`` and attach the resulting machinery to ``cls``.

    Classifies each entry as an equality, a per-Param constraint, a
    cross-constraint, a derivation, or a predicate. Auto-creates
    ``Param(float)`` for any new symbol introduced by an equality or
    constraint. Stores compiled derivations/predicates for instance-time
    evaluation.
    """
    all_eq_strs = list(cls.__dict__.get("equations", None) or [])
    if not all_eq_strs:
        if not hasattr(cls, "_has_equations"):
            cls._has_equations = False
            cls._has_cross_constraints = False
            cls._cross_constraints = []
            cls._has_derivations = False
            cls._derivations = []
            cls._derivation_names = frozenset()
            cls._has_predicates = False
            cls._predicates = []
        return

    from scadwright.component.equations import (
        classify_equation,
        extract_equality_symbols,
        parse_constraints,
        parse_cross_constraints,
        parse_derivations,
        parse_equations,
        parse_predicates,
    )

    equalities: list[str] = []
    constraints: list[str] = []
    cross_strs: list[str] = []
    derivation_asts: list[tuple] = []
    predicate_asts: list[tuple] = []
    for i, s in enumerate(all_eq_strs):
        try:
            kind, stmt = classify_equation(s)
        except ValidationError as exc:
            raise ValidationError(
                f"{cls.__name__}.equations[{i}]: {exc}"
            ) from exc
        if kind == "equality":
            equalities.append(s)
        elif kind == "cross_constraint":
            cross_strs.append(s)
        elif kind == "derivation":
            derivation_asts.append((stmt, s))
        elif kind == "predicate":
            predicate_asts.append((stmt, s))
        else:
            constraints.append(s)

    def _declare_float_param(name: str) -> None:
        p = Param(float)
        p.__set_name__(cls, name)
        setattr(cls, name, p)
        params[name] = p

    # Auto-create Param(float) for symbols introduced by equalities.
    for eq_s in equalities:
        for sym_name in extract_equality_symbols(eq_s, params.keys()):
            if sym_name not in params:
                _declare_float_param(sym_name)

    # Parse constraint inequalities and attach validators to Params.
    if constraints:
        constraint_map = parse_constraints(constraints)
        for name, validators in constraint_map.items():
            if name not in params:
                _declare_float_param(name)
            param = params[name]
            param.validators = tuple(param.validators) + tuple(validators)

    # Parse cross-constraints (var-vs-var inequalities) — evaluated at
    # instance-init time once all Params are set.
    cross_compiled: list = []
    if cross_strs:
        cross_compiled, cross_syms = parse_cross_constraints(cross_strs, params.keys())
        for sym_name in cross_syms:
            if sym_name not in params:
                _declare_float_param(sym_name)

    # Parse derivations. LHS can't collide with a Param (including Params
    # auto-declared from equality free symbols) or with an earlier derivation.
    compiled_derivations: list = []
    derivation_names: set[str] = set()
    if derivation_asts:
        compiled_derivations = parse_derivations(
            derivation_asts, extra_allowed_names=params.keys()
        )
        for name, _, raw in compiled_derivations:
            if name in params:
                raise ValidationError(
                    f"{cls.__name__}: derivation `{raw}` LHS {name!r} "
                    f"collides with Param of same name"
                )
            if name in derivation_names:
                raise ValidationError(
                    f"{cls.__name__}: derivation `{raw}` LHS {name!r} "
                    f"declared twice"
                )
            derivation_names.add(name)

    compiled_predicates: list = (
        parse_predicates(
            predicate_asts,
            extra_allowed_names=set(params.keys()) | derivation_names,
        )
        if predicate_asts else []
    )

    cls._parsed_equations = (
        parse_equations(equalities, params.keys()) if equalities else None
    )
    cls._has_equations = bool(equalities)
    cls._cross_constraints = cross_compiled
    cls._has_cross_constraints = bool(cross_compiled)
    cls._derivations = compiled_derivations
    cls._has_derivations = bool(compiled_derivations)
    cls._derivation_names = frozenset(derivation_names)
    cls._predicates = compiled_predicates
    cls._has_predicates = bool(compiled_predicates)


def _collect_anchor_defs(cls) -> dict:
    """Gather every ``AnchorDef`` declared at class scope across the MRO."""
    from scadwright.component.anchors import AnchorDef

    anchor_defs: dict = {}
    for base in reversed(cls.__mro__):
        for name, value in vars(base).items():
            if isinstance(value, AnchorDef):
                anchor_defs[name] = value
    return anchor_defs


class Component(Node):
    """Base for user-defined parametric parts.

    Subclass and override `build()` to return an AST subtree.

    Two ways to declare attributes:

    1. **Plain `__init__`** — write your own `__init__`, call
       `super().__init__()`, set `self.x = ...`.

    2. **`sc.Param` descriptors** — declare params at class scope. An
       auto-generated kwargs-only `__init__` validates inputs, solves
       `equations`, evaluates derivations, and validates predicates.

    Class attributes `fn`/`fa`/`fs` act as default resolution for primitives
    built inside `build()`. Instance attributes of the same names override.
    """

    # Class-level resolution defaults. Subclasses override as plain class vars.
    fn: float | None = None
    fa: float | None = None
    fs: float | None = None

    # Class-level centering default. Accepts True, "xy", "xz", etc.
    center = None

    # Populated by __init_subclass__ for subclasses with Param descriptors.
    __params__: dict[str, Param] = {}

    def __setattr__(self, name, value):
        # Frozen Components refuse writes to any name whose value is
        # part of the construction contract: Params (solver inputs or user
        # inputs) and derivation outputs (derived from those inputs). Letting
        # either be reassigned after __init__ would desync the instance from
        # the equations that produced it.
        if getattr(self, "_frozen", False):
            cls = type(self)
            if name in cls.__params__ or name in getattr(cls, "_derivation_names", ()):
                raise ValidationError(
                    f"{cls.__name__} is frozen after construction; cannot "
                    f"reassign {name!r}. Create a new instance instead."
                )
        # Bypass the frozen __setattr__ inherited from Node, making Component
        # and its subclasses behave like normal Python classes.
        object.__setattr__(self, name, value)

    def __init__(self, *, _source_location: SourceLocation | None = None):
        # _source_location is an internal kwarg used by auto-generated __init__
        # methods that have already captured the caller. Plain user __init__
        # methods call super().__init__() with no args; from_instantiation_site
        # walks past scadwright frames AND the user's __init__ chain.
        if _source_location is None:
            _source_location = SourceLocation.from_instantiation_site()
        self.source_location = _source_location
        self._built_tree = None
        # Bbox cache, populated by sc.bbox() on first call. Cleared by _invalidate.
        self._bbox_cache = None
        # tree_hash cache, populated by sc.tree_hash() on first call.
        self._tree_hash_cache = None
        # Custom anchors: populated from class-scope anchor() defs during
        # __init__. Also mutable at runtime via self.anchor(...) as a final
        # escape hatch for Components that can't express an anchor declaratively.
        self._anchors: dict = {}
        # Freeze flag: set to True after __init__ for equation-using Components.
        self._frozen = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        params = _collect_params_from_mro(cls)
        _apply_class_attr_overrides(cls, params)
        _parse_params_string(cls, params)
        _register_equations(cls, params)
        cls.__params__ = params
        cls.__anchor_defs__ = _collect_anchor_defs(cls)
        # Generate __init__ only if the subclass didn't define one, and
        # it has either Params or anchor defs that need wiring.
        if (params or cls.__anchor_defs__) and "__init__" not in cls.__dict__:
            cls.__init__ = _make_param_init(cls, params)

    def build(self) -> Node:
        raise NotImplementedError(
            f"{type(self).__name__} must override build()"
        )

    def center_origin(self):
        """Return the point (x, y, z) that ``center=`` shifts to the origin.

        Default: bbox center of the built tree. Override in subclasses to
        use a different reference point (e.g. a mounting face or a hole
        center rather than the geometric center of the bounding box).
        """
        from scadwright.bbox import bbox as _bbox

        bb = _bbox(self._built_tree)
        return bb.center

    def anchor(self, name: str, position: tuple, normal: tuple) -> None:
        """Declare a named anchor on this Component at runtime.

        Prefer the class-scope ``anchor()`` descriptor — both ``at=`` and
        ``normal=`` accept string expressions, which cover conditional
        positions and conditional normals. This method is the imperative
        escape hatch for Components that genuinely can't express an anchor
        declaratively.
        """
        from scadwright.anchor import Anchor

        self._anchors[name] = Anchor(
            position=(float(position[0]), float(position[1]), float(position[2])),
            normal=(float(normal[0]), float(normal[1]), float(normal[2])),
        )

    def get_anchors(self) -> dict:
        """Return this Component's anchors: bbox-derived defaults merged with custom.

        Class-scope ``anchor()`` declarations and any runtime
        ``self.anchor(...)`` calls override the bbox-derived defaults when
        they share a name.
        """
        from scadwright.anchor import anchors_from_bbox
        from scadwright.bbox import bbox as _bbox

        bb = _bbox(self)
        result = anchors_from_bbox(bb)
        result.update(self._anchors)
        return result

    def _apply_centering(self, center_spec):
        """Wrap ``_built_tree`` in a Translate that centers the requested axes."""
        from scadwright.api._vectors import _normalize_center
        from scadwright.ast.transforms import Translate

        cx, cy, cz = self.center_origin()
        axes = _normalize_center(center_spec)
        dx = -cx if axes[0] else 0
        dy = -cy if axes[1] else 0
        dz = -cz if axes[2] else 0
        if dx or dy or dz:
            return Translate(
                v=(dx, dy, dz),
                child=self._built_tree,
                source_location=self.source_location,
            )
        return self._built_tree

    def _invoke_build(self) -> Node:
        """Call `self.build()` and coerce the result.

        `build()` may either return a Node or be a generator yielding Nodes.
        Generator form is the preferred style for composite Components: the
        framework auto-unions the yielded parts so callers don't have to
        write `parts = []; ...; return union(*parts)` boilerplate.
        """
        from scadwright.boolops import union as _union  # local: avoid import cycle

        result = self.build()
        if isinstance(result, Node):
            return result
        if inspect.isgenerator(result):
            parts = list(result)
            if not parts:
                raise BuildError(
                    f"{type(self).__name__}.build() generator yielded no parts",
                    source_location=self.source_location,
                )
            for i, p in enumerate(parts):
                if not isinstance(p, Node):
                    raise BuildError(
                        f"{type(self).__name__}.build() yielded non-Node at "
                        f"index {i}: {type(p).__name__}",
                        source_location=self.source_location,
                    )
            return parts[0] if len(parts) == 1 else _union(*parts)
        raise BuildError(
            f"{type(self).__name__}.build() must return a Node or yield Nodes; "
            f"got {type(result).__name__}",
            source_location=self.source_location,
        )

    def _get_built_tree(self) -> Node:
        """Return the materialized subtree, building and caching on first call.

        If any of fn/fa/fs are set (instance attrs win over class attrs),
        build() runs inside an implicit resolution() context so primitives
        created inside inherit those values. Same treatment for a
        ``clearances`` class attribute — inner scope wins over any outer
        ``with clearances(...)`` block, matching ``fn`` semantics.
        """
        from contextlib import ExitStack

        from scadwright.api.clearances import Clearances, clearances as _clearances_ctx

        if self._built_tree is None:
            cls_name = type(self).__name__
            fn = getattr(self, "fn", None)
            fa = getattr(self, "fa", None)
            fs = getattr(self, "fs", None)
            cls_clearances = getattr(type(self), "clearances", None)
            t0 = time.perf_counter()
            try:
                with ExitStack() as stack:
                    if fn is not None or fa is not None or fs is not None:
                        stack.enter_context(_resolution(fn=fn, fa=fa, fs=fs))
                    if isinstance(cls_clearances, Clearances):
                        stack.enter_context(_clearances_ctx(cls_clearances))
                    self._built_tree = self._invoke_build()
            except SCADwrightError as exc:
                # Add a note showing which parent Component was being built,
                # so nested failures produce a readable chain.
                loc = self.source_location
                exc.add_note(
                    f"while building {cls_name}"
                    + (f" (at {loc})" if loc else "")
                )
                raise
            except Exception as exc:
                raise BuildError(
                    f"while building {cls_name}: {exc}",
                    source_location=self.source_location,
                ) from exc
            # Apply centering after build, before caching.
            center = getattr(self, "center", None)
            if center is not None:
                self._built_tree = self._apply_centering(center)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            loc = self.source_location
            _log.info(
                "built %s in %.2fms%s",
                cls_name,
                elapsed_ms,
                f" (src: {loc})" if loc else "",
            )
        return self._built_tree

    def _invalidate(self) -> None:
        """Force rebuild + bbox + tree_hash recompute on next access."""
        self._built_tree = None
        self._bbox_cache = None
        self._tree_hash_cache = None


def materialize(component: Component) -> Node:
    """Return the (cached) built subtree of a Component."""
    return component._get_built_tree()


def _resolve_anchor_defs(instance):
    """Resolve class-scope AnchorDef declarations into real anchors."""
    anchor_defs = getattr(type(instance), "__anchor_defs__", None)
    if not anchor_defs:
        return
    from scadwright.anchor import Anchor as _Anchor

    for name, adef in anchor_defs.items():
        pos = adef.resolve(instance)
        normal = adef.resolve_normal(instance)
        instance._anchors[name] = _Anchor(position=pos, normal=normal)


# Implicit kwargs accepted by every Component's auto-init in addition to
# the declared Params. These flow into the build's resolution context or
# are used for origin control. Add a new name here when introducing a new
# framework-level kwarg.
_IMPLICIT_KWARGS = frozenset({"fn", "fa", "fs", "center"})


def _resolve_clearance_kwarg(cls, kwargs: dict) -> None:
    """Inject ``clearance`` from the clearance-resolution chain when a
    joint-like Component opts in via ``_clearance_category`` and the
    user didn't pass it explicitly.

    Runs BEFORE the equation solver so the resolved value flows through
    as a "given" to sympy, same as any user-passed value. No-ops for
    Components without a ``_clearance_category`` class attribute.
    """
    if "clearance" in kwargs:
        return
    category = getattr(cls, "_clearance_category", None)
    if category is None:
        return
    from scadwright.api.clearances import resolve_clearance
    kwargs["clearance"] = resolve_clearance(category)


def _solve_equation_vars(cls, params: dict[str, Param], kwargs: dict) -> None:
    """Invoke the equation solver for a Component's equation-vars, merging
    any solved values into ``kwargs`` in place. Leaves non-equation kwargs
    untouched. Wraps the solver's ``ValidationError`` with the class name
    for nicer error context.
    """
    from scadwright.component.equations import solve_instance

    parsed = cls._parsed_equations
    given = {k: float(v) for k, v in kwargs.items() if k in parsed.equation_vars}
    defaults = {
        name: params[name].default
        for name in parsed.equation_vars
        if name not in kwargs
        and params[name].has_default()
        and params[name].default is not None
    }
    try:
        solved = solve_instance(parsed, given, defaults, params)
    except ValidationError as exc:
        raise ValidationError(f"{cls.__name__}: {exc}") from exc
    # Solved output contains both newly-solved values and any defaults the
    # solver applied on the user's behalf; both become assignments.
    for name, value in solved.items():
        kwargs.setdefault(name, value)


def _make_param_init(cls, params: dict[str, Param]):
    """Build an auto-generated kwargs-only __init__ for a Component subclass.

    Order: required params (no default) first, then params with defaults. All
    are kwargs-only so positional ambiguity from declaration order is moot.
    """

    required = [n for n, p in params.items() if not p.has_default()]
    optional = [n for n, p in params.items() if p.has_default()]

    def __init__(self, **kwargs):
        # Capture caller's frame BEFORE running setters (which may push frames).
        loc = SourceLocation.from_caller()

        unknown = set(kwargs) - set(params) - _IMPLICIT_KWARGS
        if unknown:
            raise ValidationError(
                f"{type(self).__name__}: unknown parameter(s): {sorted(unknown)}"
            )

        # Clearance resolver runs before equation-solving so the resolved
        # value flows through as a "given" to sympy, same as any explicit
        # kwarg. Only joint Components with _clearance_category opt in.
        _resolve_clearance_kwarg(cls, kwargs)

        # Solve equation-vars BEFORE the missing-required check, so solved
        # values count as "provided."
        if getattr(cls, "_has_equations", False):
            _solve_equation_vars(cls, params, kwargs)

        missing = [n for n in required if n not in kwargs]
        if missing:
            raise ValidationError(
                f"{type(self).__name__}: missing required parameter(s): {missing}"
            )

        # Initialize the Component base (sets source_location and _built_tree).
        Component.__init__(self, _source_location=loc)

        # Apply each param via Param.__set__ (which coerces and validates).
        for name in required + optional:
            value = kwargs[name] if name in kwargs else params[name].default
            setattr(self, name, value)

        # Store implicit kwargs as instance attrs so _get_built_tree picks them up.
        for impl in _IMPLICIT_KWARGS:
            if impl in kwargs:
                object.__setattr__(self, impl, kwargs[impl])

        # Cross-constraints (var-vs-var inequalities) run now that every
        # Param is set, before derivations and predicates, so violations
        # surface at the input-validation layer rather than mid-build.
        if getattr(cls, "_has_cross_constraints", False):
            from scadwright.component.equations import evaluate_cross_constraints

            values = {name: getattr(self, name, None) for name in params}
            evaluate_cross_constraints(
                cls._cross_constraints, values, type(self).__name__
            )

        _resolve_anchor_defs(self)

        # Derivations publish computed values onto the instance. They see all
        # Params (incl. solver-resolved), all earlier derivations, and namedtuple
        # fields via attribute access. Runs before predicates so predicates can
        # reference derived names.
        if getattr(cls, "_has_derivations", False):
            from scadwright.component.equations import evaluate_derivations

            evaluate_derivations(cls._derivations, self, type(self).__name__)

        # Predicates validate arbitrary Python truths about the instance.
        # Runs after derivations so predicates can reference derived names.
        if getattr(cls, "_has_predicates", False):
            from scadwright.component.equations import evaluate_predicates

            evaluate_predicates(cls._predicates, self, type(self).__name__)

        # Framework escape hatch: a user-defined `setup()` method, if
        # present, runs last. Not a user-facing pattern — every normal use
        # case belongs in derivations or predicates — but retained as an
        # internal hook for Components that genuinely need imperative work.
        post = getattr(self, "setup", None)
        if callable(post):
            post()

        # Freeze instances whose state is tied to the user-input contract
        # (equations, derivations, or predicates). Prevents post-construction
        # Param or derivation writes from desynchronizing the instance.
        if (
            getattr(cls, "_has_equations", False)
            or getattr(cls, "_has_derivations", False)
            or getattr(cls, "_has_predicates", False)
        ):
            self._frozen = True

    __init__.__qualname__ = f"{cls.__qualname__}.__init__"
    __init__.__doc__ = f"Auto-generated kwargs-only __init__ for {cls.__name__}."
    return __init__
