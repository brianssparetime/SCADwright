"""``Spec`` — a frozen, equation-resolved value bag for cross-file
shared dimensions.

A ``Spec`` is like a Component minus geometry: it carries an
``equations`` block (with adjustments and rules), runs the same
resolver, and exposes the resolved values either as class attributes
(when no ``?param`` is declared) or via per-instance access (when at
least one is). Specs reuse the entire equations DSL, the iterative
resolver, the adjustment phase, and the introspection API; this
module is a thin coordinator that wires those pieces into a non-
geometry container with appropriate freezing.

Two access modes:

- **Fixed** (no ``?param``): the resolver runs at class-definition
  time. Resolved values land on the class as plain attributes
  (``S2Spec.lens_mount_od``). The metaclass freezes the class so
  reassigning a resolved value raises ``ValidationError``.

- **Parameterized** (one or more ``?param``): class-level attribute
  access for resolved-value names raises with a clear "instantiate
  this Spec" hint. ``S2Spec(printer_profile=BAMBU_X1)`` constructs an
  instance whose attributes carry the resolved values; the instance
  is frozen after construction.
"""

from __future__ import annotations

from typing import Any

from scadwright.component._subclass_setup import (
    _apply_class_attr_overrides,
    _collect_params_from_mro,
    _register_equations,
)
from scadwright.component.params import Param
from scadwright.errors import ValidationError


class _ClassOrInstanceMethod:
    """Descriptor that dispatches to ``f(cls, *args)`` when accessed on
    the class and ``f(self, *args)`` when accessed on an instance.

    Used by :class:`Spec` so ``S2Spec.adjustments_for("x")`` (class
    form, fixed Spec) and ``s.adjustments_for("x")`` (instance form,
    parameterized Spec) both work via the same name. The wrapped
    function inspects ``isinstance(target, type)`` to branch.
    """

    def __init__(self, f):
        self.f = f
        self.__doc__ = f.__doc__
        self.__name__ = f.__name__
        self.__qualname__ = f.__qualname__

    def __get__(self, instance, owner):
        target = instance if instance is not None else owner
        f = self.f

        def call(*args, **kwargs):
            return f(target, *args, **kwargs)

        call.__doc__ = self.__doc__
        call.__name__ = self.__name__
        call.__qualname__ = self.__qualname__
        return call


class _SpecMeta(type):
    """Metaclass enforcing class-level freeze and the parameterized-
    Spec class-attr-access rejection.

    ``__setattr__`` rejects writes to declared spec values once the
    class is marked frozen. Internal init goes through
    ``type.__setattr__`` to bypass; user reassignments hit the
    metaclass and raise.

    ``__getattr__`` only fires for missing attributes — used to deliver
    the "instantiate this Spec" message when a user tries
    ``ParameterizedSpec.some_value`` on a class whose values aren't
    resolved at class-definition time.
    """

    def __setattr__(cls, name: str, value: Any) -> None:
        # ``_class_frozen`` is set at the end of __init_subclass__;
        # afterward, writes to declared spec values raise. Internal
        # init goes through ``type.__setattr__`` to bypass.
        if cls.__dict__.get("_class_frozen", False):
            spec_names: frozenset[str] = cls.__dict__.get(
                "_spec_value_names", frozenset()
            )
            params = cls.__dict__.get("__params__", {})
            if name in spec_names or name in params:
                raise ValidationError(
                    f"{cls.__name__}.{name}: Spec is frozen after "
                    f"resolution; cannot reassign. To change a value, "
                    f"edit the equations block in the {cls.__name__} "
                    f"definition (or, for a parameterized Spec, "
                    f"construct an instance with the desired "
                    f"parameters)."
                )
        super().__setattr__(name, value)

    def __getattribute__(cls, name: str) -> Any:
        # Intercept class-level attribute lookups for parameterized
        # Specs to deliver an actionable "instantiate this Spec" error.
        # We can't use ``__getattr__`` for this because ``Param``
        # descriptors return the descriptor object on class-level
        # access — normal lookup succeeds, ``__getattr__`` never fires.
        #
        # ``type.__getattribute__`` bypasses this method to avoid
        # recursion when reading the metadata bookkeeping attributes
        # below; bare ``getattr(...)`` here would re-enter.
        if name.startswith("__") and name.endswith("__"):
            return type.__getattribute__(cls, name)
        try:
            is_param = type.__getattribute__(cls, "_parameterized")
            spec_names = type.__getattribute__(cls, "_spec_value_names")
        except AttributeError:
            return type.__getattribute__(cls, name)
        if is_param and name in spec_names:
            raise AttributeError(
                f"{cls.__name__}.{name}: this Spec has parameters, "
                f"so its values are only available on an instance. "
                f"Use {cls.__name__}(...).{name} instead."
            )
        return type.__getattribute__(cls, name)



