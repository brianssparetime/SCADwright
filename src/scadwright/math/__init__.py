"""SCAD-semantic math wrappers.

Names match OpenSCAD's built-ins. Trigonometric functions take and return
**degrees** (SCAD's convention), not radians. Use as `sc.math.sin(90)`, etc.

Available: sum, min, max, abs, sign, floor, ceil, round, pow, sqrt, exp, ln,
log, sin, cos, tan, asin, acos, atan, atan2, norm, cross.

Every function also accepts animation expressions such as `t() * 360`.
Given one, it returns an expression that emits the matching SCAD call
(`sin($t * 360)`) instead of computing a number at build time. The names
and degree convention already match SCAD, so the call emits unchanged.
"""

from __future__ import annotations

import math as _m
from typing import Iterable

from scadwright.animation import FuncCall, SymbolicExpr


def _symbolic(*args) -> bool:
    return any(isinstance(a, SymbolicExpr) for a in args)


# --- numeric reductions / misc ---


def sum(values: Iterable[float], start: float = 0.0) -> float:  # noqa: A001
    """SCAD sum: sum of an iterable of numbers. Scalars only; no element-wise vector sum."""
    import builtins

    values = list(values)
    if _symbolic(start, *values):
        # Skip a zero start so the emitted sum doesn't open with `0 + `.
        if not isinstance(start, SymbolicExpr) and start == 0 and values:
            return builtins.sum(values[1:], values[0])
        return builtins.sum(values, start)
    return float(builtins.sum(values, start))


def min(*args):  # noqa: A001
    import builtins

    if len(args) == 1:
        args = tuple(args[0])
    if _symbolic(*args):
        return FuncCall("min", args)
    return builtins.min(args)


def max(*args):  # noqa: A001
    import builtins

    if len(args) == 1:
        args = tuple(args[0])
    if _symbolic(*args):
        return FuncCall("max", args)
    return builtins.max(args)


def abs(x: float) -> float:  # noqa: A001
    import builtins

    if _symbolic(x):
        return FuncCall("abs", [x])
    return float(builtins.abs(x))


def sign(x: float) -> float:
    if _symbolic(x):
        return FuncCall("sign", [x])
    if x > 0:
        return 1.0
    if x < 0:
        return -1.0
    return 0.0


def floor(x: float) -> int:
    if _symbolic(x):
        return FuncCall("floor", [x])
    return _m.floor(x)


def ceil(x: float) -> int:
    if _symbolic(x):
        return FuncCall("ceil", [x])
    return _m.ceil(x)


def round(x: float) -> int:  # noqa: A001
    """SCAD round: half-away-from-zero. Python's round() does banker's rounding."""
    if _symbolic(x):
        return FuncCall("round", [x])
    if x >= 0:
        return int(_m.floor(x + 0.5))
    return -int(_m.floor(-x + 0.5))


def pow(base: float, exp: float) -> float:  # noqa: A001
    if _symbolic(base, exp):
        return FuncCall("pow", [base, exp])
    return _m.pow(base, exp)


def sqrt(x: float) -> float:
    if _symbolic(x):
        return FuncCall("sqrt", [x])
    return _m.sqrt(x)


def exp(x: float) -> float:
    if _symbolic(x):
        return FuncCall("exp", [x])
    return _m.exp(x)


def ln(x: float) -> float:
    if _symbolic(x):
        return FuncCall("ln", [x])
    return _m.log(x)


def log(x: float, base: float = 10) -> float:
    """SCAD log: base 10 by default."""
    if _symbolic(x, base):
        # SCAD's log() is base 10 only; other bases go through ln.
        if not isinstance(base, SymbolicExpr) and base == 10:
            return FuncCall("log", [x])
        return FuncCall("ln", [x]) / FuncCall("ln", [base])
    return _m.log(x, base)


# --- trig (degrees) ---


def sin(deg: float) -> float:
    if _symbolic(deg):
        return FuncCall("sin", [deg])
    return _m.sin(_m.radians(deg))


def cos(deg: float) -> float:
    if _symbolic(deg):
        return FuncCall("cos", [deg])
    return _m.cos(_m.radians(deg))


def tan(deg: float) -> float:
    if _symbolic(deg):
        return FuncCall("tan", [deg])
    return _m.tan(_m.radians(deg))


def asin(x: float) -> float:
    if _symbolic(x):
        return FuncCall("asin", [x])
    return _m.degrees(_m.asin(x))


def acos(x: float) -> float:
    if _symbolic(x):
        return FuncCall("acos", [x])
    return _m.degrees(_m.acos(x))


def atan(x: float) -> float:
    if _symbolic(x):
        return FuncCall("atan", [x])
    return _m.degrees(_m.atan(x))


def atan2(y: float, x: float) -> float:
    if _symbolic(y, x):
        return FuncCall("atan2", [y, x])
    return _m.degrees(_m.atan2(y, x))


# --- vector math ---


def norm(v) -> float:
    """Euclidean norm of a vector."""
    v = list(v)
    if _symbolic(*v):
        # FuncCall can't emit a vector literal, so spell out the sum of squares.
        return FuncCall("sqrt", [sum(x * x for x in v)])
    return _m.sqrt(__builtins_sum_of_squares(v))


def __builtins_sum_of_squares(v) -> float:
    total = 0.0
    for x in v:
        total += float(x) * float(x)
    return total


def cross(a, b) -> tuple[float, float, float]:
    """3D cross product."""
    from scadwright.errors import ValidationError
    a, b = tuple(a), tuple(b)
    if not _symbolic(*a, *b):
        a = tuple(float(x) for x in a)
        b = tuple(float(x) for x in b)
    if len(a) != 3 or len(b) != 3:
        raise ValidationError("cross requires 3-vectors")
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )
