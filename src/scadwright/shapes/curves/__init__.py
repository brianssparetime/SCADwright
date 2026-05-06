"""Curve and sweep shapes: path generators, sweep, helix, spring, transforms."""

from scadwright.shapes.curves.helix import Helix, Spring
from scadwright.shapes.curves.paths import (
    arc_path,
    bezier_path,
    catmull_rom_path,
    composite_bezier_path,
    helix_path,
)
from scadwright.shapes.curves.shapes_2d import bezier_2d, catmull_rom_2d
from scadwright.shapes.curves.sweep import (
    circle_profile,
    path_extrude,
    polygon_profile,
    rounded_rect_profile,
    square_profile,
)

# Import to trigger registration of along_curve, bend, twist_copy transforms.
import scadwright.shapes.curves.transforms as _transforms  # noqa: F401

__all__ = [
    "Helix",
    "Spring",
    "arc_path",
    "bezier_2d",
    "bezier_path",
    "catmull_rom_2d",
    "catmull_rom_path",
    "circle_profile",
    "composite_bezier_path",
    "helix_path",
    "path_extrude",
    "polygon_profile",
    "rounded_rect_profile",
    "square_profile",
]
