"""ChamferedBox Component: cuboid with chamfered or filleted edges."""

from __future__ import annotations

from scadwright.boolops import intersection, minkowski
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder, sphere


class ChamferedBox(Component):
    """Box with edges rounded (fillet) or cut at 45 degrees (chamfer).

    ``size`` is ``(x, y, z)``. ``fillet`` rounds all edges with a sphere
    of that radius (like RoundedBox). ``chamfer`` cuts 45-degree bevels
    of that depth. Specify one or the other, not both.

    The result is centered on the origin.
    """

    size = Param(tuple)
    fillet = Param(float, default=None)
    chamfer = Param(float, default=None)

    def setup(self):
        if len(self.size) != 3:
            raise ValidationError(
                f"ChamferedBox: size must be a 3-tuple, got {self.size!r}"
            )
        if self.fillet is not None and self.chamfer is not None:
            raise ValidationError(
                "ChamferedBox: specify fillet or chamfer, not both"
            )
        if self.fillet is None and self.chamfer is None:
            raise ValidationError(
                "ChamferedBox: specify either fillet or chamfer"
            )
        edge = self.fillet if self.fillet is not None else self.chamfer
        for i, s in enumerate(self.size):
            if s <= 2 * edge:
                raise ValidationError(
                    f"ChamferedBox: size[{i}]={s} must be > 2*edge={2*edge}"
                )

    def build(self):
        x, y, z = self.size

        if self.fillet is not None:
            r = self.fillet
            inner = cube(
                [x - 2 * r, y - 2 * r, z - 2 * r], center=True
            )
            return minkowski(inner, sphere(r=r))

        # Chamfer: intersection of the box with three axis-aligned
        # cylinders whose diameter matches the box diagonal on each
        # face pair. This clips the corners and edges at 45 degrees.
        c = self.chamfer
        base = cube([x, y, z], center=True)
        # Cylinders along each axis, sized to clip the chamfer depth.
        cx = cylinder(h=x + 0.02, r=(min(y, z) / 2 - c) / (2**0.5 - 1) + min(y, z) / 2, center=True).rotate([0, 90, 0])
        cy = cylinder(h=y + 0.02, r=(min(x, z) / 2 - c) / (2**0.5 - 1) + min(x, z) / 2, center=True).rotate([90, 0, 0])
        cz = cylinder(h=z + 0.02, r=(min(x, y) / 2 - c) / (2**0.5 - 1) + min(x, y) / 2, center=True)
        return intersection(base, cx, cy, cz)
