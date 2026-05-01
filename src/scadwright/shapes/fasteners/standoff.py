"""Standoff (PCB mount post) Component."""

from __future__ import annotations

from scadwright.component.base import Component
from scadwright.component.anchors import anchor
from scadwright.shapes.three_d import Tube


class Standoff(Component):
    """Screw-mount standoff column.

    A hollow cylinder centered on the origin, base on z=0. Publishes
    a ``mount_top`` anchor at the top face for attaching mounted parts.
    """

    equations = "od, id, h > 0"

    mount_top = anchor(at="0, 0, h", normal=(0, 0, 1))

    def build(self):
        return Tube(h=self.h, od=self.od, id=self.id)
