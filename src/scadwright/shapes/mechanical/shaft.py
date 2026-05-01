"""Shaft profile Components (2D, extrudable)."""

from __future__ import annotations


from scadwright.boolops import difference
from scadwright.component.base import Component
from scadwright.primitives import circle, square


class DShaft(Component):
    """D-shaped shaft cross-section (2D).

    A circle with a flat cut on one side. ``d`` is the shaft diameter,
    ``flat_depth`` is how deep the flat cuts into the circle (measured
    from the circle edge inward). Centered on the origin.

    Extrude for a 3D shaft::

        DShaft(d=5, flat_depth=0.5).linear_extrude(height=20)
    """

    equations = "d, flat_depth > 0"

    def build(self):
        r = self.d / 2
        shaft = circle(d=self.d)
        # Flat: remove a strip from one side.
        cut_x = r - self.flat_depth
        cutter = square([self.d, self.d], center=True).right(cut_x + self.d / 2)
        return difference(shaft, cutter)


class KeyedShaft(Component):
    """Shaft cross-section with a keyway slot (2D).

    A circle with a rectangular keyway cut. ``d`` is the shaft diameter,
    ``key_w`` and ``key_h`` are the keyway width and depth. Centered on
    the origin; keyway is on the +x side.

    Extrude for a 3D shaft::

        KeyedShaft(d=10, key_w=3, key_h=1.5).linear_extrude(height=30)
    """

    equations = "d, key_w, key_h > 0"

    def build(self):
        r = self.d / 2
        shaft = circle(d=self.d)
        keyway = square([self.key_w, self.key_h + r]).translate(
            [-self.key_w / 2, r - self.key_h, 0]
        )
        return difference(shaft, keyway)
