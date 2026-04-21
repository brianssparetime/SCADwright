"""Countersink and Counterbore Components for screw holes."""

from __future__ import annotations

from scadwright.boolops import union
from scadwright.component.base import Component
from scadwright.primitives import cylinder
from scadwright.shapes.fasteners.data import get_screw_spec


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


def counterbore_for_screw(
    size: str, shaft_depth: float, *, head: str = "socket"
) -> Counterbore:
    """Counterbore sized for a standard ISO metric screw of ``size``.

    Pulls clearance_d, head_d, and head_h from the ScrewSpec for the
    given size and head style. Use ``.through(parent)`` for clean cuts.
    """
    spec = get_screw_spec(size, head)
    return Counterbore(
        shaft_d=spec.clearance_d,
        head_d=spec.head_d,
        head_depth=spec.head_h,
        shaft_depth=shaft_depth,
    )


def countersink_for_screw(
    size: str, shaft_depth: float, *, head: str = "socket"
) -> Countersink:
    """Countersink sized for a standard ISO metric screw of ``size``.

    The cone diameter matches the screw's head_d; the shaft matches
    its clearance_d. Use ``.through(parent)`` for clean cuts.
    """
    spec = get_screw_spec(size, head)
    return Countersink(
        shaft_d=spec.clearance_d,
        head_d=spec.head_d,
        head_depth=spec.head_h,
        shaft_depth=shaft_depth,
    )
