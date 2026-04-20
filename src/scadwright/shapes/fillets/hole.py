"""Countersink and Counterbore Components for screw holes."""

from __future__ import annotations

from scadwright.boolops import union
from scadwright.component.base import Component
from scadwright.primitives import cylinder


class Countersink(Component):
    """Conical countersink profile for flat-head screws.

    Produces a cone + shaft cylinder, suitable for subtracting from a
    parent. The cone sits at z=0 opening downward (into the part);
    the shaft extends upward.

    Use ``.through(parent)`` to auto-extend for clean cuts.
    """

    equations = [
        "shaft_d, head_d, head_depth, shaft_depth > 0",
    ]

    def build(self):
        shaft = cylinder(h=self.shaft_depth, d=self.shaft_d)
        cone = cylinder(
            h=self.head_depth,
            r1=self.head_d / 2,
            r2=self.shaft_d / 2,
        ).up(self.shaft_depth)
        return union(shaft, cone)


class Counterbore(Component):
    """Cylindrical counterbore profile for socket-head screws.

    Produces a stepped cylinder: narrow shaft + wider bore. The shaft
    starts at z=0; the bore sits on top.

    Use ``.through(parent)`` to auto-extend for clean cuts.
    """

    equations = [
        "shaft_d, head_d, head_depth, shaft_depth > 0",
    ]

    def build(self):
        shaft = cylinder(h=self.shaft_depth, d=self.shaft_d)
        bore = cylinder(h=self.head_depth, d=self.head_d).up(self.shaft_depth)
        return union(shaft, bore)
