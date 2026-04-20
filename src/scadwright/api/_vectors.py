"""Argument-shape normalizers used by factories and transform methods.

Strings and non-numbers are rejected. Ambiguous scalar broadcasts on
transform vectors (e.g. `translate(5)`) raise ValidationError. Scalar
broadcast is retained only for genuinely uniform inputs (cube/square
sizes, uniform scale) where there's one unambiguous interpretation.
"""

from __future__ import annotations

import math
from numbers import Real
from typing import Iterable

from scadwright.ast.base import SourceLocation
from scadwright.errors import ValidationError


Vec3 = tuple[float, float, float]
Vec2 = tuple[float, float]


def _reject_non_numeric(v, name: str) -> None:
    loc = SourceLocation.from_caller()
    raise ValidationError(
        f"{name} must be a number or sequence of numbers, got {type(v).__name__}: {v!r}",
        source_location=loc,
    )


def _coerce_number(x) -> float | None:
    """Return a float if x is a legitimate number, else None.

    Note: `SymbolicExpr` (animation) is intentionally not handled here —
    transform vectors that allow symbolic values use `_coerce_numlike`
    instead, so validators that rely on this helper still see only real
    numbers."""
    if isinstance(x, str) or isinstance(x, bool):
        return None
    if not isinstance(x, Real):
        return None
    f = float(x)
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _coerce_numlike(x):
    """Like `_coerce_number`, but also accepts a `SymbolicExpr` (returned
    as-is). Used by transform vector handling so values like `t() * 10`
    flow through to the emitter without being rejected as non-numeric."""
    from scadwright.animation import SymbolicExpr  # late import: avoid cycle
    if isinstance(x, SymbolicExpr):
        return x
    return _coerce_number(x)


def _as_vec(
    v,
    dim: int,
    *,
    name: str = "value",
    default_scalar_broadcast: bool = True,
    allow_symbolic: bool = False,
) -> tuple:
    """Normalize a vector-like argument to a dim-tuple of floats.

    - If `default_scalar_broadcast` is True, a scalar broadcasts to (n,)*dim.
      Used for genuinely uniform inputs (cube/square sizes, uniform scale).
    - If False, scalar is rejected with guidance to pass a full vector.
    - Strings and bools are always rejected.
    - If `allow_symbolic` is True, individual elements may be `SymbolicExpr`
      instances (e.g. `t() * 360`); they pass through to the emitter.
    """
    coerce = _coerce_numlike if allow_symbolic else _coerce_number
    from scadwright.animation import SymbolicExpr  # late import: avoid cycle

    if isinstance(v, str) or isinstance(v, bool):
        loc = SourceLocation.from_caller()
        raise ValidationError(
            f"{name} must be a number or sequence of numbers, got {type(v).__name__}: {v!r}",
            source_location=loc,
        )
    if isinstance(v, SymbolicExpr):
        if not allow_symbolic:
            loc = SourceLocation.from_caller()
            raise ValidationError(
                f"{name} does not accept symbolic expressions here; use a number",
                source_location=loc,
            )
        # Symbolic scalar broadcast: only allowed where numeric scalar is.
        if not default_scalar_broadcast:
            axes = "xyz"[:dim]
            example_vec = "[" + ", ".join(["t()"] + ["0"] * (dim - 1)) + "]"
            example_kwargs = ", ".join(
                f"{ax}={'t()' if i == 0 else 0}" for i, ax in enumerate(axes)
            )
            loc = SourceLocation.from_caller()
            raise ValidationError(
                f"{name}: scalar (including symbolic) not accepted here. "
                f"Pass a {dim}-vector like {example_vec} or use keyword "
                f"arguments like {example_kwargs}.",
                source_location=loc,
            )
        return (v,) * dim
    if isinstance(v, Real):
        if not default_scalar_broadcast:
            axes = "xyz"[:dim]
            example_vec = "[" + ", ".join(["5"] + ["0"] * (dim - 1)) + "]"
            example_kwargs = ", ".join(
                f"{ax}={5 if i == 0 else 0}" for i, ax in enumerate(axes)
            )
            loc = SourceLocation.from_caller()
            raise ValidationError(
                f"{name}: scalar not accepted here (ambiguous — which axis?). "
                f"Pass a {dim}-vector like {example_vec} or use keyword "
                f"arguments like {example_kwargs}.",
                source_location=loc,
            )
        f = coerce(v)
        if f is None:
            loc = SourceLocation.from_caller()
            raise ValidationError(
                f"{name} must be finite, got {v!r}",
                source_location=loc,
            )
        return (f,) * dim
    try:
        seq = list(v)
    except TypeError:
        loc = SourceLocation.from_caller()
        raise ValidationError(
            f"{name} must be iterable, got {type(v).__name__}: {v!r}",
            source_location=loc,
        ) from None
    if len(seq) != dim:
        loc = SourceLocation.from_caller()
        raise ValidationError(
            f"{name} must have exactly {dim} elements, got {len(seq)}: {seq!r}",
            source_location=loc,
        )
    out = []
    for i, x in enumerate(seq):
        f = coerce(x)
        if f is None:
            loc = SourceLocation.from_caller()
            raise ValidationError(
                f"{name}[{i}] must be a finite number, got {type(x).__name__}: {x!r}",
                source_location=loc,
            )
        out.append(f)
    return tuple(out)


