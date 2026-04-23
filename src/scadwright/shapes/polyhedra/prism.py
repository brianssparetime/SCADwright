"""Prism and Pyramid Components."""

from __future__ import annotations

from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import polyhedron
from scadwright.shapes.polyhedra._util import ring_points


class Prism(Component):
    """N-sided prism (or frustum when top_r differs from r).

    The prism sits with its base on z=0, centered on the origin in XY.
    ``sides`` must be at least 3. When ``top_r`` is provided and differs
    from ``r``, the result is a frustum (tapered prism).
    """

    equations = ["r, h > 0", "?top_r > 0"]
    sides = Param(int, min=3)

    def build(self):
        n = self.sides
        r_top = self.top_r if self.top_r is not None else self.r

        points = ring_points(n, self.r, 0.0) + ring_points(n, r_top, self.h)

        faces = []
        # Bottom face (reversed winding).
        faces.append(list(range(n - 1, -1, -1)))
        # Top face.
        faces.append(list(range(n, 2 * n)))
        # Side quads (as two triangles each).
        for i in range(n):
            i_next = (i + 1) % n
            faces.append([i, i_next, n + i_next, n + i])

        return polyhedron(points=points, faces=faces)


class Pyramid(Component):
    """N-sided pyramid tapering to a point at (0, 0, h).

    The base sits on z=0, centered on the origin in XY.
    """

    equations = ["r, h > 0"]
    sides = Param(int, min=3)

    def build(self):
        n = self.sides
        points = ring_points(n, self.r, 0.0)
        apex = len(points)
        points.append((0.0, 0.0, self.h))

        faces = []
        # Base (reversed winding).
        faces.append(list(range(n - 1, -1, -1)))
        # Side triangles.
        for i in range(n):
            faces.append([i, (i + 1) % n, apex])

        return polyhedron(points=points, faces=faces)
