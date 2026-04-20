"""2D and 3D primitive shape factories.

Import what you need:

    from scadwright.primitives import cube, cylinder, circle

or, for quick scripts, glob-import the whole (small) surface:

    from scadwright.primitives import *
"""

from scadwright.api.factories import (
    circle,
    cube,
    cylinder,
    polygon,
    polyhedron,
    scad_import,
    sphere,
    square,
    surface,
    text,
)

__all__ = [
    "cube",
    "sphere",
    "cylinder",
    "polyhedron",
    "square",
    "circle",
    "polygon",
    "text",
    "surface",
    "scad_import",
]
