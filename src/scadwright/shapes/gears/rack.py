"""Rack (linear gear) Component."""

from __future__ import annotations

import math

from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.extrusions import linear_extrude
from scadwright.primitives import polygon


class Rack(Component):
    """Linear gear rack that meshes with a spur gear of the same module.

    The rack extends along the x-axis, centered at x=0. Teeth point
    upward (+y in 2D, +z after extrusion). ``length`` is the total
    rack length; ``teeth`` is the number of teeth.

    ``h`` is the extrusion depth (z-axis).
    """

    equations = [
        "module, length, h > 0",
        "pressure_angle > 0",
        "pressure_angle <= 45",
    ]
    teeth = Param(int, min=1)
    pressure_angle = Param(float, default=20.0)

    def build(self):
        m = self.module
        pa = math.radians(self.pressure_angle)
        pitch = math.pi * m  # circular pitch
        addendum = m
        dedendum = 1.25 * m
        tooth_half = pitch / 4

        # Build the 2D rack profile: a series of trapezoidal teeth.
        points = []
        start_x = -self.length / 2

        # Bottom-left corner.
        points.append((start_x, -dedendum))

        for i in range(self.teeth):
            cx = start_x + (i + 0.5) * pitch
            # Left root.
            left_root_x = cx - tooth_half - dedendum * math.tan(pa)
            # Left tip.
            left_tip_x = cx - tooth_half + addendum * math.tan(pa)
            # Right tip.
            right_tip_x = cx + tooth_half - addendum * math.tan(pa)
            # Right root.
            right_root_x = cx + tooth_half + dedendum * math.tan(pa)

            points.append((left_root_x, -dedendum))
            points.append((left_tip_x, addendum))
            points.append((right_tip_x, addendum))
            points.append((right_root_x, -dedendum))

        # Bottom-right corner.
        end_x = start_x + self.teeth * pitch
        points.append((end_x, -dedendum))

        # Close the bottom.
        points.append((end_x, -dedendum - m))
        points.append((start_x, -dedendum - m))

        profile = polygon(points=points)
        return linear_extrude(profile, height=self.h)
