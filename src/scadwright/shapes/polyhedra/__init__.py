"""Polyhedra and basic 3D shapes."""

from scadwright.shapes.polyhedra.dome import Dome, Ellipsoid, Ogive, Paraboloid
from scadwright.shapes.polyhedra.prism import Prism, Pyramid
from scadwright.shapes.polyhedra.regular import (
    Dodecahedron,
    Icosahedron,
    Octahedron,
    Tetrahedron,
)
from scadwright.shapes.polyhedra.torus import Elbow, Torus

__all__ = [
    "Dodecahedron",
    "Dome",
    "Elbow",
    "Ellipsoid",
    "Icosahedron",
    "Octahedron",
    "Ogive",
    "Paraboloid",
    "Prism",
    "Pyramid",
    "Tetrahedron",
    "Torus",
]
