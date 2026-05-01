"""Torus Component."""

from __future__ import annotations

from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.extrusions import rotate_extrude
from scadwright.primitives import circle


class Torus(Component):
    """Torus (donut) centered on the origin in the XY plane.

    ``major_r`` is the distance from the center of the torus to the
    center of the tube. ``minor_r`` is the tube radius. Optional
    ``angle`` sweeps a partial torus (default 360 for a full ring).
    """

    equations = """
        major_r, minor_r > 0
        ?angle = ?angle or 360.0
        angle > 0
        angle <= 360
        minor_r < major_r
    """

    def build(self):
        cross = circle(r=self.minor_r).right(self.major_r)
        return rotate_extrude(cross, angle=self.angle)
