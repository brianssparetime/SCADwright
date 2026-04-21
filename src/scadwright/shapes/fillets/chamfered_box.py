"""ChamferedBox Component: cuboid with chamfered or filleted edges."""

from __future__ import annotations

from scadwright.boolops import minkowski
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.errors import ValidationError
from scadwright.primitives import cube, polyhedron, sphere


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

        # Chamfer via Minkowski sum with a regular octahedron of "radius" c
        # (vertices at ±c on each axis). The octahedron's eight triangular
        # faces are 45° to all three principal axes, so the sum produces
        # the documented 45-degree bevels of depth c on every cube edge.
        # Mirrors the fillet branch's minkowski(cube, sphere) pattern.
        c = self.chamfer
        inner = cube([x - 2 * c, y - 2 * c, z - 2 * c], center=True)
        oct = polyhedron(
            points=[
                (c, 0, 0), (-c, 0, 0),
                (0, c, 0), (0, -c, 0),
                (0, 0, c), (0, 0, -c),
            ],
            faces=[
                [0, 2, 4], [0, 4, 3], [0, 3, 5], [0, 5, 2],
                [1, 4, 2], [1, 2, 5], [1, 5, 3], [1, 3, 4],
            ],
        )
        return minkowski(inner, oct)
