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

import ast
import inspect
import time
from typing import Any

from scadwright.ast.base import Node, SourceLocation
from scadwright.api.resolution import resolution as _resolution
from scadwright.component.params import Param, _MISSING
from scadwright.errors import BuildError, SCADwrightError, ValidationError
from scadwright._logging import get_logger

_log = get_logger("scadwright.component")


# Algebraic function names used in equations that produce numeric results.
# Mirror of ``_ALGEBRAIC_FUNCTION_NAMES`` in resolver_ast plus a few extra
# numeric-yielding callables.
_NUMERIC_CALL_NAMES = frozenset({
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
    "degrees", "radians",
    "sqrt", "log", "exp", "abs", "ceil", "floor",
    "min", "max", "sum", "round",
    "int", "float",
})


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
        if node.func.id not in _NUMERIC_CALL_NAMES:
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
    eq_target_names: set[str] = set()
    for eq in unified_eqs:
        if isinstance(eq.lhs, ast.Name):
            eq_target_names.add(eq.lhs.id)
        if isinstance(eq.rhs, ast.Name):
            eq_target_names.add(eq.rhs.id)
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
        bare_targets = []
        if isinstance(eq.lhs, ast.Name):
            bare_targets.append((eq.lhs.id, eq.rhs))
        if isinstance(eq.rhs, ast.Name):
            bare_targets.append((eq.rhs.id, eq.lhs))
        for name, other_side in bare_targets:
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
    eq_lhs_target_names: set[str] = set()
    for eq in unified_eqs:
        if isinstance(eq.lhs, ast.Name):
            eq_lhs_target_names.add(eq.lhs.id)
        if isinstance(eq.rhs, ast.Name):
            eq_lhs_target_names.add(eq.rhs.id)
    cls._override_names = frozenset(optional_names & eq_lhs_target_names)

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


# =============================================================================
# build() return-value diagnostics
# =============================================================================
#
# When ``build()`` returns something the framework can't materialize, the
# error needs to be specific enough that a user (especially a fresh AI
# instance) can fix it without grepping the source. The two functions below
# format the diagnostic; the actual raise site is in ``_invoke_build``.


def _describe_build_result(result) -> str:
    """One-phrase description of an unexpected ``build()`` return value."""
    from scadwright.ast.base import Node as _Node

    if result is None:
        return "None"
    if isinstance(result, (list, tuple)):
        kind = type(result).__name__
        if not result:
            return f"empty {kind}"
        if all(isinstance(x, _Node) for x in result):
            return f"{kind} of {len(result)} Nodes"
        bad = [(i, type(x).__name__) for i, x in enumerate(result)
               if not isinstance(x, _Node)]
        bad_summary = ", ".join(t for _, t in bad[:3])
        if len(bad) > 3:
            bad_summary += f", ... ({len(bad)} total)"
        return f"{kind} with non-Node items (types: {bad_summary})"
    return type(result).__name__


