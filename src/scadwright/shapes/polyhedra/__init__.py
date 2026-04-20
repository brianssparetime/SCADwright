"""Polyhedra and basic 3D shapes."""

from scadwright.shapes.polyhedra.dome import Dome, SphericalCap
from scadwright.shapes.polyhedra.prism import Prism, Pyramid
from scadwright.shapes.polyhedra.regular import (
    Dodecahedron,
    Icosahedron,
    Octahedron,
    Tetrahedron,
)
from scadwright.shapes.polyhedra.torus import Torus

__all__ = [
    "Dodecahedron",
    "Dome",
    "Icosahedron",
    "Octahedron",
    "Prism",
    "SphericalCap",
    "Pyramid",
    "Tetrahedron",
    "Torus",
]
