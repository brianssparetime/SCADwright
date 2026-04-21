"""Shared helpers for polyhedra Components."""

from __future__ import annotations

import math


def ring_points(n: int, r: float, z: float) -> list[tuple[float, float, float]]:
    """``n`` evenly-spaced points on a circle of radius ``r`` at height ``z``.

    Used by Prism, Pyramid, Tetrahedron, Octahedron — any polyhedron
    whose vertex set decomposes into one or more regular polygonal rings.
    """
    return [
        (r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), z)
        for i in range(n)
    ]
