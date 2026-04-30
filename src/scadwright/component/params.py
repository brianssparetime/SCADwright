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
        # True when the metaclass auto-created this Param from a name appearing
        # in `equations` or `params = "..."`. Used solely to add a hint to the
        # coercion error when a non-float value lands on an auto-declared float.
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
        """Asymmetric strict type check.

        ``int → float`` is the one allowed widening — every int is a
        valid floating-point value, and dimensional inputs in 3D
        modeling are written as whole numbers (`Tube(thk=1)`,
        `cube([10, 10, 5])`). Every other type is strict isinstance:
        ``:bool`` rejects ``int``, ``:int`` rejects ``float``, ``:str``
        rejects non-strings, etc.
        """
        if self.type is None or value is None:
            return value
        # Reject booleans-as-numbers BEFORE the isinstance check, because
        # `isinstance(True, int)` is True in Python — without this guard,
        # Param(int) would silently accept bool.
        if isinstance(value, bool) and self.type is not bool:
            raise ValidationError(
                f"{type(instance).__name__}.{self._name}: expected {self.type.__name__}, got bool",
                source_location=loc,
            )
        if isinstance(value, self.type):
            return value
        # For int, reject non-integer numerics rather than silently truncating.
        # `int(3.5)` in Python returns 3 — that's almost always a user bug,
        # not an intent to round down.
        if self.type is int and isinstance(value, float) and not value.is_integer():
            raise ValidationError(
                f"{type(instance).__name__}.{self._name}: expected int, "
                f"got non-integer float {value!r} (would silently truncate to "
                f"{int(value)}; pass an int or round explicitly if intended).",
                source_location=loc,
            )
        # Asymmetric int → float widening. Lossless and matches Python's
        # arithmetic semantics where `1 + 1.5` yields `2.5` without any
        # explicit conversion at the source level.
        if self.type is float and isinstance(value, int):
            return float(value)
        # Strict reject for everything else: no `bool(value)`, no
        # `str(value)`, no `tuple(value)`. The user passes the wrong
        # type; the framework says so and lets them fix the call.
        msg = (
            f"{type(instance).__name__}.{self._name}: expected "
            f"{self.type.__name__}, got {type(value).__name__} ({value!r})"
        )
        if self._auto_declared and self.type is float:
            msg += (
                f"\nHint: `{self._name}` was auto-declared as Param(float) "
                f"from its appearance in `equations`. For a non-float value, "
                f"declare it explicitly above the equations list, e.g. "
                f"`{self._name} = Param(tuple)`."
            )
        raise ValidationError(msg, source_location=loc)

    def has_default(self) -> bool:
        return self.default is not _MISSING

    @staticmethod
    def group(names: str, type: type | None = None, **kwargs) -> None:
        """Declare several Params sharing the same type and validators.

        Call from inside a Component class body:

            class Tube(Component):
                Param.group("h id od thk", float, positive=True)
                fn = Param(int, default=None)
                equations = ["od == id + 2*thk"]

        Every name in `names` becomes an independent `Param(type, **kwargs)`
        on the class. `names` is space- or comma-separated. Per-param
        overrides are just separate declarations on following lines.

        Note: attributes are injected into the enclosing class-body namespace
        via frame introspection. IDEs and static type checkers may not see
        them as class attributes. If you need IDE completion for these
        fields, declare them individually.
        """
        import sys

        # Normalize: accept both space and comma separators.
        tokens = [n.strip() for n in names.replace(",", " ").split()]
        if not tokens:
            raise ValidationError("Param.group: names must be non-empty")

        dupes = {n for n in tokens if tokens.count(n) > 1}
        if dupes:
            raise ValidationError(
                f"Param.group: duplicate name(s) in {names!r}: {sorted(dupes)}"
            )

        try:
            frame = sys._getframe(1)
        except ValueError:
            raise ValidationError(
                "Param.group() must be called inside a class body"
            ) from None

        # Class bodies have `__qualname__` set in their namespace during
        # class construction (distinguishes them from module/function frames).
        if "__qualname__" not in frame.f_locals:
            raise ValidationError(
                "Param.group() must be called inside a class body"
            )

        namespace = frame.f_locals
        class_qualname = namespace.get("__qualname__", "<unknown>")
        for name in tokens:
            if name in namespace:
                raise ValidationError(
                    f"Param.group: name {name!r} is already defined in class "
                    f"{class_qualname!r}. Param.group doesn't override existing "
                    f"declarations — either remove the earlier definition, pick "
                    f"a different name, or omit {name!r} from the group and "
                    f"declare only the others."
                )
            namespace[name] = Param(type, **kwargs)


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
