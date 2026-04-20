"""Platonic solid Components: Tetrahedron, Octahedron, Dodecahedron, Icosahedron."""

from __future__ import annotations

import math

from scadwright.component.base import Component
from scadwright.primitives import polyhedron


class Tetrahedron(Component):
    """Regular tetrahedron inscribed in a sphere of radius ``r``.

    Centered on the origin with one vertex pointing up (+z).
    """

    equations = ["r > 0"]

    def build(self):
        # Vertices of a regular tetrahedron inscribed in a unit sphere,
        # scaled by r. One vertex at the top.
        r = self.r
        angle = math.acos(-1 / 3)  # ~109.47 degrees
        sin_a = math.sin(angle)
        pts = [
            (0, 0, r),
            (r * sin_a, 0, r * (-1 / 3)),
            (r * sin_a * math.cos(2 * math.pi / 3),
             r * sin_a * math.sin(2 * math.pi / 3),
             r * (-1 / 3)),
            (r * sin_a * math.cos(4 * math.pi / 3),
             r * sin_a * math.sin(4 * math.pi / 3),
             r * (-1 / 3)),
        ]
        faces = [
            [0, 1, 2],
            [0, 2, 3],
            [0, 3, 1],
            [1, 3, 2],
        ]
        return polyhedron(points=pts, faces=faces)


class Octahedron(Component):
    """Regular octahedron inscribed in a sphere of radius ``r``.

    Centered on the origin with vertices on the axes.
    """

    equations = ["r > 0"]

    def build(self):
        r = self.r
        pts = [
            (r, 0, 0), (-r, 0, 0),
            (0, r, 0), (0, -r, 0),
            (0, 0, r), (0, 0, -r),
        ]
        faces = [
            [4, 0, 2], [4, 2, 1], [4, 1, 3], [4, 3, 0],
            [5, 2, 0], [5, 1, 2], [5, 3, 1], [5, 0, 3],
        ]
        return polyhedron(points=pts, faces=faces)


class Dodecahedron(Component):
    """Regular dodecahedron inscribed in a sphere of radius ``r``.

    Centered on the origin.
    """

    equations = ["r > 0"]

    def build(self):
        r = self.r
        phi = (1 + math.sqrt(5)) / 2
        # Vertices of a unit dodecahedron, scaled to circumradius r.
        # The circumradius of a unit dodecahedron (edge=2/phi) is sqrt(3).
        s = r / math.sqrt(3)
        sp = s * phi
        si = s / phi

        pts = [
            # Cube vertices.
            (s, s, s), (s, s, -s), (s, -s, s), (s, -s, -s),
            (-s, s, s), (-s, s, -s), (-s, -s, s), (-s, -s, -s),
            # Rectangle in XY plane.
            (0, si, sp), (0, si, -sp), (0, -si, sp), (0, -si, -sp),
            # Rectangle in XZ plane.
            (si, sp, 0), (si, -sp, 0), (-si, sp, 0), (-si, -sp, 0),
            # Rectangle in YZ plane.
            (sp, 0, si), (sp, 0, -si), (-sp, 0, si), (-sp, 0, -si),
        ]
        faces = [
            [0, 16, 2, 10, 8],
            [0, 8, 4, 14, 12],
            [16, 17, 3, 13, 2],
            [1, 12, 14, 5, 9],
            [1, 9, 11, 3, 17],
            [0, 12, 1, 17, 16],
            [2, 13, 15, 6, 10],
            [4, 8, 10, 6, 18],
            [4, 18, 19, 5, 14],
            [7, 11, 9, 5, 19],
            [7, 15, 13, 3, 11],
            [6, 15, 7, 19, 18],
        ]
        return polyhedron(points=pts, faces=faces)


class Icosahedron(Component):
    """Regular icosahedron inscribed in a sphere of radius ``r``.

    Centered on the origin.
    """

    equations = ["r > 0"]

    def build(self):
        r = self.r
        phi = (1 + math.sqrt(5)) / 2
        # Circumradius of a unit icosahedron (edge=2) is sqrt(phi+2) ~= 1.902.
        s = r / math.sqrt(phi + 2)
        sp = s * phi

        pts = [
            (0, s, sp), (0, s, -sp), (0, -s, sp), (0, -s, -sp),
            (s, sp, 0), (s, -sp, 0), (-s, sp, 0), (-s, -sp, 0),
            (sp, 0, s), (sp, 0, -s), (-sp, 0, s), (-sp, 0, -s),
        ]
        faces = [
            [0, 2, 8], [0, 8, 4], [0, 4, 6], [0, 6, 10], [0, 10, 2],
            [2, 5, 8], [8, 9, 4], [4, 1, 6], [6, 11, 10], [10, 7, 2],
            [3, 5, 7], [3, 9, 5], [3, 1, 9], [3, 11, 1], [3, 7, 11],
            [5, 2, 7], [9, 8, 5], [1, 4, 9], [11, 6, 1], [7, 10, 11],
        ]
        return polyhedron(points=pts, faces=faces)
