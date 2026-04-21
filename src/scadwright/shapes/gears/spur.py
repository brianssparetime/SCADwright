"""Spur gear Component."""

from __future__ import annotations

import math

from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.extrusions import linear_extrude
from scadwright.primitives import polygon
from scadwright.shapes.gears.involute import gear_dimensions, involute_tooth_profile


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
    ]
    teeth = Param(int, min=6)
    pressure_angle = Param(float, default=20.0)
    helix_angle = Param(float, default=0.0)

    def setup(self):                                    # framework hook: optional
        pr, br, otr, rr = gear_dimensions(self.module, self.teeth, self.pressure_angle)
        self.pitch_r = pr
        self.base_r = br
        self.outer_r = otr
        self.root_r = rr

    def build(self):
        # Generate one tooth-period polygon and rotate N copies.
        tooth = involute_tooth_profile(
            self.module, self.teeth, self.pressure_angle,
        )
        period = 2 * math.pi / self.teeth

        # Build the full gear profile by rotating the tooth polygon.
        all_points = []
        for i in range(self.teeth):
            angle = i * period
            c, s = math.cos(angle), math.sin(angle)
            for x, y in tooth:
                all_points.append((x * c - y * s, x * s + y * c))

        profile = polygon(points=all_points)

        twist = self.helix_angle if self.helix_angle != 0 else None
        if twist is not None:
            # Twist per unit height: tan(helix_angle) * 360 / (pi * pitch_d)
            # Simplified: twist the full height by helix_angle degrees.
            return linear_extrude(profile, height=self.h, twist=twist)
        return linear_extrude(profile, height=self.h)
