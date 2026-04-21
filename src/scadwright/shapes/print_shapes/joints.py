"""Print joint Components: tab/slot, snap hook, grip tab."""

from __future__ import annotations

from scadwright.boolops import union
from scadwright.component.base import Component
from scadwright.primitives import cube


class TabSlot(Component):
    """Finger joint tab-and-slot pair.

    Produces a tab (positive) and slot (negative) that interlock.
    ``tab_w``, ``tab_h``, ``tab_d`` are the tab dimensions.
    ``clearance`` adds play around the slot for print tolerance.

    The tab sits at z=0 extending upward. The slot is a matching
    cutout (use the ``slot`` attribute to get just the cutter).
    """

    equations = [
        "tab_w, tab_h, tab_d, clearance > 0",
        "slot_w == tab_w + 2 * clearance",
        "slot_h == tab_h + clearance",
        "slot_d == tab_d + 2 * clearance",
    ]

    def build(self):
        return cube([self.tab_w, self.tab_d, self.tab_h], center="xy")


class SnapHook(Component):
    """Cantilever snap-fit hook.

    A vertical arm with a hook at the top. The arm flexes to allow
    the hook to snap over a ledge. ``arm_length`` is the arm height,
    ``hook_depth`` is how far the hook protrudes, ``thk`` is the arm
    thickness, ``width`` is the arm width.

    The hook base sits at z=0, hook at z=arm_length.
    """

    equations = [
        "arm_length, hook_depth, thk, width > 0",
    ]

    def build(self):
        arm = cube([self.width, self.thk, self.arm_length], center="x")
        hook = cube([self.width, self.hook_depth + self.thk, self.thk], center="x")
        hook = hook.up(self.arm_length)
        return union(arm, hook)


class GripTab(Component):
    """Tab for joining two separately-printed parts.

    A rectangular tab with tapered sides for press-fit grip. One part
    gets the tab (positive), the other gets a matching pocket (negative,
    with clearance). The tab sits at z=0.

    ``taper`` is the per-side taper amount (the tab is wider at the
    base than the tip by 2*taper).
    """

    equations = ["tab_w, tab_h, tab_d, taper >= 0"]

    def build(self):
        # Simple rectangular tab; taper is applied as a slight scale.
        if self.taper <= 0:
            return cube([self.tab_w, self.tab_d, self.tab_h], center="xy")

        from scadwright.extrusions import linear_extrude
        from scadwright.primitives import square

        base = square([self.tab_w + 2 * self.taper, self.tab_d], center=True)
        scale = self.tab_w / (self.tab_w + 2 * self.taper)
        return linear_extrude(base, height=self.tab_h, scale=scale)
