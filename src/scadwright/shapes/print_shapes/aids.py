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
    fix for drilled-fit holes on FDM prints.

    ``sides`` (default 8) is the polygon count for the cutter; it also
    pins the cutter's ``$fn`` so the compensation isn't undone by a
    higher ambient resolution. ``circumradius`` is published.

    Subtract like any cutter — ``through(parent)`` still works.
    """

    equations = [
        "circumradius == (d / 2) / cos(pi / sides)",
        "d, h > 0",
    ]
    sides = Param(int, min=3, default=8)

    def build(self):
        return cylinder(h=self.h, r=self.circumradius, fn=self.sides)
