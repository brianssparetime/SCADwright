"""Aluminum extrusion profile Components (2D, extrudable)."""

from __future__ import annotations

from scadwright.boolops import difference, union
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import circle, square


class ExtrusionProfile(Component):
    """2020/2040-style aluminum extrusion cross-section (2D).

    Generates a simplified T-slot extrusion profile centered on the
    origin. ``size`` is the profile width in mm (20, 30, or 40 for
    standard sizes). ``slots`` controls how many T-slot channels to
    include per side (1 for 2020, 2 for 2040 on the long axis).

    Extrude for a 3D rail::

        ExtrusionProfile(size=20).linear_extrude(height=200)
    """

    equations = ["size > 0"]
    slots = Param(int, default=1)

    def build(self):
        s = self.size
        half = s / 2

        # Outer square.
        body = square([s, s], center=True)

        # Center bore.
        bore_d = s * 0.22
        bore = circle(d=bore_d)

        # T-slot channels on each face.
        slot_w = s * 0.26
        slot_depth = s * 0.25
        slot_opening = s * 0.14

        cutters = [bore]
        for face in range(4):
            angle = face * 90
            for slot_idx in range(self.slots):
                if self.slots == 1:
                    offset = 0
                else:
                    offset = (slot_idx - (self.slots - 1) / 2) * (s / self.slots)

                # T-shaped slot: narrow opening + wider interior.
                opening = square([slot_opening, slot_depth], center=True)
                opening = opening.translate([0, half - slot_depth / 2, 0])
                interior = square([slot_w, slot_depth * 0.6], center=True)
                interior = interior.translate([0, half - slot_depth, 0])

                slot = union(opening, interior)
                if offset != 0:
                    slot = slot.translate([offset, 0, 0])
                slot = slot.rotate([0, 0, angle])
                cutters.append(slot)

        return difference(body, union(*cutters))
