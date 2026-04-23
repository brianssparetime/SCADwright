"""Hex and square nut Components."""

from __future__ import annotations

from scadwright.boolops import difference
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cube, cylinder
from scadwright.shapes.fasteners.data import NutSpec, get_nut_spec
from scadwright.shapes.two_d import regular_polygon


class HexNut(Component):
    """ISO metric hex nut.

    Specify ``spec=NutSpec(d=, af=, h=)`` for custom sizes, or use the
    ``HexNut.of("M3")`` classmethod for canned ISO sizes. Dimensions
    from ISO 4032. Centered on the origin, flat faces on z=0 and z=h.

    Publishes ``af`` (across-flats), ``h`` (height), ``d`` (bore) for
    convenient dimension access.
    """

    spec = Param(NutSpec)
    equations = [
        "af = spec.af",
        "h = spec.h",
        "d = spec.d",
    ]

    @classmethod
    def of(cls, size: str, **kwargs):
        """Build a HexNut from an ISO size string (e.g. ``"M3"``)."""
        return cls(spec=get_nut_spec(size), **kwargs)

    def build(self):
        hex_profile = regular_polygon(sides=6, r=self.af / 2)
        outer = hex_profile.linear_extrude(height=self.h)
        hole = cylinder(h=self.h, d=self.d).through(outer)
        return difference(outer, hole)


class SquareNut(Component):
    """Square nut (DIN 562 style).

    Specify ``spec=NutSpec(...)`` for custom, or ``SquareNut.of("M3")``
    for canned ISO sizes (uses the same across-flats dimension as the
    hex nut for that size, but square cross-section).

    Publishes ``af`` (across-flats / side length), ``h`` (height),
    ``d`` (bore).
    """

    spec = Param(NutSpec)
    equations = [
        "af = spec.af",
        "h = spec.h",
        "d = spec.d",
    ]

    @classmethod
    def of(cls, size: str, **kwargs):
        """Build a SquareNut from an ISO size string (e.g. ``"M3"``)."""
        return cls(spec=get_nut_spec(size), **kwargs)

    def build(self):
        outer = cube([self.af, self.af, self.h], center="xy")
        hole = cylinder(h=self.h, d=self.d).through(outer)
        return difference(outer, hole)
