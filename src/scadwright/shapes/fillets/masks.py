"""Fillet and chamfer mask Components for subtracting along edges."""

from __future__ import annotations

import math

from scadwright.boolops import difference
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cube, cylinder


class FilletMask(Component):
    """Subtractable fillet mask along an axis-aligned edge.

    Place along an edge and subtract to round it. The mask is a cube
    with a cylindrical quarter removed, producing a concave fillet when
    subtracted from a parent.

    ``axis`` is the edge direction: ``"x"``, ``"y"``, or ``"z"``.
    ``length`` is the extent along that axis.
    """

    equations = ["r, length > 0"]
    axis = Param(str, default="z", one_of=("x", "y", "z"))

    def build(self):
        r = self.r
        ax = self.axis

        if ax == "z":
            block = cube([r, r, self.length])
            cutter = cylinder(h=self.length, r=r).translate([r, r, 0])
        elif ax == "x":
            block = cube([self.length, r, r])
            cutter = cylinder(h=self.length, r=r).rotate([0, 90, 0]).translate([0, r, r])
        else:  # y
            block = cube([r, self.length, r])
            cutter = cylinder(h=self.length, r=r).rotate([90, 0, 0]).translate([r, self.length, r])

        return difference(block, cutter.through(block))


class ChamferMask(Component):
    """Subtractable chamfer mask along an axis-aligned edge.

    Place along an edge and subtract to chamfer it. The mask is a
    triangular prism (45-degree chamfer).

    ``axis`` is the edge direction: ``"x"``, ``"y"``, or ``"z"``.
    ``length`` is the extent along that axis. ``size`` is the chamfer
    depth (distance removed from each face of the edge).
    """

    equations = ["size, length > 0"]
    axis = Param(str, default="z", one_of=("x", "y", "z"))

    def build(self):
        s = self.size
        ax = self.axis

        # Build a triangular prism by subtracting a rotated cube from a
        # square cross-section block.
        diag = s * math.sqrt(2)
        if ax == "z":
            block = cube([s, s, self.length])
            # Diagonal cut: rotate a cube 45 degrees.
            cutter = cube([diag, diag, self.length]).rotate([0, 0, 45])
        elif ax == "x":
            block = cube([self.length, s, s])
            cutter = cube([self.length, diag, diag]).rotate([45, 0, 0])
        else:  # y
            block = cube([s, self.length, s])
            cutter = cube([diag, self.length, diag]).rotate([0, 45, 0])

        return difference(block, cutter.through(block))
