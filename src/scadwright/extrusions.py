"""Standalone functional extrusions.

Both forms produce the same AST — use whichever reads better at the call site:

    from scadwright.extrusions import linear_extrude
    part = linear_extrude(circle(r=5), height=10)

    # equivalently, via the chained method on Node:
    part = circle(r=5).linear_extrude(height=10)
"""

from __future__ import annotations

from scadwright.api._validate import (
    _require_integer,
    _require_number,
    _require_positive,
    _require_resolution,
    _require_size_vec2,
)
from scadwright.api.resolution import resolve as _resolve_res
from scadwright.ast.base import Node, SourceLocation
from scadwright.ast.extrude import LinearExtrude, RotateExtrude
from scadwright.errors import ValidationError


def linear_extrude(
    child: Node,
    height: float,
    *,
    center: bool = False,
    twist: float = 0.0,
    slices: int | None = None,
    scale=1.0,
    convexity: int | None = None,
    fn: float | None = None,
    fa: float | None = None,
    fs: float | None = None,
) -> LinearExtrude:
    if not isinstance(child, Node):
        loc = SourceLocation.from_caller()
        raise ValidationError(
            f"linear_extrude child must be a Node, got {type(child).__name__}",
            source_location=loc,
        )
    height = _require_positive(height, "linear_extrude height")
    twist = _require_number(twist, "linear_extrude twist")
    if slices is not None:
        slices = _require_integer(slices, "linear_extrude slices")
    if convexity is not None:
        convexity = _require_integer(convexity, "linear_extrude convexity")
    from numbers import Real

    if isinstance(scale, Real) and not isinstance(scale, bool):
        scale_val = _require_positive(scale, "linear_extrude scale")
    else:
        scale_val = _require_size_vec2(scale, "linear_extrude scale")
    fn, fa, fs = _resolve_res(fn, fa, fs)
    fn, fa, fs = _require_resolution(fn, fa, fs, context="linear_extrude")
    return LinearExtrude(
        child=child,
        height=height,
        center=bool(center),
        twist=twist,
        slices=slices,
        scale=scale_val,
        convexity=convexity,
        fn=fn,
        fa=fa,
        fs=fs,
        source_location=SourceLocation.from_caller(),
    )


def rotate_extrude(
    child: Node,
    *,
    angle: float = 360.0,
    convexity: int | None = None,
    fn: float | None = None,
    fa: float | None = None,
    fs: float | None = None,
) -> RotateExtrude:
    if not isinstance(child, Node):
        loc = SourceLocation.from_caller()
        raise ValidationError(
            f"rotate_extrude child must be a Node, got {type(child).__name__}",
            source_location=loc,
        )
    angle = _require_number(angle, "rotate_extrude angle")
    if convexity is not None:
        convexity = _require_integer(convexity, "rotate_extrude convexity")
    fn, fa, fs = _resolve_res(fn, fa, fs)
    fn, fa, fs = _require_resolution(fn, fa, fs, context="rotate_extrude")
    return RotateExtrude(
        child=child,
        angle=angle,
        convexity=convexity,
        fn=fn,
        fa=fa,
        fs=fs,
        source_location=SourceLocation.from_caller(),
    )


__all__ = ["linear_extrude", "rotate_extrude"]
