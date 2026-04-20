"""Argument validators for factories.

Strict type checks — reject strings where numbers are expected, require iterables
where vectors are expected, reject NaN/inf, enforce sign constraints where
meaningful. Raises ValidationError with a source location at the caller's call
site.

Rule on booleans: `True` and `False` are rejected everywhere a number is
expected, even though Python makes `bool` a subclass of `int`. A boolean
turning into 0 or 1 silently is almost always a bug in geometry code
(`cube(True)` isn't what anyone meant). If a factory legitimately takes a
boolean (centering, flags, etc.), it uses a separate `bool`-typed validator.
The same rule applies in the Param descriptor's type coercion.
"""

from __future__ import annotations

import math
from numbers import Real
from typing import Iterable

from scadwright.ast.base import SourceLocation
from scadwright.errors import ValidationError


def _loc() -> SourceLocation | None:
    """Source location at the first user frame outside scadwright."""
    return SourceLocation.from_caller()


def _is_symbolic(value) -> bool:
    from scadwright.animation import SymbolicExpr
    return isinstance(value, SymbolicExpr)


def _require_number(value, name: str) -> float:
    """Require a finite number. Rejects bool, str, non-Real. SymbolicExpr is
    passed through unchanged so animation expressions can flow into primitive
    sizes; sign/range checks below also short-circuit on symbolic values."""
    if _is_symbolic(value):
        return value  # type: ignore[return-value]
    if isinstance(value, str) or not isinstance(value, Real) or isinstance(value, bool):
        raise ValidationError(
            f"{name} must be a number, got {type(value).__name__}: {value!r}",
            source_location=_loc(),
        )
    f = float(value)
    if math.isnan(f) or math.isinf(f):
        raise ValidationError(
            f"{name} must be finite, got {f}",
            source_location=_loc(),
        )
    return f


def _require_non_negative(value, name: str) -> float:
    f = _require_number(value, name)
    if _is_symbolic(f):
        return f  # type: ignore[return-value]
    if f < 0:
        raise ValidationError(
            f"{name} must be non-negative, got {f}",
            source_location=_loc(),
        )
    return f


def _require_positive(value, name: str) -> float:
    f = _require_number(value, name)
    if _is_symbolic(f):
        return f  # type: ignore[return-value]
    if f <= 0:
        raise ValidationError(
            f"{name} must be positive, got {f}",
            source_location=_loc(),
        )
    return f


def _require_resolution(
    fn: float | None,
    fa: float | None,
    fs: float | None,
    *,
    context: str,
) -> tuple[float | None, float | None, float | None]:
    """Validate a (fn, fa, fs) triple. Each must be positive when set.

    Call AFTER `_resolve_res(...)` so that context-inherited values are
    checked too (not just explicit kwargs). `context` names the caller
    (e.g. "sphere") for error messages.
    """
    if fn is not None:
        fn = _require_positive(fn, f"{context} fn")
    if fa is not None:
        fa = _require_positive(fa, f"{context} fa")
    if fs is not None:
        fs = _require_positive(fs, f"{context} fs")
    return (fn, fa, fs)


def _require_integer(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValidationError(
            f"{name} must be an integer, got {type(value).__name__}: {value!r}",
            source_location=_loc(),
        )
    f = float(value)
    if not f.is_integer():
        raise ValidationError(
            f"{name} must be an integer, got {value!r}",
            source_location=_loc(),
        )
    return int(f)


def _require_vec(value, dim: int, name: str) -> tuple[float, ...]:
    """Require an iterable of exactly `dim` finite numbers. Strings are rejected."""
    if isinstance(value, str) or isinstance(value, Real):
        raise ValidationError(
            f"{name} must be a length-{dim} iterable of numbers, got {type(value).__name__}: {value!r}",
            source_location=_loc(),
        )
    try:
        items = list(value)
    except TypeError:
        raise ValidationError(
            f"{name} must be iterable, got {type(value).__name__}: {value!r}",
            source_location=_loc(),
        ) from None
    if len(items) != dim:
        raise ValidationError(
            f"{name} must have exactly {dim} elements, got {len(items)}: {items!r}",
            source_location=_loc(),
        )
    out = []
    for i, x in enumerate(items):
        if isinstance(x, str) or not isinstance(x, Real) or isinstance(x, bool):
            raise ValidationError(
                f"{name}[{i}] must be a number, got {type(x).__name__}: {x!r}",
                source_location=_loc(),
            )
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            raise ValidationError(
                f"{name}[{i}] must be finite, got {f}",
                source_location=_loc(),
            )
        out.append(f)
    return tuple(out)


def _require_vec3(value, name: str) -> tuple[float, float, float]:
    v = _require_vec(value, 3, name)
    return (v[0], v[1], v[2])


def _require_vec2(value, name: str) -> tuple[float, float]:
    v = _require_vec(value, 2, name)
    return (v[0], v[1])


def _require_non_empty(seq, name: str) -> None:
    if len(seq) == 0:
        raise ValidationError(
            f"{name} must be non-empty",
            source_location=_loc(),
        )


def _require_size_vec3(value, name: str) -> tuple[float, float, float]:
    """Vec3 of non-negative numbers. For cube sizes, resize targets, etc."""
    v = _require_vec3(value, name)
    for i, f in enumerate(v):
        if f < 0:
            raise ValidationError(
                f"{name}[{i}] must be non-negative, got {f}",
                source_location=_loc(),
            )
    return v


def _require_size_vec2(value, name: str) -> tuple[float, float]:
    v = _require_vec2(value, name)
    for i, f in enumerate(v):
        if f < 0:
            raise ValidationError(
                f"{name}[{i}] must be non-negative, got {f}",
                source_location=_loc(),
            )
    return v
