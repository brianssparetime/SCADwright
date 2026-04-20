"""Bevel gear Component (simplified conical approximation)."""

from __future__ import annotations

import math

from scadwright.boolops import intersection
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.errors import ValidationError
from scadwright.extrusions import linear_extrude
from scadwright.primitives import cylinder, polygon
from scadwright.shapes.gears.involute import gear_dimensions, involute_tooth_profile


class BevelGear(Component):
    """Simplified bevel gear: a spur gear profile tapered to a cone.

    This is an approximation (Tredgold's method): a spur gear profile
    is linearly scaled from full size at the base to a smaller size at
    the tip. Suitable for visualization and 3D-printing prototypes.

    ``cone_angle`` (degrees) is the half-angle of the pitch cone.
    For a 90-degree gear pair, each gear has ``cone_angle=45``.
    """

    equations = ["module, h > 0"]
    teeth = Param(int)
    pressure_angle = Param(float, default=20.0)
    cone_angle = Param(float, default=45.0)

    def setup(self):                                    # framework hook: optional
        if self.teeth < 6:
            raise ValidationError(
                f"BevelGear: teeth must be >= 6, got {self.teeth}"
            )
        if not (0 < self.cone_angle < 90):
            raise ValidationError(
                f"BevelGear: cone_angle must be in (0, 90), got {self.cone_angle}"
            )
        pr, br, otr, rr = gear_dimensions(self.module, self.teeth, self.pressure_angle)
        self.pitch_r = pr
        self.outer_r = otr

    def build(self):
        # Build the spur gear profile at full size, extrude with linear
        # taper using scale parameter.
        tooth = involute_tooth_profile(
            self.module, self.teeth, self.pressure_angle,
        )
        period = 2 * math.pi / self.teeth
        all_points = []
        for i in range(self.teeth):
            angle = i * period
            c, s = math.cos(angle), math.sin(angle)
            for x, y in tooth:
                all_points.append((x * c - y * s, x * s + y * c))

        profile = polygon(points=all_points)

        # Taper: scale at the top is reduced by the cone geometry.
        scale_top = 1 - self.h * math.tan(math.radians(self.cone_angle)) / self.pitch_r
        scale_top = max(0.01, scale_top)

        return linear_extrude(profile, height=self.h, scale=scale_top)
