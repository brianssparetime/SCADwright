"""2D shape library.

Naming convention:
- lowercase factory functions for simple parametric shapes (rounded_rect, regular_polygon).
- Capitalized Component classes for shapes with non-trivial parameter logic
  or computed attributes worth reading off the instance (Sector, Arc,
  RoundedEndsArc, RoundedSlot).
"""

from __future__ import annotations

import math

from scadwright.boolops import difference, hull, intersection, minkowski, union
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.errors import ValidationError
from scadwright.primitives import circle, polygon, square


# --- factory functions ---


def rounded_rect(x: float, y: float, r: float, *, fn: int | None = None):
    """Rectangle of width x and height y with corners rounded by radius r.

    Implementation: minkowski(square([x-2r, y-2r], center=True), circle(r))
    centered at the origin.
    """
    if r <= 0:
        return square([x, y], center=True)
    inner = square([x - 2 * r, y - 2 * r], center=True)
    return minkowski(inner, circle(r=r, fn=fn))


def rounded_square(size, r: float, *, fn: int | None = None):
    """Square of side `size` (or [w, h]) with rounded corners."""
    if isinstance(size, (int, float)):
        x = y = float(size)
    else:
        x, y = float(size[0]), float(size[1])
    return rounded_rect(x, y, r, fn=fn)


def regular_polygon(sides: int, r: float):
    """Regular n-gon inscribed in radius r, centered at origin, first vertex on +X."""
    if sides < 3:
        raise ValidationError(f"regular_polygon: sides must be >= 3, got {sides}")
    points = [
        (r * math.cos(2 * math.pi * i / sides), r * math.sin(2 * math.pi * i / sides))
        for i in range(sides)
    ]
    return polygon(points=points)


# --- Component-shaped 2D shapes ---


class Sector(Component):
    """Pie slice: a portion of a disc between two angles (degrees).

    Built as `intersection(circle(r), angled_wedge)`. The wedge is a
    straight-sided guard extending past the disc; the curved boundary
    comes from `circle(r)`, which flows `$fn` through the framework
    like any other primitive — no Sector-specific resolution knob.
    """

    equations = """
        r > 0
        len(angles:tuple) = 2                       # (start_deg, end_deg)
    """

    def build(self):
        start, end = float(self.angles[0]), float(self.angles[1])
        if end < start:
            end += 360.0
        ext = self.r * 2  # guard radius: wedge must extend past the disc
        span = end - start
        # Subdivide the wedge into ≤90° chunks so the polygon stays convex.
        n_segs = max(1, int(math.ceil(span / 90)))
        pts = [(0.0, 0.0)]
        for i in range(n_segs + 1):
            t = start + span * i / n_segs
            pts.append((ext * math.cos(math.radians(t)), ext * math.sin(math.radians(t))))
        return intersection(circle(r=self.r), polygon(points=pts))


class Arc(Component):
    """Annular ring segment: a band between r-width/2 and r+width/2 from `angles[0]` to `angles[1]`."""

    equations = """
        inner_r = r - width / 2
        outer_r = r + width / 2
        r, width > 0
        len(angles:tuple) = 2
    """

    def build(self):
        outer = Sector(r=self.outer_r, angles=self.angles)
        if self.inner_r <= 0:
            return outer
        return difference(outer, circle(r=self.inner_r))


class RoundedEndsArc(Component):
    """Arc with rounded (capsule) endpoints."""

    equations = """
        r, width, end_r > 0
        len(angles:tuple) = 2
    """

    def build(self):
        arc = Arc(r=self.r, angles=self.angles, width=self.width)
        start, end = float(self.angles[0]), float(self.angles[1])
        endpoints = []
        for theta in (start, end):
            x = self.r * math.cos(math.radians(theta))
            y = self.r * math.sin(math.radians(theta))
            endpoints.append(
                circle(r=self.end_r).translate([x, y, 0])
            )
        return union(arc, *endpoints)


class RoundedSlot(Component):
    """Capsule / stadium: a rectangle with semicircular caps on the short sides.

    `length` is the total length along the centerline (caps included). `width`
    is the diameter of the caps (and the height of the rectangle).
    """

    equations = """
        radius = width / 2
        length, width > 0
    """

    def build(self):
        r = self.radius
        rect_length = max(0.0, self.length - self.width)
        if rect_length <= 0:
            return circle(r=r)
        rect = square([rect_length, self.width], center=True)
        cap = circle(r=r)
        return union(
            rect,
            cap.right(rect_length / 2),
            cap.left(rect_length / 2),
        )


class Teardrop(Component):
    """FDM-friendly teardrop profile for horizontal holes.

    A circle with a pointed tip at +y, tangent lines rising from the
    circle at ``tip_angle`` above horizontal. The classic printable-
    horizontal-hole shape: for ``tip_angle`` <= 45° every exterior
    surface slopes steeply enough to print unsupported.

    ``cap_h`` optionally truncates the tip with a horizontal cut
    (useful when the remaining point is still unprintable overhead).
    ``tip_height`` is computed at construction from ``r`` and ``tip_angle``.
    """

    # 45° is the canonical FDM-printability threshold: at that slope every
    # overhanging surface is steep enough to print unsupported.
    equations = """
        ?tip_angle = ?tip_angle or 45.0
        tip_height = r / cos(tip_angle)
        r > 0
        tip_angle > 0
        tip_angle < 90
        ?cap_h > r
        ?cap_h < tip_height
    """

    def build(self):
        alpha = math.radians(self.tip_angle)
        # Tangent points where the tip's tangent lines meet the circle.
        tx = self.r * math.sin(alpha)
        ty = self.r * math.cos(alpha)
        cap = polygon(points=[
            (-tx, ty),
            (tx, ty),
            (0.0, self.tip_height),
        ])
        shape = union(circle(r=self.r), cap)
        if self.cap_h is not None:
            # Clip everything above y = cap_h. Rectangle spans from y=-r (bottom
            # of circle) up to y=cap_h, centered on x so tangent-side clipping
            # stays symmetric.
            height = self.cap_h + self.r
            clip = square([3 * self.r, height], center=True).forward(
                (self.cap_h - self.r) / 2
            )
            shape = intersection(shape, clip)
        return shape


class Keyhole(Component):
    """Keyhole profile: circle (head) with a narrower slot extending in -y.

    For wall-hanging mounts: a screw head passes through the head of
    radius ``r_big``, then the part slides down so the shoulder catches
    on the narrower ``r_slot`` slot. ``slot_length`` is the distance from
    the head center to the slot-end cap center.
    """

    equations = """
        r_big, r_slot, slot_length > 0
        r_slot < r_big
    """

    def build(self):
        head = circle(r=self.r_big)
        slot = hull(
            circle(r=self.r_slot),
            circle(r=self.r_slot).back(self.slot_length),
        )
        return union(head, slot)
