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
    # `fillet > 0` and `chamfer > 0` are per-Param constraints that fire
    # only when the value is non-None (optional-Param opt-out), so they
    # coexist with the XOR predicate below.
    equations = [
        "fillet > 0",
        "chamfer > 0",
        "len(size) == 3",
        "(fillet is None) != (chamfer is None)",                                                 # XOR: exactly one
        "all(s > 2 * (fillet if fillet is not None else chamfer) for s in size)",
    ]
    fillet = Param(float, default=None)
    chamfer = Param(float, default=None)

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
