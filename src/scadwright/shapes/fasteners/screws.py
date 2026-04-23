"""Bolt Component and clearance/tap hole factories."""

from __future__ import annotations

from scadwright.boolops import union
from scadwright.component.base import Component
from scadwright.component.anchors import anchor
from scadwright.component.params import Param
from scadwright.primitives import cylinder
from scadwright.shapes.fasteners.data import get_screw_spec
from scadwright.shapes.two_d import regular_polygon


class Bolt(Component):
    """ISO metric bolt with head and shaft.

    Specify ``size`` (e.g. ``"M3"``) and ``length`` (shaft length).
    ``head`` selects the head style: ``"socket"`` (default) or
    ``"button"``. Thread geometry is smooth (no helical threads);
    use ThreadedRod for actual thread profiles.

    The bolt stands upright with the head at the top (+z) and the
    shaft extending downward.
    """

    size = Param(str)
    equations = ["length > 0"]
    head = Param(str, default="socket")

    tip = anchor(at=(0, 0, 0), normal=(0, 0, -1))

    def build(self):
        s = get_screw_spec(self.size, self.head)
        shaft = cylinder(h=self.length, d=s.d)
        # Head: hex profile extruded for socket head, cylinder for button.
        if self.head == "socket":
            head = regular_polygon(sides=6, r=s.head_d / 2).linear_extrude(
                height=s.head_h
            )
        else:
            head = cylinder(h=s.head_h, d=s.head_d)
        head = head.up(self.length)
        return union(shaft, head)


def clearance_hole(size: str, depth: float, *, head: str = "socket"):
    """Return a cylinder sized as a clearance hole for the given screw size.

    The cylinder starts at z=0 and extends upward by ``depth``.
    Use ``.through(parent)`` for clean cuts.
    """
    spec = get_screw_spec(size, head)
    return cylinder(h=depth, d=spec.clearance_d)


def tap_hole(size: str, depth: float, *, head: str = "socket"):
    """Return a cylinder sized as a tap drill hole for the given screw size.

    The cylinder starts at z=0 and extends upward by ``depth``.
    """
    spec = get_screw_spec(size, head)
    return cylinder(h=depth, d=spec.tap_d)
