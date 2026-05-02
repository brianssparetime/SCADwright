"""Auto-generated ``__init__`` factory for Component subclasses.

When ``Component.__init_subclass__`` finds a subclass with Param
descriptors (or anchor defs) and no hand-written ``__init__``, it calls
``_make_param_init(cls, params)`` to build a kwargs-only auto-init that:

1. Resolves a clearance kwarg from the active clearance chain
   (joint Components opt in via ``_clearance_category``).
2. Runs the iterative resolver to fill in equation-derived values.
3. Validates required Params, applies each via ``Param.__set__`` so
   coercion + per-Param validators fire.
4. Stashes implicit kwargs (``fn``/``fa``/``fs``/``center``) on the
   instance for the build pipeline to pick up.
5. Resolves class-scope anchor declarations into runtime Anchors.
6. Calls the user's ``setup()`` hook if present (escape hatch).
7. Freezes the instance against further Param/derivation writes when
   the Component carries equations or constraints.

The factory is loaded lazily from ``Component.__init_subclass__`` so
that this module can freely import ``Component`` at top level without
creating an import cycle: by the time ``__init_subclass__`` fires for a
real subclass, ``base.py`` is already fully loaded.
"""

from __future__ import annotations

from scadwright.ast.base import SourceLocation
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.errors import ValidationError


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
