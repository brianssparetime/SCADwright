"""Worm and WormGear Components using sweep."""

from __future__ import annotations

import math

from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.shapes.curves.paths import helix_path
from scadwright.shapes.curves.sweep import path_extrude
from scadwright.shapes.gears.involute import spur_profile
from scadwright.extrusions import linear_extrude


class Worm(Component):
    """Worm (screw gear) that meshes with a WormGear.

    A helical thread on a cylindrical shaft. The worm axis is along z.
    ``leads`` is the number of thread starts (1 = single-start).
    """

    equations = [
        "module, length, shaft_r > 0",
        "pressure_angle > 0",
        "pressure_angle <= 45",
        "pitch == pi * module",
        "thread_r == shaft_r + module",
    ]
    leads = Param(int, default=1, min=1)
    pressure_angle = Param(float, default=20.0)

    def build(self):
        # Trapezoidal thread cross-section.
        m = self.module
        pa = math.radians(self.pressure_angle)
        addendum = m
        dedendum = 1.25 * m
        half_top = m * math.pi / 4 - addendum * math.tan(pa)
        half_bot = m * math.pi / 4 + dedendum * math.tan(pa)

        profile = [
            (half_top, addendum),
            (-half_top, addendum),
            (-half_bot, -dedendum),
            (half_bot, -dedendum),
        ]

        # Sweep the thread profile along a helix.
        turns = self.length / self.pitch
        path = helix_path(
            r=self.shaft_r + addendum / 2,
            pitch=self.pitch * self.leads,
            turns=turns / self.leads,
            points_per_turn=36,
        )
        return path_extrude(profile, path)


class WormGear(Component):
    """Worm gear (worm wheel) that meshes with a Worm.

    Essentially a spur gear whose module matches the worm's module.
    The gear axis is along z, perpendicular to the worm axis.
    """

    equations = [
        "module, h > 0",
        "pressure_angle > 0",
        "pressure_angle <= 45",
        "pitch_r == module * teeth / 2",
        "base_r == pitch_r * cos(pressure_angle * pi / 180)",
        "outer_r == pitch_r + module",
        "root_r == pitch_r - 1.25 * module",
    ]
    teeth = Param(int, min=12)
    pressure_angle = Param(float, default=20.0)

    def build(self):
        profile = spur_profile(self.module, self.teeth, self.pressure_angle)
        return linear_extrude(profile, height=self.h)
