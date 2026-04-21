"""Extrusion mixin for Node: linear_extrude, rotate_extrude as chained methods."""

from __future__ import annotations


class _ExtrudeMixin:
    """Chained extrusion methods.

    Both exist as standalone functions too (``scadwright.extrusions``);
    use whichever reads better at the call site.
    """

    def linear_extrude(
        self,
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
    ) -> "Node":
        from scadwright.api._validate import _require_resolution
        from scadwright.api._vectors import _as_vec2
        from scadwright.api.resolution import resolve as _resolve_res
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.extrude import LinearExtrude

        scale_val = float(scale) if isinstance(scale, (int, float)) else _as_vec2(scale)
        rfn, rfa, rfs = _resolve_res(fn, fa, fs)
        rfn, rfa, rfs = _require_resolution(rfn, rfa, rfs, context="linear_extrude")
        return LinearExtrude(
            child=self,
            height=float(height),
            center=bool(center),
            twist=float(twist),
            slices=slices,
            scale=scale_val,
            convexity=convexity,
            fn=rfn,
            fa=rfa,
            fs=rfs,
            source_location=SourceLocation.from_caller(),
        )

    def rotate_extrude(
        self,
        *,
        angle: float = 360.0,
        convexity: int | None = None,
        fn: float | None = None,
        fa: float | None = None,
        fs: float | None = None,
    ) -> "Node":
        from scadwright.api._validate import _require_resolution
        from scadwright.api.resolution import resolve as _resolve_res
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.extrude import RotateExtrude

        rfn, rfa, rfs = _resolve_res(fn, fa, fs)
        rfn, rfa, rfs = _require_resolution(rfn, rfa, rfs, context="rotate_extrude")
        return RotateExtrude(
            child=self,
            angle=float(angle),
            convexity=convexity,
            fn=rfn,
            fa=rfa,
            fs=rfs,
            source_location=SourceLocation.from_caller(),
        )
