"""SCAD-semantic math wrappers.

Names match OpenSCAD's built-ins. Trigonometric functions take and return
**degrees** (SCAD's convention), not radians. Use as `sc.math.sin(90)`, etc.

Available: sum, min, max, abs, sign, floor, ceil, round, pow, sqrt, exp, ln,
log, sin, cos, tan, asin, acos, atan, atan2, norm, cross.
"""

from __future__ import annotations

import math as _m
from typing import Iterable


# --- numeric reductions / misc ---


def sum(values: Iterable[float], start: float = 0.0) -> float:  # noqa: A001
    """SCAD sum: sum of an iterable of numbers. Scalars only; no element-wise vector sum."""
    import builtins

    return float(builtins.sum(values, start))


def min(*args):  # noqa: A001
    import builtins

    if len(args) == 1:
        return builtins.min(args[0])
    return builtins.min(args)


def max(*args):  # noqa: A001
    import builtins

    if len(args) == 1:
        return builtins.max(args[0])
    return builtins.max(args)


def abs(x: float) -> float:  # noqa: A001
    import builtins

    return float(builtins.abs(x))


def sign(x: float) -> float:
    if x > 0:
        return 1.0
    if x < 0:
        return -1.0
    return 0.0


def floor(x: float) -> int:
    return _m.floor(x)


def ceil(x: float) -> int:
    return _m.ceil(x)


def round(x: float) -> int:  # noqa: A001
    """SCAD round: half-away-from-zero. Python's round() does banker's rounding."""
    if x >= 0:
        return int(_m.floor(x + 0.5))
    return -int(_m.floor(-x + 0.5))


def pow(base: float, exp: float) -> float:  # noqa: A001
    return _m.pow(base, exp)


def sqrt(x: float) -> float:
    return _m.sqrt(x)


def exp(x: float) -> float:
    return _m.exp(x)


def ln(x: float) -> float:
    return _m.log(x)


def log(x: float, base: float = 10) -> float:
    """SCAD log: base 10 by default."""
    return _m.log(x, base)


# --- trig (degrees) ---


def sin(deg: float) -> float:
    return _m.sin(_m.radians(deg))


def cos(deg: float) -> float:
    return _m.cos(_m.radians(deg))


def tan(deg: float) -> float:
    return _m.tan(_m.radians(deg))


def asin(x: float) -> float:
    return _m.degrees(_m.asin(x))


def acos(x: float) -> float:
    return _m.degrees(_m.acos(x))


def atan(x: float) -> float:
    return _m.degrees(_m.atan(x))


def atan2(y: float, x: float) -> float:
    return _m.degrees(_m.atan2(y, x))


# --- vector math ---


def norm(v) -> float:
    """Euclidean norm of a vector."""
    return _m.sqrt(__builtins_sum_of_squares(v))


def __builtins_sum_of_squares(v) -> float:
    total = 0.0
    for x in v:
        total += float(x) * float(x)
    return total


def cross(a, b) -> tuple[float, float, float]:
    """3D cross product."""
    from scadwright.errors import ValidationError
    a = tuple(float(x) for x in a)
    b = tuple(float(x) for x in b)
    if len(a) != 3 or len(b) != 3:
        raise ValidationError("cross requires 3-vectors")
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )
