"""Timing pulley Components (GT2, HTD)."""

from __future__ import annotations

from scadwright.boolops import union
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.shapes.three_d import Tube


class _BeltPulley(Component):
    """Shared base for timing-belt pulleys.

    Subclasses declare ``equations`` covering the belt-specific
    geometry: ``pitch_d``, ``od``, ``flange_d``, ``flange_h`` (plus
    any additional inputs like HTD's ``pitch``). The bore is along z;
    the body sits z=[0, belt_width] with flanges extending below z=0
    and above z=belt_width.
    """

    teeth = Param(int, min=10)

    def build(self):
        body = Tube(h=self.belt_width, od=self.od, id=self.bore_d)
        top = Tube(h=self.flange_h, od=self.flange_d, id=self.bore_d).up(self.belt_width)
        bot = Tube(h=self.flange_h, od=self.flange_d, id=self.bore_d).down(self.flange_h)
        return union(body, top, bot)


class GT2Pulley(_BeltPulley):
    """GT2 timing belt pulley.

    ``teeth`` determines the pulley diameter (GT2 pitch = 2mm).
    ``bore_d`` is the shaft bore diameter. ``belt_width`` controls
    the central body width; flanges extend 0.8mm beyond on each side.

    The pulley is centered on the origin, bore along z.
    """

    equations = [
        "bore_d, belt_width > 0",
        "pitch_d == teeth * 2.0 / pi",
        "od == pitch_d + 1.0",
        "flange_d == od + 2.0",
        "flange_h == 0.8",
    ]


class HTDPulley(_BeltPulley):
    """HTD (High Torque Drive) timing belt pulley.

    ``teeth`` and ``pitch`` (default 5mm for HTD-5M) determine the
    diameter. Flanges extend 1.0mm beyond the body on each side.
    """

    equations = [
        "bore_d, belt_width, pitch > 0",
        "pitch_d == teeth * pitch / pi",
        "od == pitch_d + 1.5",
        "flange_d == od + 2.0",
        "flange_h == 1.0",
    ]
