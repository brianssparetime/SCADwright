"""Print joint Components: tab/slot, snap hook, grip tab."""

from __future__ import annotations

from scadwright.boolops import union
from scadwright.component.base import Component
from scadwright.extrusions import linear_extrude
from scadwright.primitives import cube, polyhedron, square


class TabSlot(Component):
    """Finger joint tab-and-slot pair.

    The Component itself emits the tab (positive). For the matching
    slot cutter, read the ``.slot`` property — a cube sized to ``tab + clearance``
    that you position at the receiving part and subtract:

        tab = TabSlot(tab_w=5, tab_h=3, tab_d=10, clearance=0.2)
        wall = difference(wall, tab.slot.translate([x, y, z]).through(wall))

    ``tab_w``, ``tab_h``, ``tab_d`` are the tab dimensions; ``clearance``
    adds play around the slot for print tolerance. Slot dimensions are
    published as ``slot_w``, ``slot_h``, ``slot_d``.
    """

    equations = [
        "tab_w, tab_h, tab_d, clearance > 0",
        "slot_w == tab_w + 2 * clearance",
        "slot_h == tab_h + clearance",
        "slot_d == tab_d + 2 * clearance",
    ]

    def build(self):
        return cube([self.tab_w, self.tab_d, self.tab_h], center="xy")

    @property
    def slot(self):
        """Cutter cube sized for the matching slot, centered on the origin in xy."""
        return cube([self.slot_w, self.slot_d, self.slot_h], center="xy")


class SnapHook(Component):
    """Cantilever snap-fit hook with a ramped barb.

    A vertical arm with a triangular barb on its +Y face near the top.
    The barb has a flat catch (bottom face, perpendicular to the arm)
    that grips a ledge, and a slanted ramp (top face) that deflects the
    arm during insertion.

    Arm: z=[0, arm_length], x=[-width/2, +width/2], y=[0, thk].
    Barb: on the +Y face at the top; catch at z=arm_length-hook_height,
    ramp terminating at z=arm_length, tip protruding to y=thk+hook_depth.

    A 45° ramp (typical) is ``hook_height == hook_depth``.
    """

    equations = [
        "arm_length, hook_depth, hook_height, thk, width > 0",
        "hook_height <= arm_length",
    ]

    def build(self):
        arm = cube([self.width, self.thk, self.arm_length], center="x")

        # Triangular barb: prism with catch (bottom), ramp (slanted),
        # and back face coincident with the arm's front. Small overlap
        # into the arm (0.01) keeps the union manifold-clean.
        y_back = self.thk - 0.01
        y_tip = self.thk + self.hook_depth
        z_bot = self.arm_length - self.hook_height
        z_top = self.arm_length
        x = self.width / 2
        vertices = [
            (-x, y_back, z_bot),   # 0 L back-bottom (catch level, at arm front)
            (-x, y_tip, z_bot),    # 1 L tip (catch edge)
            (-x, y_back, z_top),   # 2 L back-top (ramp terminus)
            (+x, y_back, z_bot),   # 3 R back-bottom
            (+x, y_tip, z_bot),    # 4 R tip
            (+x, y_back, z_top),   # 5 R back-top
        ]
        faces = [
            [0, 2, 1],        # left triangle (normal -x)
            [3, 4, 5],        # right triangle (normal +x)
            [0, 1, 4, 3],     # catch (bottom, normal -z)
            [1, 2, 5, 4],     # ramp (slanted, normal toward +y+z)
            [0, 3, 5, 2],     # back (overlaps into arm, normal -y)
        ]
        barb = polyhedron(points=vertices, faces=faces)
        return union(arm, barb)


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
