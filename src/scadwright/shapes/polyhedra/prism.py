"""Prism and Pyramid Components."""

from __future__ import annotations

import math

from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import polyhedron


class Prism(Component):
    """N-sided prism (or frustum when top_r differs from r).

    The prism sits with its base on z=0, centered on the origin in XY.
    ``sides`` must be at least 3. When ``top_r`` is provided and differs
    from ``r``, the result is a frustum (tapered prism).
    """

    equations = ["r, h > 0", "top_r >= 0"]
    sides = Param(int, min=3)
    top_r = Param(float, default=None)

    def build(self):
        n = self.sides
        r_bot = self.r
        r_top = self.top_r if self.top_r is not None else self.r
        h = self.h

        # Bottom and top vertex rings.
        points = []
        for i in range(n):
            angle = 2 * math.pi * i / n
            c, s = math.cos(angle), math.sin(angle)
            points.append((r_bot * c, r_bot * s, 0.0))
        for i in range(n):
            angle = 2 * math.pi * i / n
            c, s = math.cos(angle), math.sin(angle)
            points.append((r_top * c, r_top * s, h))

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
        points = []
        for i in range(n):
            angle = 2 * math.pi * i / n
            points.append((self.r * math.cos(angle), self.r * math.sin(angle), 0.0))
        apex = len(points)
        points.append((0.0, 0.0, self.h))

        faces = []
        # Base (reversed winding).
        faces.append(list(range(n - 1, -1, -1)))
        # Side triangles.
        for i in range(n):
            faces.append([i, (i + 1) % n, apex])

        return polyhedron(points=points, faces=faces)
