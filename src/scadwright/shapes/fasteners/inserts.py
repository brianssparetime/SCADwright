"""Heat-set insert pocket and captive nut pocket Components."""

from __future__ import annotations

from scadwright.boolops import union
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cube, cylinder
from scadwright.shapes.fasteners.data import (
    InsertSpec, NutSpec, get_insert_spec, get_nut_spec,
)
from scadwright.shapes.two_d import regular_polygon


class HeatSetPocket(Component):
    """Pocket sized for a common brass heat-set insert.

    Specify ``spec=InsertSpec(...)`` for custom sizes, or use
    ``HeatSetPocket.of("M3")`` for canned datasheet dimensions. The
    pocket is a cylinder starting at z=0, extending upward. Subtract
    from a parent to create the pocket.

    Publishes ``hole_d`` and ``hole_depth`` for downstream sizing.
    """

    spec = Param(InsertSpec)
    equations = [
        "hole_d = spec.hole_d",
        "hole_depth = spec.hole_depth",
    ]

    @classmethod
    def of(cls, size: str, **kwargs):
        """Build a HeatSetPocket from an ISO size string (e.g. ``"M3"``)."""
        return cls(spec=get_insert_spec(size), **kwargs)

    def build(self):
        return cylinder(h=self.hole_depth, d=self.hole_d)


class CaptiveNutPocket(Component):
    """Hex pocket with insertion channel for a captive nut.

    Specify ``spec=NutSpec(...)`` for custom, or ``CaptiveNutPocket.of("M3", depth=3)``
    for canned ISO sizes. The pocket is a hex hole with a rectangular
    insertion slot on one side. Centered on the origin at z=0.

    ``channel_axis`` controls which direction the insertion slot
    extends: ``"x"`` (default) or ``"y"``.

    Publishes ``af`` (across-flats) for downstream sizing.
    """

    spec = Param(NutSpec)
    equations = [
        "depth > 0",
        "af = spec.af",
    ]
    channel_axis = Param(str, default="x", one_of=("x", "y"))

    @classmethod
    def of(cls, size: str, **kwargs):
        """Build a CaptiveNutPocket from an ISO size string (e.g. ``"M3"``)."""
        return cls(spec=get_nut_spec(size), **kwargs)

    def build(self):
        hex_pocket = regular_polygon(sides=6, r=self.af / 2).linear_extrude(
            height=self.depth
        )
        # Insertion channel: a rectangle extending outward from the hex.
        channel_length = self.af  # extend one full nut-width outward
        if self.channel_axis == "x":
            channel = cube([channel_length, self.af, self.depth]).translate(
                [self.af / 2, -self.af / 2, 0]
            )
        else:
            channel = cube([self.af, channel_length, self.depth]).translate(
                [-self.af / 2, self.af / 2, 0]
            )
        return union(hex_pocket, channel)
