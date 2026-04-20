"""2D shape library.

Naming convention:
- lowercase factory functions for simple parametric shapes (rounded_rect, regular_polygon).
- Capitalized Component classes for shapes with non-trivial parameter logic
  or multiple useful published attributes (Sector, Arc, RoundedEndsArc, RoundedSlot).
"""

from __future__ import annotations

import math as _m

from scadwright.boolops import difference, intersection, minkowski, union
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
        (r * _m.cos(2 * _m.pi * i / sides), r * _m.sin(2 * _m.pi * i / sides))
        for i in range(sides)
    ]
    return polygon(points=points)


# --- Component-shaped 2D shapes ---


class Sector(Component):
    """Pie slice: a portion of a disc between two angles (degrees).

    Built as `intersection(circle(r), angled_wedge)`.
    """

    equations = ["r > 0"]
    angles = Param(tuple)  # (start_deg, end_deg)

    def build(self):
        start, end = float(self.angles[0]), float(self.angles[1])
        if end < start:
            end += 360.0
        steps = max(2, int(self.fn) if self.fn else 32)
        verts = [(0.0, 0.0)]
        for i in range(steps + 1):
            t = start + (end - start) * (i / steps)
            verts.append((self.r * _m.cos(_m.radians(t)), self.r * _m.sin(_m.radians(t))))
        wedge = polygon(points=verts)
        return intersection(circle(r=self.r), wedge)


class Arc(Component):
    """Annular ring segment: a band between r-width/2 and r+width/2 from `angles[0]` to `angles[1]`."""

    equations = [
        "inner_r == r - width / 2",
        "outer_r == r + width / 2",
        "r, width > 0",
    ]
    angles = Param(tuple)

    def build(self):
        outer = Sector(r=self.outer_r, angles=self.angles)
        if self.inner_r <= 0:
            return outer
        return difference(outer, circle(r=self.inner_r))


class RoundedEndsArc(Component):
    """Arc with rounded (capsule) endpoints."""

    equations = ["r, width, end_r > 0"]
    angles = Param(tuple)

    def build(self):
        arc = Arc(r=self.r, angles=self.angles, width=self.width)
        start, end = float(self.angles[0]), float(self.angles[1])
        endpoints = []
        for theta in (start, end):
            x = self.r * _m.cos(_m.radians(theta))
            y = self.r * _m.sin(_m.radians(theta))
            endpoints.append(
                circle(r=self.end_r).translate([x, y, 0])
            )
        return union(arc, *endpoints)


class RoundedSlot(Component):
    """Capsule / stadium: a rectangle with semicircular caps on the short sides.

    `length` is the total length along the centerline (caps included). `width`
    is the diameter of the caps (and the height of the rectangle).
    """

    equations = [
        "radius == width / 2",
        "length, width > 0",
    ]

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
