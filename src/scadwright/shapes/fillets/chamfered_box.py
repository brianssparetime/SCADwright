"""ChamferedBox Component: cuboid with chamfered or filleted edges."""

from __future__ import annotations

from scadwright.boolops import minkowski
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cube, polyhedron, sphere


class ChamferedBox(Component):
    """Box with edges rounded (fillet) or cut at 45 degrees (chamfer).

    ``size`` is ``(x, y, z)``. ``fillet`` rounds all edges with a sphere
    of that radius (like RoundedBox). ``chamfer`` cuts 45-degree bevels
    of that depth. Specify one or the other, not both.

    The result is centered on the origin.
    """

    size = Param(tuple)
    # `?fillet` / `?chamfer` auto-declare as Param(float, default=None); the
    # positivity rules skip when unset. `exactly_one(...)` enforces that
    # the caller specifies one and only one. The `edge` line then names
    # whichever is set so the size check reads as one idea. Truthy form
    # (`?fillet if ?fillet else ?chamfer`) is safe because the positivity
    # rule rejects 0, leaving None as the only falsy value.
    equations = [
        "?fillet > 0",
        "?chamfer > 0",
        "len(size) == 3",
        "exactly_one(?fillet, ?chamfer)",
        "edge = ?fillet if ?fillet else ?chamfer",                                 # active edge radius
        "all(s > 2 * edge for s in size)",                                         # every side fits
    ]

    def build(self):
        x, y, z = self.size
        r = self.edge
        inner = cube([x - 2 * r, y - 2 * r, z - 2 * r], center=True)

        if self.fillet is not None:
            return minkowski(inner, sphere(r=r))

        # Chamfer via Minkowski sum with a regular octahedron of "radius" r
        # (vertices at ±r on each axis). The octahedron's eight triangular
        # faces are 45° to all three principal axes, so the sum produces
        # the documented 45-degree bevels of depth r on every cube edge.
        # Mirrors the fillet branch's minkowski(cube, sphere) pattern.
        oct = polyhedron(
            points=[
                (r, 0, 0), (-r, 0, 0),
                (0, r, 0), (0, -r, 0),
                (0, 0, r), (0, 0, -r),
            ],
            faces=[
                [0, 2, 4], [0, 4, 3], [0, 3, 5], [0, 5, 2],
                [1, 4, 2], [1, 2, 5], [1, 5, 3], [1, 3, 4],
            ],
        )
        return minkowski(inner, oct)
