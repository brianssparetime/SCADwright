"""FDM print aids: shapes that compensate for print-process artifacts."""

from __future__ import annotations

from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cylinder


class PolyHole(Component):
    """Laird-compensated polygonal hole cutter.

    OpenSCAD approximates a circle with an n-gon, so a ``cylinder(d=d)``
    used as a hole prints to an *inscribed* diameter strictly less than
    ``d``. ``PolyHole`` scales the polygon's circumradius so the
    inscribed circle matches the requested ``d`` exactly — the standard
    fix for drilled-fit holes on FDM prints. ``self.d`` is therefore the
    as-printed inscribed diameter (the effective hole size); the larger
    ``self.circumradius`` is the polygon circumradius used internally.

    ``sides`` is the polygon count for the cutter; it also pins the
    cutter's ``$fn`` so the compensation isn't undone by a higher
    ambient resolution. Typical FDM values are 6 or 8.

    Subtract like any cutter — ``through(parent)`` still works.
    """

    equations = [
        "circumradius = (d / 2) / cos(pi / sides)",
        "d, h > 0",
    ]
    sides = Param(int, min=3)

    def build(self):
        return cylinder(h=self.h, r=self.circumradius, fn=self.sides)
