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


class Component(Node):
    """Base for user-defined parametric parts.

    Subclass and override `build()` to return an AST subtree.

    Two ways to declare attributes:

    1. **Plain `__init__`** — write your own `__init__`, call
       `super().__init__()`, set `self.x = ...`.

    2. **`sc.Param` descriptors** — declare params at class scope. Auto-generated
       kwargs-only `__init__` runs validators, then calls `setup()`
       if defined.

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
        # Equation-using Components freeze after construction: Param writes
        # would desync from the solved values, so we refuse them.
        if (
            getattr(self, "_frozen", False)
            and name in type(self).__params__
        ):
            raise ValidationError(
                f"{type(self).__name__} uses equations and is frozen after "
                f"construction; cannot reassign Param {name!r}. "
                f"Create a new instance instead."
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
        # Custom anchors: populated from class-scope anchor() defs and/or self.anchor() in setup().
        self._anchors: dict = {}
        # Freeze flag: set to True after __init__ for equation-using Components.
        self._frozen = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        import copy as _copy

        # Collect Params declared on this subclass (and inherited from bases).
        params: dict[str, Param] = {}
        for base in reversed(cls.__mro__):
            for name, value in vars(base).items():
                if isinstance(value, Param):
                    params[name] = value

        # Class-attr overrides: if a subclass shadows an inherited Param with
        # a plain value (e.g. `class MyBox(Box): outer_size = (60, 40, 40)`),
        # treat that value as the Param's default in this subclass. We clone
        # the inherited Param with the new default and reinstall the clone
        # as a descriptor so instance assignment still runs validators.
        for name in list(params.keys()):
            override = cls.__dict__.get(name, _MISSING)
            if override is _MISSING or isinstance(override, Param):
                continue
            cloned = _copy.copy(params[name])
            cloned.default = override
            params[name] = cloned
            setattr(cls, name, cloned)
            # copy.copy preserves _name, but call __set_name__ defensively
            # in case a Param variant relies on it.
            if hasattr(cloned, "__set_name__"):
                cloned.__set_name__(cls, name)

        # Process `params = "..."` class attribute: auto-create Param(float)
        # for each name listed.
        params_str = cls.__dict__.get("params", None)
        if isinstance(params_str, str):
            tokens = [n.strip() for n in params_str.replace(",", " ").split()
                      if n.strip()]
            for tok in tokens:
                if tok not in params:
                    p = Param(float)
                    p.__set_name__(cls, tok)
                    setattr(cls, tok, p)
                    params[tok] = p

        # Process `equations = [...]` class attribute: auto-create Params for
        # equation symbols and attach constraint validators.
        all_eq_strs = list(cls.__dict__.get("equations", None) or [])

        if all_eq_strs:
            from scadwright.component.equations import (
                classify_equation,
                extract_equality_symbols,
                parse_constraints,
                parse_equations,
            )

            equalities = []
            constraints = []
            for s in all_eq_strs:
                kind = classify_equation(s)
                if kind == "equality":
                    equalities.append(s)
                else:
                    constraints.append(s)

            # Auto-create Param(float) for equation symbols not already declared.
            for eq_s in equalities:
                for sym_name in extract_equality_symbols(eq_s, params.keys()):
                    if sym_name not in params:
                        p = Param(float)
                        p.__set_name__(cls, sym_name)
                        setattr(cls, sym_name, p)
                        params[sym_name] = p

            # Parse constraint inequalities and attach validators to Params.
            if constraints:
                constraint_map = parse_constraints(constraints)
                for name, validators in constraint_map.items():
                    if name not in params:
                        # Constraint references a variable not in any equation
                        # or params -- auto-create it.
                        p = Param(float)
                        p.__set_name__(cls, name)
                        setattr(cls, name, p)
                        params[name] = p
                    # Append constraint validators to the Param.
                    param = params[name]
                    param.validators = tuple(param.validators) + tuple(validators)

            cls._parsed_equations = parse_equations(equalities, params.keys()) if equalities else None
            cls._has_equations = bool(equalities)
        elif not hasattr(cls, "_has_equations"):
            cls._has_equations = False

        cls.__params__ = params

        # Collect AnchorDef descriptors declared at class scope.
        from scadwright.component.anchors import AnchorDef

        anchor_defs: dict[str, AnchorDef] = {}
        for base in reversed(cls.__mro__):
            for name, value in vars(base).items():
                if isinstance(value, AnchorDef):
                    anchor_defs[name] = value
        cls.__anchor_defs__ = anchor_defs

        # If the subclass didn't define its own __init__, and it has Params
        # or anchor defs, generate one that takes the params as kwargs-only
        # and resolves anchor defs after construction.
        if (params or anchor_defs) and "__init__" not in cls.__dict__:
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
        """Declare a named anchor on this Component.

        Prefer the class-scope ``anchor()`` descriptor for most anchors.
        Use this method in ``setup()`` only when anchor position or normal
        depends on conditional logic that can't be expressed as a string
        expression.
        """
        from scadwright.anchor import Anchor

        self._anchors[name] = Anchor(
            position=(float(position[0]), float(position[1]), float(position[2])),
            normal=(float(normal[0]), float(normal[1]), float(normal[2])),
        )

    def get_anchors(self) -> dict:
        """Return this Component's anchors: bbox-derived defaults merged with custom.

        Custom anchors (declared via ``self.anchor()`` in ``setup()``) override
        bbox-derived anchors when they share the same name.
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
        created inside inherit those values.
        """
        if self._built_tree is None:
            cls_name = type(self).__name__
            fn = getattr(self, "fn", None)
            fa = getattr(self, "fa", None)
            fs = getattr(self, "fs", None)
            t0 = time.perf_counter()
            try:
                if fn is None and fa is None and fs is None:
                    self._built_tree = self._invoke_build()
                else:
                    with _resolution(fn=fn, fa=fa, fs=fs):
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
        instance._anchors[name] = _Anchor(position=pos, normal=adef.normal)


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

        # Validate kwargs: must be declared params or implicit kwargs.
        _IMPLICIT = {"fn", "fa", "fs", "center"}
        unknown = set(kwargs) - set(params) - _IMPLICIT
        if unknown:
            raise ValidationError(
                f"{type(self).__name__}: unknown parameter(s): {sorted(unknown)}"
            )

        # If the class has equations, solve for missing equation-variables
        # before checking for missing required params.
        if getattr(cls, "_has_equations", False):
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
                raise ValidationError(
                    f"{type(self).__name__}: {exc}"
                ) from exc
            # Solver may return either newly-solved values or defaults it
            # applied on the user's behalf; both go into kwargs for assignment.
            for name, value in solved.items():
                kwargs.setdefault(name, value)

        missing = [n for n in required if n not in kwargs]
        if missing:
            raise ValidationError(
                f"{type(self).__name__}: missing required parameter(s): {missing}"
            )

        # Initialize the Component base (sets source_location and _built_tree).
        Component.__init__(self, _source_location=loc)

        # Apply each param: provided value or default.
        for name in required + optional:
            if name in kwargs:
                value = kwargs[name]
            else:
                value = params[name].default
            # Goes through Param.__set__ → coerce + validate.
            setattr(self, name, value)

        # Store implicit kwargs (fn/fa/fs/center) as instance attrs so
        # _get_built_tree() picks them up.
        for _impl_name in _IMPLICIT:
            if _impl_name in kwargs:
                object.__setattr__(self, _impl_name, kwargs[_impl_name])

        # Resolve class-scope anchor defs into real anchors.
        _resolve_anchor_defs(self)

        # Optional post-params hook.
        post = getattr(self, "setup", None)
        if callable(post):
            post()

        # Freeze equation-using instances so post-construction Param writes
        # can't desync from the solved values.
        if getattr(cls, "_has_equations", False):
            self._frozen = True

    __init__.__qualname__ = f"{cls.__qualname__}.__init__"
    __init__.__doc__ = f"Auto-generated kwargs-only __init__ for {cls.__name__}."
    return __init__
