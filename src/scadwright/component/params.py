"""Declarative component parameters: Param descriptor and validator helpers.

Usage:
    class Bracket(sc.Component):
        equations = ["width, height > 0"]

        def build(self):
            return sc.cube([self.width, self.height, 5])

`Param` collects type, default, validators, and doc. The Component metaclass
machinery (`__init_subclass__` in component.base) auto-generates a kwargs-only
`__init__` if the user didn't write one. Plain `__init__` continues to work for
Components that don't use Param.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from scadwright.ast.base import SourceLocation
from scadwright.errors import ValidationError


_MISSING = object()


class Param:
    """Descriptor declaring a component parameter.

    Stored value lives in `instance.__dict__[name]`. Validators run on assignment.
    Type coercion: if `type` is provided and the assigned value isn't already an
    instance, we attempt `type(value)`; ValidationError on failure.
    """

    def __init__(
        self,
        type: type | None = None,
        *,
        default: Any = _MISSING,
        validators: Sequence[Callable[[Any], None]] = (),
        doc: str | None = None,
        # Validator shorthand — expand to callables appended after `validators`.
        positive: bool = False,
        non_negative: bool = False,
        min: Any = None,
        max: Any = None,
        range: tuple[Any, Any] | None = None,
        one_of: Sequence[Any] | None = None,
    ):
        self.type = type
        self.default = default
        self.doc = doc
        self._name: str = ""  # set by __set_name__
        # True when the metaclass auto-created this Param from a name
        # appearing in `equations`. Used solely to add a hint to the
        # coercion error when a non-float value lands on an auto-declared
        # float.
        self._auto_declared: bool = False

        vs = list(validators)
        if positive:
            vs.append(_positive_impl)
        if non_negative:
            vs.append(_non_negative_impl)
        if min is not None:
            vs.append(_minimum_impl(min))
        if max is not None:
            vs.append(_maximum_impl(max))
        if range is not None:
            lo, hi = range
            vs.append(_in_range_impl(lo, hi))
        if one_of is not None:
            vs.append(_one_of_impl(*one_of))
        self.validators = tuple(vs)

    def __set_name__(self, owner, name: str) -> None:
        self._name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        try:
            return instance.__dict__[self._name]
        except KeyError:
            raise AttributeError(self._name) from None

    def __set__(self, instance, value: Any) -> None:
        # Capture source_location up front — from_caller walks past scadwright
        # frames so this lands on the user's call site regardless of whether
        # the assignment came from auto-init, post_params, or user code.
        loc = SourceLocation.from_caller()
        coerced = self._coerce(value, instance, loc)
        # Optional Params (default=None) opt out of validation when unset.
        # This lets `Param(float, default=None)` coexist with `equations = ["x > 0"]`.
        if coerced is not None:
            for v in self.validators:
                try:
                    v(coerced)
                except ValidationError as exc:
                    raise ValidationError(
                        f"{type(instance).__name__}.{self._name}: {exc}",
                        source_location=loc,
                    ) from exc
                except Exception as exc:
                    raise ValidationError(
                        f"{type(instance).__name__}.{self._name}: {exc}",
                        source_location=loc,
                    ) from exc
        instance.__dict__[self._name] = coerced
        # Invalidate cached build/bbox/hash so a subsequent access sees the new value.
        invalidate = getattr(instance, "_invalidate", None)
        if callable(invalidate):
            invalidate()

    def _coerce(self, value: Any, instance, loc=None) -> Any:
        """Asymmetric strict type check — see :func:`_coerce_value`."""
        return _coerce_value(
            value,
            type_=self.type,
            auto_declared=self._auto_declared,
            name=self._name,
            component_name=type(instance).__name__,
            loc=loc,
        )

    def has_default(self) -> bool:
        return self.default is not _MISSING


def _coerce_value(
    value: Any,
    *,
    type_: type | None,
    auto_declared: bool = False,
    name: str = "",
    component_name: str = "",
    loc: SourceLocation | None = None,
) -> Any:
    """Asymmetric strict type check shared by Param.__set__ and the resolver.

    ``int → float`` is the one allowed widening — every int is a valid
    floating-point value, and dimensional inputs in 3D modeling are
    written as whole numbers (``Tube(thk=1)``, ``cube([10, 10, 5])``).
    Every other type is strict isinstance: ``:bool`` rejects ``int``,
    ``:int`` rejects ``float``, ``:str`` rejects non-strings, etc.

    ``type_=None`` and ``value is None`` short-circuit (no coercion).
    Booleans are rejected before the isinstance check because Python's
    ``isinstance(True, int)`` is True — without the guard, ``:int``
    would silently accept ``True``. Non-integer floats land on a
    targeted error rather than silently truncating, since ``int(3.5)``
    returning 3 is almost always a user bug, not an intent to round.

    ``auto_declared`` enables a hint suggesting an explicit ``Param``
    declaration when the float-widening fails for an auto-declared
    name (the resolver sees this when an equation uses a name that was
    auto-typed as float but the caller passed a tuple/etc.).
    """
    if type_ is None or value is None:
        return value
    prefix = (
        f"{component_name}.{name}"
        if component_name and name
        else name or "<param>"
    )
    if isinstance(value, bool) and type_ is not bool:
        raise ValidationError(
            f"{prefix}: expected {type_.__name__}, got bool",
            source_location=loc,
        )
    if isinstance(value, type_):
        return value
    if type_ is float and isinstance(value, int):
        return float(value)
    if (
        type_ is int
        and isinstance(value, float)
        and not value.is_integer()
    ):
        raise ValidationError(
            f"{prefix}: expected int, got non-integer float {value!r} "
            f"(would silently truncate to {int(value)}; pass an int or "
            f"round explicitly if intended).",
            source_location=loc,
        )
    msg = (
        f"{prefix}: expected {type_.__name__}, got "
        f"{type(value).__name__} ({value!r})"
    )
    if auto_declared and type_ is float:
        msg += (
            f"\nHint: `{name}` was auto-declared as Param(float) "
            f"from its appearance in `equations`. For a non-float value, "
            f"declare it explicitly above the equations list, e.g. "
            f"`{name} = Param(tuple)`."
        )
    raise ValidationError(msg, source_location=loc)


# --- Validator helpers ---


def _positive_impl(x):
    if not (x > 0):
        raise ValidationError(f"must be positive, got {x}")


def _non_negative_impl(x):
    if not (x >= 0):
        raise ValidationError(f"must be non-negative, got {x}")


def _minimum_impl(n):
    def check(x):
        if not (x >= n):
            raise ValidationError(f"must be >= {n}, got {x}")
    return check


def _maximum_impl(n):
    def check(x):
        if not (x <= n):
            raise ValidationError(f"must be <= {n}, got {x}")
    return check


def _in_range_impl(lo, hi):
    def check(x):
        if not (lo <= x <= hi):
            raise ValidationError(f"must be in [{lo}, {hi}], got {x}")
    return check


def _one_of_impl(*values):
    valid = set(values)
    def check(x):
        if x not in valid:
            raise ValidationError(f"must be one of {sorted(valid)!r}, got {x!r}")
    return check


# Public names for the list-form `validators=[...]` API (back-compat).
positive = _positive_impl
non_negative = _non_negative_impl
minimum = _minimum_impl
maximum = _maximum_impl
in_range = _in_range_impl
one_of = _one_of_impl
