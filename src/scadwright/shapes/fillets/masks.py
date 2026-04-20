"""Fillet and chamfer mask Components for subtracting along edges."""

from __future__ import annotations

import math

from scadwright.boolops import difference
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.errors import ValidationError
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
    axis = Param(str, default="z")

    def setup(self):
        if self.axis.lower() not in ("x", "y", "z"):
            raise ValidationError(
                f"FilletMask: axis must be 'x', 'y', or 'z', got {self.axis!r}"
            )

    def build(self):
        r = self.r
        ax = self.axis.lower()

        if ax == "z":
            block = cube([r, r, self.length])
            cutter = cylinder(h=self.length + 0.02, r=r).translate([r, r, -0.01])
        elif ax == "x":
            block = cube([self.length, r, r])
            cutter = cylinder(h=self.length + 0.02, r=r).rotate([0, 90, 0]).translate([-0.01, r, r])
        else:  # y
            block = cube([r, self.length, r])
            cutter = cylinder(h=self.length + 0.02, r=r).rotate([90, 0, 0]).translate([r, self.length + 0.01, r])

        return difference(block, cutter)


class ChamferMask(Component):
    """Subtractable chamfer mask along an axis-aligned edge.

    Place along an edge and subtract to chamfer it. The mask is a
    triangular prism (45-degree chamfer).

    ``axis`` is the edge direction: ``"x"``, ``"y"``, or ``"z"``.
    ``length`` is the extent along that axis. ``size`` is the chamfer
    depth (distance removed from each face of the edge).
    """

    equations = ["size, length > 0"]
    axis = Param(str, default="z")

    def setup(self):
        if self.axis.lower() not in ("x", "y", "z"):
            raise ValidationError(
                f"ChamferMask: axis must be 'x', 'y', or 'z', got {self.axis!r}"
            )

    def build(self):
        s = self.size
        ax = self.axis.lower()

        # Build a triangular prism by subtracting a rotated cube from a
        # square cross-section block.
        if ax == "z":
            block = cube([s, s, self.length])
            # Diagonal cut: rotate a cube 45 degrees.
            diag = s * math.sqrt(2)
            cutter = cube([diag, diag, self.length + 0.02]).rotate([0, 0, 45]).translate([0, 0, -0.01])
        elif ax == "x":
            block = cube([self.length, s, s])
            diag = s * math.sqrt(2)
            cutter = cube([self.length + 0.02, diag, diag]).rotate([45, 0, 0]).translate([-0.01, 0, 0])
        else:  # y
            block = cube([s, self.length, s])
            diag = s * math.sqrt(2)
            cutter = cube([diag, self.length + 0.02, diag]).rotate([0, 45, 0]).translate([0, -0.01, 0])

        return difference(block, cutter)
