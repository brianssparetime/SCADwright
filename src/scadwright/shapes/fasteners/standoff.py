"""Standoff (PCB mount post) Component."""

from __future__ import annotations

from scadwright.boolops import difference, union
from scadwright.component.base import Component
from scadwright.component.anchors import anchor
from scadwright.primitives import cylinder


class Standoff(Component):
    """Screw-mount standoff column with optional base flange.

    A hollow cylinder (the post) with an optional wider base disc.
    Centered on the origin, base on z=0.
    """

    equations = [
        "od, id, h > 0",
    ]

    mount_top = anchor(at="0, 0, h", normal=(0, 0, 1))

    def build(self):
        post = difference(
            cylinder(h=self.h, d=self.od),
            cylinder(h=self.h + 0.02, d=self.id).down(0.01),
        )
        return post