class Spec(metaclass=_SpecMeta):
    """Base for cross-file shared-dimension value bags.

    Subclass and write an ``equations`` block. Resolved values become
    class attributes (no ``?param`` declared) or instance attributes
    (any ``?param`` declared).

    The class itself is frozen after resolution: assigning to a
    resolved value name raises ``ValidationError``. Parameterized
    specs reject class-level attribute access for resolved-value
    names with a clear hint to instantiate.
    """

    # Sentinels populated by __init_subclass__ / instance __init__.
    # ``_class_frozen`` blocks reassignment of resolved values on the
    # CLASS (relevant primarily for fixed Specs, where the resolved
    # values live as class attributes). ``_frozen`` is the
    # INSTANCE-level flag for parameterized Specs and matches
    # Component's instance-freeze convention so user code reading
    # ``instance._frozen`` works uniformly across the two.
    _unified_equations: list = []
    _unified_constraints: list = []
    _unified_adjustments: list = []
    _override_names: frozenset = frozenset()
    _optional_names: frozenset = frozenset()
    _spec_value_names: frozenset = frozenset()
    _parameterized: bool = False
    _class_frozen: bool = False
    _frozen: bool = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        params = _collect_params_from_mro(cls)
        _apply_class_attr_overrides(cls, params)
        _register_equations(cls, params)
        type.__setattr__(cls, "__params__", params)

        is_parameterized = bool(cls._optional_names)
        type.__setattr__(cls, "_parameterized", is_parameterized)

        if is_parameterized:
            # Build an __init__ that runs the resolver per instance.
            cls.__init__ = _make_spec_init(cls, params)
            # The class itself is frozen against further class-attr
            # writes (no resolved values to write at class-define time
            # in the parameterized case, so freezing here just
            # prevents stray class-attr writes by the user).
            type.__setattr__(cls, "_class_frozen", True)
            return

        # Fixed Spec: resolve at class-define time.
        if cls._unified_equations or cls._unified_adjustments:
            from scadwright.component.resolver import IterativeResolver
            resolver = IterativeResolver(
                equations=cls._unified_equations,
                constraints=cls._unified_constraints,
                params=params,
                supplied={},
                component_name=cls.__name__,
                override_names=cls._override_names,
                adjustments=cls._unified_adjustments,
            )
            resolved = resolver.resolve()
            for name, value in resolved.items():
                type.__setattr__(cls, name, value)
            type.__setattr__(
                cls,
                "_provenance",
                {
                    name: tuple(adjs)
                    for name, adjs in resolver._provenance.items()
                },
            )
        type.__setattr__(cls, "_class_frozen", True)

    def __setattr__(self, name: str, value: Any) -> None:
        # Instance-level freeze for parameterized Specs. Mirrors the
        # Component freeze flag (``_frozen``) so user code that reads
        # ``instance._frozen`` works uniformly across both. Different
        # from the metaclass's ``_class_frozen`` which guards class-
        # level reassignment for fixed Specs.
        if getattr(self, "_frozen", False):
            cls = type(self)
            if name in cls.__dict__.get("_spec_value_names", frozenset()):
                raise ValidationError(
                    f"{cls.__name__}.{name}: Spec instance is frozen "
                    f"after construction; cannot reassign. Construct "
                    f"a new {cls.__name__}(...) with the desired "
                    f"parameters instead."
                )
        object.__setattr__(self, name, value)

    @_ClassOrInstanceMethod
    def adjustments_for(target, name: str) -> list:
        """Return the adjustments applied to ``name`` in source order.

        Works on both the class (fixed Spec) and an instance
        (parameterized Spec). On a parameterized Spec class — where
        provenance lives per-instance, not per-class — raises
        :class:`ValidationError` directing the caller to instantiate.

        Raises :class:`ValidationError` when ``name`` is unknown to
        the spec; empty list when ``name`` exists but was never
        adjusted (or every adjustment skipped).
        """
        from scadwright.component.adjustments import adjustments_for_lookup

        if isinstance(target, type):
            # Class form: provenance lives on the class for fixed
            # Specs only. Reject if parameterized.
            if target.__dict__.get("_parameterized", False):
                raise ValidationError(
                    f"{target.__name__}.adjustments_for: this Spec has "
                    f"parameters; call on an instance instead, e.g. "
                    f"{target.__name__}(...).adjustments_for({name!r})."
                )
            provenance = target.__dict__.get("_provenance", {})
            cls = target
        else:
            # Instance form: provenance is on the instance.
            provenance = getattr(target, "_provenance", {}) or {}
            cls = type(target)
        return adjustments_for_lookup(
            name=name,
            provenance=provenance,
            valid_names=cls.__dict__.get("_spec_value_names", frozenset()),
            owner_name=cls.__name__,
        )

    @_ClassOrInstanceMethod
    def all_adjustments(target) -> dict:
        """Return ``{name: [Adjustment, ...]}`` for every adjusted name.

        Works on both the class (fixed Spec) and an instance
        (parameterized Spec); raises on a parameterized class for the
        same reason as :meth:`adjustments_for`.
        """
        from scadwright.component.adjustments import all_adjustments_lookup

        if isinstance(target, type):
            if target.__dict__.get("_parameterized", False):
                raise ValidationError(
                    f"{target.__name__}.all_adjustments: this Spec has "
                    f"parameters; call on an instance instead, e.g. "
                    f"{target.__name__}(...).all_adjustments()."
                )
            provenance = target.__dict__.get("_provenance", {})
        else:
            provenance = getattr(target, "_provenance", {}) or {}
        return all_adjustments_lookup(provenance)


