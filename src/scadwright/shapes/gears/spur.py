"""Spur gear Component."""

from __future__ import annotations

import math

from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.extrusions import linear_extrude
from scadwright.shapes.gears.involute import spur_profile


class SpurGear(Component):
    """Involute spur gear.

    Standard involute tooth profile. Specify ``module`` (tooth size),
    ``teeth`` (count), and ``h`` (thickness). The gear is centered on
    the origin with the bore along the z-axis.

    ``helix_angle`` (degrees) produces a helical gear. Set to 0
    (default) for a straight spur gear. For herringbone, build two
    helical gears mirrored.

    Published attributes: ``pitch_r``, ``outer_r``, ``root_r``,
    ``base_r`` (the standard gear circle radii).
    """

    equations = [
        "module, h > 0",
        "pressure_angle > 0",
        "pressure_angle <= 45",
        "helix_angle >= -45",
        "helix_angle <= 45",
        "pitch_r == module * teeth / 2",
        "base_r == pitch_r * cos(pressure_angle * pi / 180)",
        "outer_r == pitch_r + module",
        "root_r == pitch_r - 1.25 * module",
    ]
    teeth = Param(int, min=6)
    pressure_angle = Param(float, default=20.0)
    helix_angle = Param(float, default=0.0)

    def build(self):
        profile = spur_profile(self.module, self.teeth, self.pressure_angle)

        if self.helix_angle != 0:
            # Helical gear: lead L = pi * d / tan(beta) is the axial
            # distance per revolution; total twist over height h is
            # 360 * h / L = 360 * h * tan(beta) / (pi * d), with beta
            # in radians for tan().
            beta_rad = math.radians(self.helix_angle)
            pitch_d = 2 * self.pitch_r
            total_twist = 360.0 * self.h * math.tan(beta_rad) / (math.pi * pitch_d)
            return linear_extrude(profile, height=self.h, twist=total_twist)
        return linear_extrude(profile, height=self.h)
