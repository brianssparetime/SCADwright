"""Fillet and chamfer mask Components for subtracting along edges."""

from __future__ import annotations

import math

from scadwright.boolops import difference
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cube, cylinder


class FilletMask(Component):
    """Quarter-cylinder fillet piece for axis-aligned edges.

    The shape is an ``r`` x ``r`` x ``length`` prism with a quarter-
    cylinder of radius ``r`` removed along its edge. The same geometry
    serves two uses depending on how you combine it with a parent:

    - **Round an outside (convex) edge** by subtracting: place along
      the edge and ``difference()`` — the result is a rounded transition
      where the sharp corner was.
    - **Fill an inside (concave) corner** by unioning: place in the
      corner and ``union()`` — the quarter-cylinder curve becomes a
      smooth tangent between the two walls, relieving stress at the
      re-entrant corner.

    ``axis`` is the edge direction: ``"x"``, ``"y"``, or ``"z"``.
    ``length`` is the extent along that axis.
    """

    equations = """
        r, length > 0
        ?axis:str = ?axis or "z"
        axis in ("x", "y", "z")
    """

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

        # Pin the through() axis to the edge direction. Auto-detection
        # otherwise picks x (or y) because the cutter is 2r wide vs the
        # r-wide block — but that lateral overlap is geometric design
        # (the quarter-cylinder is tangent to the block's outer faces),
        # not a coincident face that needs extending. Extending along x
        # turns the cutter into an ellipse and breaks the tangency,
        # leaving a hair-thin sliver where the fillet meets the parent.
        return difference(block, cutter.through(block, axis=ax))

    def tight_bbox(self):
        # The cutter carves out a quarter-cylinder from inside the
        # block; outer extents = the block's bbox.
        from scadwright.bbox import bbox
        return bbox(self)


class ChamferMask(Component):
    """Subtractable chamfer mask along an axis-aligned edge.

    Place along an edge and subtract to chamfer it. The mask is a
    triangular prism (45-degree chamfer).

    ``axis`` is the edge direction: ``"x"``, ``"y"``, or ``"z"``.
    ``length`` is the extent along that axis. ``size`` is the chamfer
    depth (distance removed from each face of the edge).
    """

    equations = """
        size, length > 0
        ?axis:str = ?axis or "z"
        axis in ("x", "y", "z")
    """

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

        # Same reasoning as FilletMask: pin to the edge axis so through()
        # extends along the edge, not laterally where the rotated cutter
        # is wider than the block by design.
        return difference(block, cutter.through(block, axis=ax))

    def tight_bbox(self):
        # The cutter chamfers one corner of the block; outer extents
        # = the block's bbox.
        from scadwright.bbox import bbox
        return bbox(self)
