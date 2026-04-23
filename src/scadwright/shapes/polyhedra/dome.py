"""Dome (hemisphere) and SphericalCap Components."""

from __future__ import annotations

from scadwright.boolops import difference, intersection
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cylinder, sphere


class Dome(Component):
    """Hemisphere with optional wall thickness, flat face on z=0.

    Solid dome when ``thk`` is not provided. Hollow shell when ``thk``
    is given (the inner sphere has radius ``r - thk``).
    """

    equations = [
        "r > 0",
        "?thk > 0",
        "?thk < r",
    ]

    def build(self):
        # Full sphere clipped to z >= 0.
        clip = cylinder(h=self.r + 1, r=self.r + 1)
        outer = intersection(sphere(r=self.r), clip)
        if self.thk is None:
            return outer
        inner_r = self.r - self.thk
        inner = intersection(sphere(r=inner_r), clip)
        return difference(outer, inner)


class SphericalCap(Component):
    """A portion of a sphere sliced off by a plane.

    The cap sits with its flat face on z=0 and the dome rising in +z.
    Four dimensional parameters linked by two equations; specify any
    two and the framework solves the rest::

        SphericalCap(sphere_r=20, cap_height=8)
        SphericalCap(cap_dia=30, cap_height=5)
    """

    equations = [
        "cap_r == cap_dia / 2",
        "cap_r**2 == cap_height * (2 * sphere_r - cap_height)",
        "cap_height, cap_dia, cap_r, sphere_r > 0",
        "cap_height <= 2 * sphere_r",
    ]

    def build(self):
        s = sphere(r=self.sphere_r).up(self.sphere_r - self.cap_height)
        clip = cylinder(h=self.cap_height, r=self.sphere_r + 0.01)
        return intersection(s, clip)
