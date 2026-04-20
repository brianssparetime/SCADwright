"""Timing pulley Components (GT2, HTD)."""

from __future__ import annotations

import math

from scadwright.boolops import difference
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.errors import ValidationError
from scadwright.primitives import cylinder


class GT2Pulley(Component):
    """GT2 timing belt pulley.

    ``teeth`` determines the pulley diameter (GT2 pitch = 2mm).
    ``bore_d`` is the shaft bore diameter. ``belt_width`` controls
    the pulley width (flanges extend 1mm beyond on each side).

    The pulley is centered on the origin, bore along z.
    """

    teeth = Param(int)
    equations = ["bore_d, belt_width > 0"]

    def setup(self):                                    # framework hook: optional
        if self.teeth < 10:
            raise ValidationError(
                f"GT2Pulley: teeth must be >= 10, got {self.teeth}"
            )
        self.pitch_d = self.teeth * 2.0 / math.pi
        self.od = self.pitch_d + 1.0  # approximate outer diameter

    def build(self):
        flange_extra = 1.0
        body = cylinder(h=self.belt_width, d=self.od)
        # Flanges: slightly wider discs on top and bottom.
        flange_d = self.od + 2 * flange_extra
        flange_h = 0.8
        bottom_flange = cylinder(h=flange_h, d=flange_d).down(flange_h)
        top_flange = cylinder(h=flange_h, d=flange_d).up(self.belt_width)
        bore = cylinder(
            h=self.belt_width + 2 * flange_h + 0.02,
            d=self.bore_d,
        ).down(flange_h + 0.01)

        from scadwright.boolops import union
        return difference(union(body, bottom_flange, top_flange), bore)


class HTDPulley(Component):
    """HTD (High Torque Drive) timing belt pulley.

    ``teeth`` and ``pitch`` (default 5mm for HTD-5M) determine the
    diameter. Otherwise identical to GT2Pulley in structure.
    """

    teeth = Param(int)
    equations = ["bore_d, belt_width, pitch > 0"]

    def setup(self):                                    # framework hook: optional
        if self.teeth < 10:
            raise ValidationError(
                f"HTDPulley: teeth must be >= 10, got {self.teeth}"
            )
        self.pitch_d = self.teeth * self.pitch / math.pi
        self.od = self.pitch_d + 1.5

    def build(self):
        flange_extra = 1.0
        body = cylinder(h=self.belt_width, d=self.od)
        flange_d = self.od + 2 * flange_extra
        flange_h = 1.0
        bottom_flange = cylinder(h=flange_h, d=flange_d).down(flange_h)
        top_flange = cylinder(h=flange_h, d=flange_d).up(self.belt_width)
        bore = cylinder(
            h=self.belt_width + 2 * flange_h + 0.02,
            d=self.bore_d,
        ).down(flange_h + 0.01)

        from scadwright.boolops import union
        return difference(union(body, bottom_flange, top_flange), bore)
