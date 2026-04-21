"""Timing pulley Components (GT2, HTD)."""

from __future__ import annotations


from scadwright.boolops import difference
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cylinder


class GT2Pulley(Component):
    """GT2 timing belt pulley.

    ``teeth`` determines the pulley diameter (GT2 pitch = 2mm).
    ``bore_d`` is the shaft bore diameter. ``belt_width`` controls
    the pulley width (flanges extend 1mm beyond on each side).

    The pulley is centered on the origin, bore along z.
    """

    teeth = Param(int, min=10)
    equations = [
        "bore_d, belt_width > 0",
        "pitch_d == teeth * 2.0 / pi",
        "od == pitch_d + 1.0",
    ]

    def build(self):
        flange_extra = 1.0
        body = cylinder(h=self.belt_width, d=self.od)
        # Flanges: slightly wider discs on top and bottom.
        flange_d = self.od + 2 * flange_extra
        flange_h = 0.8
        bottom_flange = cylinder(h=flange_h, d=flange_d).down(flange_h)
        top_flange = cylinder(h=flange_h, d=flange_d).up(self.belt_width)

        from scadwright.boolops import union
        assembled = union(body, bottom_flange, top_flange)
        bore = cylinder(
            h=self.belt_width + 2 * flange_h,
            d=self.bore_d,
        ).down(flange_h)
        return difference(assembled, bore.through(assembled))


class HTDPulley(Component):
    """HTD (High Torque Drive) timing belt pulley.

    ``teeth`` and ``pitch`` (default 5mm for HTD-5M) determine the
    diameter. Otherwise identical to GT2Pulley in structure.
    """

    teeth = Param(int, min=10)
    equations = [
        "bore_d, belt_width, pitch > 0",
        "pitch_d == teeth * pitch / pi",
        "od == pitch_d + 1.5",
    ]

    def build(self):
        flange_extra = 1.0
        body = cylinder(h=self.belt_width, d=self.od)
        flange_d = self.od + 2 * flange_extra
        flange_h = 1.0
        bottom_flange = cylinder(h=flange_h, d=flange_d).down(flange_h)
        top_flange = cylinder(h=flange_h, d=flange_d).up(self.belt_width)

        from scadwright.boolops import union
        assembled = union(body, bottom_flange, top_flange)
        bore = cylinder(
            h=self.belt_width + 2 * flange_h,
            d=self.bore_d,
        ).down(flange_h)
        return difference(assembled, bore.through(assembled))
