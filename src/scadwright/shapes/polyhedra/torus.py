"""Torus Component."""

from __future__ import annotations

from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.errors import ValidationError
from scadwright.extrusions import rotate_extrude
from scadwright.primitives import circle


class Torus(Component):
    """Torus (donut) centered on the origin in the XY plane.

    ``major_r`` is the distance from the center of the torus to the
    center of the tube. ``minor_r`` is the tube radius. Optional
    ``angle`` sweeps a partial torus (default 360 for a full ring).
    """

    equations = ["major_r, minor_r > 0"]
    angle = Param(float, default=360.0)

    def setup(self):
        if self.minor_r >= self.major_r:
            raise ValidationError(
                f"Torus: minor_r ({self.minor_r}) must be < major_r ({self.major_r})"
            )
        if not (0 < self.angle <= 360):
            raise ValidationError(
                f"Torus: angle must be in (0, 360], got {self.angle}"
            )

    def build(self):
        cross = circle(r=self.minor_r).right(self.major_r)
        return rotate_extrude(cross, angle=self.angle)