def _make_spec_init(cls, params: dict[str, Param]):
    """Build an auto-generated kwargs-only ``__init__`` for a
    parameterized Spec subclass.

    Mirrors ``_init_factory._make_param_init`` but stripped of the
    geometry pipeline (no anchors, no build, no centering, no source
    location bookkeeping). The instance freezes against further
    Param/spec-value writes after construction.
    """
    from scadwright.component._init_factory import _IMPLICIT_KWARGS

    required = [n for n, p in params.items() if not p.has_default()]
    optional = [n for n, p in params.items() if p.has_default()]

    def __init__(self, **kwargs):
        unknown = set(kwargs) - set(params) - _IMPLICIT_KWARGS
        if unknown:
            raise ValidationError(
                f"{type(self).__name__}: unknown parameter(s): "
                f"{sorted(unknown)}"
            )

        from scadwright.component.resolver import IterativeResolver

        resolver = IterativeResolver(
            equations=cls._unified_equations,
            constraints=cls._unified_constraints,
            params=params,
            supplied=dict(kwargs),
            component_name=cls.__name__,
            override_names=cls._override_names,
            adjustments=cls._unified_adjustments,
        )
        resolved = resolver.resolve()

        # Mirror init-factory's adjustment-aware kwargs merge so the
        # post-adjust value lands on the instance even when the user
        # supplied the pre-adjust value as a kwarg. Runs BEFORE the
        # missing-required check so resolver-derived values count as
        # supplied.
        adjusted_names = {adj.name for adj in cls._unified_adjustments}
        override_names = cls._override_names
        for name, value in resolved.items():
            if (
                name in override_names
                and kwargs.get(name) is None
                and value is not None
            ):
                kwargs[name] = value
                continue
            if name in adjusted_names:
                kwargs[name] = value
                continue
            if name in kwargs:
                continue
            kwargs[name] = value

        missing = [n for n in required if n not in kwargs]
        if missing:
            raise ValidationError(
                f"{type(self).__name__}: missing required parameter(s): "
                f"{missing}"
            )

        # Apply each Param via __set__ so coercion + per-Param
        # validators fire.
        for name in required + optional:
            if name in kwargs:
                value = kwargs[name]
            else:
                value = params[name].default
            setattr(self, name, value)

        # Derivation-target values (computed names that aren't Params
        # — same fall-through as Component) go on the instance directly.
        param_names = set(params)
        for name, value in kwargs.items():
            if name not in param_names and name not in _IMPLICIT_KWARGS:
                object.__setattr__(self, name, value)

        # Adjustment provenance for the introspection API.
        object.__setattr__(
            self,
            "_provenance",
            {
                name: tuple(adjs)
                for name, adjs in resolver._provenance.items()
            },
        )

        # Freeze the instance.
        object.__setattr__(self, "_frozen", True)

    __init__.__qualname__ = f"{cls.__qualname__}.__init__"
    __init__.__doc__ = (
        f"Auto-generated kwargs-only __init__ for parameterized Spec "
        f"{cls.__name__}."
    )
    return __init__
