"""Heat-set insert pocket and captive nut pocket Components."""

from __future__ import annotations

from scadwright.boolops import union
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cube, cylinder
from scadwright.shapes.fasteners.data import get_insert_spec, get_nut_spec


class HeatSetPocket(Component):
    """Pocket sized for a common brass heat-set insert.

    Specify ``size`` (e.g. ``"M3"``). Dimensions from common insert
    datasheets. The pocket is a cylinder starting at z=0, extending
    upward. Subtract from a parent to create the pocket.
    """

    size = Param(str)

    def setup(self):                                    # framework hook: optional
        spec = get_insert_spec(self.size)
        self._spec = spec
        self.hole_d = spec.hole_d
        self.hole_depth = spec.hole_depth

    def build(self):
        return cylinder(h=self._spec.hole_depth, d=self._spec.hole_d)


class CaptiveNutPocket(Component):
    """Hex pocket with insertion channel for a captive nut.

    Specify ``size`` (e.g. ``"M3"``) and ``depth`` (pocket depth into
    the part). The pocket is a hex hole with a rectangular insertion
    slot on one side. Centered on the origin at z=0.

    ``channel_axis`` controls which direction the insertion slot
    extends: ``"x"`` (default) or ``"y"``.
    """

    size = Param(str)
    equations = ["depth > 0"]
    channel_axis = Param(str, default="x")

    def setup(self):                                    # framework hook: optional
        spec = get_nut_spec(self.size)
        self._spec = spec
        self.af = spec.af

    def build(self):
        from scadwright.shapes.two_d import regular_polygon

        s = self._spec
        hex_pocket = regular_polygon(sides=6, r=s.af / 2).linear_extrude(
            height=self.depth
        )
        # Insertion channel: a rectangle extending outward from the hex.
        channel_length = s.af  # extend one full nut-width outward
        if self.channel_axis == "x":
            channel = cube([channel_length, s.af, self.depth]).translate(
                [s.af / 2, -s.af / 2, 0]
            )
        else:
            channel = cube([s.af, channel_length, self.depth]).translate(
                [-s.af / 2, s.af / 2, 0]
            )
        return union(hex_pocket, channel)
