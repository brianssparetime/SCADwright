"""Hex and square nut Components."""

from __future__ import annotations

from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cube, cylinder
from scadwright.shapes.fasteners.data import get_nut_spec
from scadwright.shapes.two_d import regular_polygon


class HexNut(Component):
    """ISO metric hex nut.

    Specify ``size`` (e.g. ``"M3"``). Dimensions from ISO 4032.
    Centered on the origin, flat faces on z=0 and z=h.
    """

    size = Param(str)

    def setup(self):                                    # framework hook: optional
        spec = get_nut_spec(self.size)
        self._spec = spec
        self.af = spec.af
        self.h = spec.h
        self.d = spec.d

    def build(self):
        s = self._spec
        hex_profile = regular_polygon(sides=6, r=s.af / 2)
        outer = hex_profile.linear_extrude(height=s.h)
        hole = cylinder(h=s.h, d=s.d).through(outer)
        from scadwright.boolops import difference
        return difference(outer, hole)


class SquareNut(Component):
    """Square nut (DIN 562 style).

    Specify ``size`` (e.g. ``"M3"``). Uses the same across-flats
    dimension as the hex nut for that size, but square cross-section.
    """

    size = Param(str)

    def setup(self):                                    # framework hook: optional
        spec = get_nut_spec(self.size)
        self._spec = spec
        self.af = spec.af
        self.h = spec.h
        self.d = spec.d

    def build(self):
        s = self._spec
        outer = cube([s.af, s.af, s.h], center="xy")
        hole = cylinder(h=s.h, d=s.d).through(outer)
        from scadwright.boolops import difference
        return difference(outer, hole)
