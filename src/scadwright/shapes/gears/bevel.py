"""Bevel gear Component (simplified conical approximation)."""

from __future__ import annotations

import math

from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.extrusions import linear_extrude
from scadwright.shapes.gears.involute import spur_profile


class BevelGear(Component):
    """Simplified bevel gear: a spur gear profile tapered to a cone.

    This is an approximation (Tredgold's method): a spur gear profile
    is linearly scaled from full size at the base to a smaller size at
    the tip. Suitable for visualization and 3D-printing prototypes.

    ``cone_angle`` (degrees) is the half-angle of the pitch cone.
    For a 90-degree gear pair, each gear has ``cone_angle=45``.
    """

    equations = [
        "module, h > 0",
        "pressure_angle > 0",
        "pressure_angle <= 45",
        "cone_angle > 0",
        "cone_angle < 90",
        "pitch_r == module * teeth / 2",
        "base_r == pitch_r * cos(pressure_angle * pi / 180)",
        "outer_r == pitch_r + module",
        "root_r == pitch_r - 1.25 * module",
    ]
    teeth = Param(int, min=6)
    pressure_angle = Param(float, default=20.0)
    cone_angle = Param(float, default=45.0)

    def build(self):
        profile = spur_profile(self.module, self.teeth, self.pressure_angle)
        # Taper: scale at the top is reduced by the cone geometry.
        scale_top = 1 - self.h * math.tan(math.radians(self.cone_angle)) / self.pitch_r
        scale_top = max(0.01, scale_top)
        return linear_extrude(profile, height=self.h, scale=scale_top)