def _as_vec3(
    v,
    *,
    name: str = "value",
    default_scalar_broadcast: bool = True,
    allow_symbolic: bool = False,
) -> Vec3:
    return _as_vec(
        v,
        3,
        name=name,
        default_scalar_broadcast=default_scalar_broadcast,
        allow_symbolic=allow_symbolic,
    )  # type: ignore[return-value]


def _as_vec2(
    v,
    *,
    name: str = "value",
    default_scalar_broadcast: bool = True,
    allow_symbolic: bool = False,
) -> Vec2:
    return _as_vec(
        v,
        2,
        name=name,
        default_scalar_broadcast=default_scalar_broadcast,
        allow_symbolic=allow_symbolic,
    )  # type: ignore[return-value]


def _vec_from_args(
    v,
    x: float,
    y: float,
    z: float,
    *,
    name: str = "value",
    default: Vec3 = (0.0, 0.0, 0.0),
    allow_symbolic: bool = False,
) -> Vec3:
    """Resolve a 3-vector from either a positional v or x/y/z kwargs.

    Scalar broadcast is NOT allowed here — transform vectors need a full 3-vec
    or keyword form. `translate(5)` is an error; `translate([5,0,0])` or
    `translate(x=5)` is correct. With `allow_symbolic=True`, individual
    elements may be `SymbolicExpr` for animation.
    """
    coerce = _coerce_numlike if allow_symbolic else _coerce_number
    if v is not None:
        return _as_vec3(
            v,
            name=name,
            default_scalar_broadcast=False,
            allow_symbolic=allow_symbolic,
        )
    out = []
    for axis, val in (("x", x), ("y", y), ("z", z)):
        f = coerce(val)
        if f is None:
            loc = SourceLocation.from_caller()
            raise ValidationError(
                f"{name}.{axis} must be a finite number, got {type(val).__name__}: {val!r}",
                source_location=loc,
            )
        out.append(f)
    return (out[0], out[1], out[2])


def _normalize_center_2d(center) -> tuple[bool, bool]:
    if isinstance(center, bool):
        return (center, center)
    if isinstance(center, str):
        s = center.lower()
        return ("x" in s, "y" in s)
    if isinstance(center, Iterable):
        seq = [bool(b) for b in center]
        while len(seq) < 2:
            seq.append(False)
        return (seq[0], seq[1])
    b = bool(center)
    return (b, b)


def _normalize_center(center) -> tuple[bool, bool, bool]:
    if isinstance(center, bool):
        return (center, center, center)
    if isinstance(center, str):
        s = center.lower()
        return ("x" in s, "y" in s, "z" in s)
    if isinstance(center, Iterable):
        seq = [bool(b) for b in center]
        while len(seq) < 3:
            seq.append(False)
        return (seq[0], seq[1], seq[2])
    b = bool(center)
    return (b, b, b)
