"""Ring gear (internal gear) Component."""

from __future__ import annotations

import math

from scadwright.boolops import difference
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.extrusions import linear_extrude
from scadwright.primitives import circle, polygon
from scadwright.shapes.gears.involute import involute_tooth_profile


class RingGear(Component):
    """Internal (ring) gear: teeth on the inside of a ring.

    Meshes with a spur gear of the same module and pressure angle.
    ``rim_thk`` is the wall thickness outside the tooth roots.
    """

    equations = [
        "module, h, rim_thk > 0",
        "pressure_angle > 0",
        "pressure_angle <= 45",
        "pitch_r == module * teeth / 2",
        "outer_r == pitch_r + module",
        "root_r == pitch_r - 1.25 * module",
    ]
    teeth = Param(int, min=12)
    pressure_angle = Param(float, default=20.0)

    def build(self):
        # The ring gear is a disc with the spur gear profile subtracted.
        outer_d = 2 * (self.outer_r + self.rim_thk)

        # Build spur gear profile.
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

        gear_profile = polygon(points=all_points)
        ring = circle(d=outer_d)

        profile_2d = difference(ring, gear_profile)
        return linear_extrude(profile_2d, height=self.h)
