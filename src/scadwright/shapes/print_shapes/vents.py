"""Vent slot Component."""

from __future__ import annotations

from scadwright.boolops import difference, union
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cube


class VentSlots(Component):
    """Parametric vent slots: a row of rectangular slots in a panel.

    The panel is ``width`` x ``height`` x ``thk``, centered in XY.
    Slots run horizontally, evenly spaced vertically. Subtract from
    a parent or use standalone.
    """

    equations = [
        "width, height, thk > 0",
        "slot_width, slot_height > 0",
    ]
    slot_count = Param(int, min=1)

    def build(self):
        panel = cube([self.width, self.height, self.thk], center="xy")
        spacing = self.height / (self.slot_count + 1)

        slots = []
        for i in range(self.slot_count):
            y = -self.height / 2 + spacing * (i + 1) - self.slot_height / 2
            slot = cube([self.slot_width, self.slot_height, self.thk])
            slots.append(slot.translate([-self.slot_width / 2, y, 0]))

        return difference(panel, union(*slots).through(panel))
