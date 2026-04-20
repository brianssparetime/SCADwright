"""Curve and sweep shapes: path generators, sweep, helix, spring, transforms."""

from scadwright.shapes.curves.helix import Helix, Spring
from scadwright.shapes.curves.paths import bezier_path, catmull_rom_path, helix_path
from scadwright.shapes.curves.sweep import circle_profile, path_extrude

# Import to trigger registration of along_curve, bend, twist_copy transforms.
import scadwright.shapes.curves.transforms as _transforms  # noqa: F401

__all__ = [
    "Helix",
    "Spring",
    "bezier_path",
    "catmull_rom_path",
    "circle_profile",
    "helix_path",
    "path_extrude",
]