def _build_return_hint(result) -> str | None:
    """Return a focused hint for the most common new-author mistakes, or
    ``None`` to fall back to the generic message."""
    from scadwright.ast.base import Node as _Node

    if result is None:
        return (
            "did you forget a `return` statement? For multiple parts, "
            "use `yield each_part` (auto-unioned by the framework)."
        )
    if isinstance(result, (list, tuple)):
        if not result:
            return (
                "build() must `yield` at least one part, or `return` a "
                "single Node."
            )
        if all(isinstance(x, _Node) for x in result):
            return (
                "change `return [a, b, c]` to either `yield a; yield b; "
                "yield c` (preferred — auto-unioned by the framework) "
                "or `return union(a, b, c)`."
            )
        # mixed list/tuple: indices are useful, the description already
        # names the bad types — no extra hint adds value.
        return None
    return None


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
        # Frozen Components refuse writes to any Param. Params cover both
        # user-supplied inputs and resolver-filled values; under the
        # unified spec those are the same category. Reassigning any of
        # them after __init__ would desync the instance from the
        # equations that produced it.
        if getattr(self, "_frozen", False):
            cls = type(self)
            if name in cls.__params__:
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

    def anchor(
        self,
        name: str,
        position: tuple,
        normal: tuple,
        *,
        kind: str = "planar",
        surface_params=None,
    ) -> None:
        """Declare a named anchor on this Component at runtime.

        Prefer the class-scope ``anchor()`` descriptor — both ``at=`` and
        ``normal=`` accept string expressions, which cover conditional
        positions and conditional normals. This method is the imperative
        escape hatch for Components that genuinely can't express an anchor
        declaratively.

        ``kind`` and ``surface_params`` carry surface-type metadata for
        decoration transforms (see ``docs/add_text.md``). The default
        ``"planar"`` covers every flat face.
        """
        from scadwright.anchor import Anchor, _normalize_surface_params

        self._anchors[name] = Anchor(
            position=(float(position[0]), float(position[1]), float(position[2])),
            normal=(float(normal[0]), float(normal[1]), float(normal[2])),
            kind=kind,
            surface_params=_normalize_surface_params(surface_params),
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

        # Non-Node, non-generator return values. The base error message stays
        # the same across every shape so existing tests matching on
        # "must return a Node or yield Nodes" continue to pass; we append a
        # focused hint for the most common new-author mistakes.
        cls_name = type(self).__name__
        base = (
            f"{cls_name}.build() must return a Node or yield Nodes; "
            f"got {_describe_build_result(result)}"
        )
        hint = _build_return_hint(result)
        msg = f"{base}\nHint: {hint}" if hint else base
        raise BuildError(msg, source_location=self.source_location)

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
        if hasattr(adef, "resolve_surface_params"):
            sp = adef.resolve_surface_params(instance)
        else:
            sp = ()
        instance._anchors[name] = _Anchor(
            position=pos,
            normal=normal,
            kind=getattr(adef, "kind", "planar"),
            surface_params=sp,
        )


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


def _run_iterative_resolver(cls, params: dict[str, Param], kwargs: dict):
    """Replace the legacy bucketed pipeline with the unified iterative
    resolver. Mutates ``kwargs`` in place to add resolved values, and
    returns the resolver so the caller can read post-resolve metadata
    (`_supplied_names`, `_applied_defaults`, `knowns`) for the emit-time
    glossary.
    """
    from scadwright.component.resolver import IterativeResolver

    resolver = IterativeResolver(
        equations=cls._unified_equations,
        constraints=cls._unified_constraints,
        params=params,
        supplied=dict(kwargs),
        component_name=cls.__name__,
        override_names=getattr(cls, "_override_names", frozenset()),
    )
    try:
        resolved = resolver.resolve()
    except ValidationError:
        raise
    # Push every resolved value into kwargs so the rest of the auto-init
    # picks it up. Skip None-valued keys for params that weren't supplied
    # to avoid over-supplying optionals back into the kwargs.
    override_names = getattr(cls, "_override_names", frozenset())
    for name, value in resolved.items():
        # Override semantic: if the caller passed name=None for an
        # override target, the resolver's pre-resolve filled the
        # value via the override pattern. Prefer the resolver's
        # value over the caller's None.
        if (
            name in override_names
            and kwargs.get(name) is None
            and value is not None
        ):
            kwargs[name] = value
            continue
        if name in kwargs:
            continue
        kwargs[name] = value
    return resolver


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

        # Clearance resolver runs before the equation resolver so the
        # resolved value flows through as a "given" to the solver, same
        # as any explicit kwarg. Only joint Components with
        # _clearance_category opt in.
        _resolve_clearance_kwarg(cls, kwargs)

        has_eqs_or_constraints = bool(
            cls._unified_equations or cls._unified_constraints
        )
        resolver = None
        if has_eqs_or_constraints:
            resolver = _run_iterative_resolver(cls, params, kwargs)

        missing = [n for n in required if n not in kwargs]
        if missing:
            raise ValidationError(
                f"{type(self).__name__}: missing required parameter(s): {missing}"
            )

        # Initialize the Component base (sets source_location and _built_tree).
        Component.__init__(self, _source_location=loc)

        # Stash resolver metadata for the emit-time glossary. Three
        # disjoint name sets cover every entry in the resolved knowns:
        # caller-supplied, Param-default-applied, equation-derived. The
        # third is implicit (knowns − supplied − defaults) and computed
        # on demand by the formatter.
        if resolver is not None:
            object.__setattr__(
                self, "_glossary_supplied", frozenset(resolver._supplied_names),
            )
            object.__setattr__(
                self, "_glossary_defaults", frozenset(resolver._applied_defaults),
            )
            object.__setattr__(
                self, "_glossary_knowns", dict(resolver.knowns),
            )

        # Apply each Param via Param.__set__ (coerces and validates).
        for name in required + optional:
            value = kwargs[name] if name in kwargs else params[name].default
            setattr(self, name, value)

        # Store implicit kwargs as instance attrs so _get_built_tree picks them up.
        for impl in _IMPLICIT_KWARGS:
            if impl in kwargs:
                object.__setattr__(self, impl, kwargs[impl])

        # Derivation-target values (computed names that aren't Params)
        # go on the instance directly so build() can read them.
        if has_eqs_or_constraints:
            param_names = set(params)
            for name, value in kwargs.items():
                if name not in param_names and name not in _IMPLICIT_KWARGS:
                    object.__setattr__(self, name, value)

        _resolve_anchor_defs(self)

        # Framework escape hatch: a user-defined `setup()` method, if
        # present, runs last. Retained as an internal hook for Components
        # that genuinely need imperative work.
        post = getattr(self, "setup", None)
        if callable(post):
            post()

        # Freeze instances whose state is tied to the equations contract.
        # Prevents post-construction Param or derivation-target writes
        # from desynchronizing the instance.
        if has_eqs_or_constraints:
            self._frozen = True

    __init__.__qualname__ = f"{cls.__qualname__}.__init__"
    __init__.__doc__ = f"Auto-generated kwargs-only __init__ for {cls.__name__}."
    return __init__
