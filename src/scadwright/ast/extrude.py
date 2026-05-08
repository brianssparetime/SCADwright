"""Extrusion AST nodes."""

from __future__ import annotations

from dataclasses import dataclass

from scadwright.ast.base import Node


@dataclass(frozen=True)
class LinearExtrude(Node):
    child: Node
    height: float
    center: bool = False
    twist: float = 0.0
    slices: int | None = None
    scale: tuple[float, float] | float = 1.0
    convexity: int | None = None
    fn: float | None = None
    fa: float | None = None
    fs: float | None = None

    def fuse_extend(self, anchor, eps: float):
        """Locally extend this linear_extrude by ``eps`` along the
        ``top`` or ``bottom`` planar end-cap anchor.

        Bumps ``height`` by ``eps`` and translates so the opposite
        face stays put. For non-zero ``twist`` or non-unit ``scale``,
        the bumped extrusion's twist rate / scale ratio change by a
        factor of ``height/(height+eps)`` — invisible inside the eps
        band where the union sits.

        Returns ``None`` for non-planar anchors (none today; defensive).
        """
        if anchor.kind != "planar":
            return None
        sign = 1 if anchor.normal[2] > 0 else -1
        bumped = LinearExtrude(
            child=self.child,
            height=self.height + eps,
            center=self.center,
            twist=self.twist,
            slices=self.slices,
            scale=self.scale,
            convexity=self.convexity,
            fn=self.fn,
            fa=self.fa,
            fs=self.fs,
            source_location=self.source_location,
        )
        if self.center:
            delta_z = sign * eps / 2.0
        elif sign < 0:
            delta_z = -eps
        else:
            delta_z = 0.0
        if delta_z == 0.0:
            return bumped
        from scadwright.ast.transforms import Translate
        return Translate(
            v=(0.0, 0.0, delta_z),
            child=bumped,
            source_location=self.source_location,
        )


@dataclass(frozen=True)
class RotateExtrude(Node):
    child: Node
    angle: float = 360.0
    convexity: int | None = None
    fn: float | None = None
    fa: float | None = None
    fs: float | None = None
