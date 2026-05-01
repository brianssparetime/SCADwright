"""Finger-joint Components: TabSlot, GripTab."""

from __future__ import annotations

from scadwright.component.base import Component
from scadwright.extrusions import linear_extrude
from scadwright.primitives import cube, square


class TabSlot(Component):
    """Finger joint tab-and-slot pair.

    The Component itself emits the tab (positive). For the matching
    slot cutter, read the ``.slot`` property — a cube sized to ``tab + clearance``
    that you position at the receiving part and subtract:

        tab = TabSlot(tab_w=5, tab_h=3, tab_d=10)
        wall = difference(wall, tab.slot.translate([x, y, z]).through(wall))

    ``tab_w``, ``tab_h``, ``tab_d`` are the tab dimensions; ``clearance``
    adds play around the slot for print tolerance. If not passed,
    ``clearance`` resolves from the active scope (``with clearances(...)``,
    Design/Component class attrs, or ``DEFAULT_CLEARANCES.finger``).
    Slot dimensions are available on the instance as ``slot_w``,
    ``slot_h``, ``slot_d``.
    """

    _clearance_category = "finger"

    equations = """
        tab_w, tab_h, tab_d, clearance > 0
        slot_w = tab_w + 2 * clearance
        slot_h = tab_h + clearance
        slot_d = tab_d + 2 * clearance
    """

    def build(self):
        return cube([self.tab_w, self.tab_d, self.tab_h], center="xy")

    @property
    def slot(self):
        """Cutter cube sized for the matching slot, centered on the origin in xy."""
        return cube([self.slot_w, self.slot_d, self.slot_h], center="xy")


class GripTab(Component):
    """Tab for joining two separately-printed parts.

    A rectangular tab with tapered sides for press-fit grip. One part
    gets the tab (positive), the other gets a matching pocket (negative,
    with clearance). The tab sits at z=0.

    ``taper`` is the per-side taper amount (the tab is wider at the
    base than the tip by 2*taper).
    """

    equations = "tab_w, tab_h, tab_d, taper >= 0"

    def build(self):
        # Tapered (or straight, when taper == 0) prism via linear_extrude
        # with a scaled top. base_w is wider than tab_w by 2*taper at z=0;
        # the top scales down to tab_w. With taper=0 this collapses to a
        # plain rectangular prism.
        base_w = self.tab_w + 2 * self.taper
        scale = self.tab_w / base_w
        return linear_extrude(
            square([base_w, self.tab_d], center=True),
            height=self.tab_h,
            scale=scale,
        )
