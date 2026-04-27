"""Ring gear (internal gear) Component."""

from __future__ import annotations

from scadwright.boolops import difference
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.extrusions import linear_extrude
from scadwright.primitives import circle
from scadwright.shapes.gears.involute import spur_profile


class RingGear(Component):
    """Internal (ring) gear: teeth on the inside of a ring.

    Meshes with a spur gear of the same module and pressure angle.
    ``rim_thk`` is the wall thickness outside the tooth roots.
    """

    equations = [
        "module, h, rim_thk > 0",
        "pressure_angle > 0",
        "pressure_angle <= 45",
        "pitch_r = module * teeth / 2",
        "base_r = pitch_r * cos(pressure_angle * pi / 180)",
        "outer_r = pitch_r + module",
        "root_r = pitch_r - 1.25 * module",
    ]
    teeth = Param(int, min=12)
    # ISO 4033 convention — almost every gear-cutting application uses 20°;
    # 14.5° is a legacy carryover, 25° is a niche high-strength variant.
    pressure_angle = Param(float, default=20.0)

    def build(self):
        # The ring gear is a disc with the spur gear profile subtracted.
        outer_d = 2 * (self.outer_r + self.rim_thk)
        gear_profile = spur_profile(self.module, self.teeth, self.pressure_angle)
        ring = circle(d=outer_d)
        return linear_extrude(difference(ring, gear_profile), height=self.h)
