"""Parametric battery holder: a desk tray with N cradles for cylindrical
cells, sized to a given battery spec.

A `BatterySpec` namedtuple carries one battery's dimensions. Lines in
`equations` compute the tray's pitch, outer dimensions, and cradle
positions directly from the spec, plus a rule that checks the tray
isn't deeper than the battery is long. A custom transform cuts one
finger slot per cradle. Per-battery concrete subclasses fill in the
rest of the dimensions.

Run:
    python examples/battery-holder.py
    scadwright build examples/battery-holder.py --variant=display
"""

from collections import namedtuple

from scadwright import Component, Param
from scadwright.boolops import difference, union
from scadwright.design import Design, run, variant
from scadwright.primitives import cylinder
from scadwright.shapes import RoundedSlot, Tube, rounded_rect
from scadwright.transforms import transform


# =============================================================================
# REUSABLE: battery spec, custom verb, generic holder
# =============================================================================


BatterySpec = namedtuple("BatterySpec", "d length label")

AAA     = BatterySpec(d=10.5, length=44.5, label="AAA")
AA      = BatterySpec(d=14.5, length=50.5, label="AA")
C_CELL  = BatterySpec(d=26.2, length=50.0, label="C")
D_CELL  = BatterySpec(d=34.2, length=61.5, label="D")
_18650  = BatterySpec(d=18.5, length=65.0, label="18650")
CR123A  = BatterySpec(d=17.0, length=34.5, label="CR123A")


@transform("finger_scoop", inline=True)
def finger_scoop(node, *, at_x, tray_y, slot_w, slot_h, slot_depth, slot_top_z):
    """Cut a vertical rounded-slot finger window through an outer wall,
    aligned with the battery's long axis, so the user can see the cell
    and pinch it out from the side.

    The cutter is a `RoundedSlot` (capsule) extruded normal to the wall.
    Its long axis runs along z (the battery axis); its short axis runs
    along x. It spans from `slot_top_z - slot_h` up to `slot_top_z`.

    For the window to actually expose the cell, `slot_depth` must exceed
    the wall thickness between the cradle well and the outer wall
    (`wall_thk + side_clearance` in the holder below) with a few mm of
    margin to read as a visible cutout rather than a shallow notch.

    `at_x` is the cradle's x-position (the slot is centered on it).
    `tray_y` is the outer-wall y-coordinate (the surface to notch).
    `slot_w` / `slot_h` are the slot's width (x) and height (z).
    `slot_depth` is penetration into the tray, measured from `tray_y`
    inward. `slot_top_z` is the z-coordinate of the slot's top cap.
    """
    cutter = (
        RoundedSlot(length=slot_h, width=slot_w)
        .linear_extrude(height=slot_depth)
        .rotate([-90, -90, 0])  # local (length=X, width=Y, depth=Z) → world (width=X, depth=Y, length=Z)
        .translate([at_x, tray_y, slot_top_z - slot_h / 2])
        .through(node, axis="y")
    )
    return difference(node, cutter)


class BatteryHolder(Component):
    """Open-top tray with N cradle wells sized to a single battery spec.
    Each well is a cylindrical pocket sunk into a rounded-corner tray."""

    spec = Param(BatterySpec)
    equations = """
        count:int > 0
        wall_thk, clearance, end_clearance, side_clearance, floor_thk, tray_depth, scoop_width, scoop_height, scoop_depth > 0
        corner_r >= 0
        tray_depth > floor_thk
        tray_depth < spec.length
        pitch = spec.d + 2 * (clearance + wall_thk)
        outer_w = count * pitch + 2 * end_clearance
        outer_l = pitch + 2 * side_clearance
        cradle_positions = tuple(-(count - 1) * pitch / 2 + i * pitch for i in range(count))
    """

    def build(self):                                       # framework hook: required; returns the shape
        body = rounded_rect(self.outer_w, self.outer_l, r=self.corner_r).linear_extrude(height=self.tray_depth)

        well_d = self.spec.d + 2 * self.clearance
        wells = union(*[
            cylinder(h=self.tray_depth - self.floor_thk, d=well_d)
                .translate([x, 0, self.floor_thk])
                .through(body)
            for x in self.cradle_positions
        ])

        carved = difference(body, wells)

        for x in self.cradle_positions:
            carved = carved.finger_scoop(
                at_x=x, tray_y=-self.outer_l / 2,
                slot_w=self.scoop_width, slot_h=self.scoop_height,
                slot_depth=self.scoop_depth,
                slot_top_z=self.tray_depth - self.wall_thk,
            )
        return carved


def _battery_stand_in(spec: BatterySpec, fn: int = 32):
    """A colored cylinder roughly the size of a real cell, for display
    variants that want to show the holder with its contents."""
    body = Tube(h=spec.length - 2, od=spec.d, thk=0.8, fn=fn)
    return body.color("darkgreen")


# =============================================================================
# CONCRETE: specific holders for this project
# =============================================================================


class AA6Holder(BatteryHolder):
    spec = AA
    count = 6
    wall_thk = 1.6
    clearance = 0.4
    end_clearance = 3.0
    side_clearance = 3.0
    floor_thk = 2.0
    tray_depth = 40.0
    corner_r = 3.0
    scoop_width = 10.0
    scoop_height = 28.0
    scoop_depth = 8.0


class Holder18650x4(BatteryHolder):
    spec = _18650
    count = 4
    wall_thk = 2.0
    clearance = 0.5
    end_clearance = 4.0
    side_clearance = 4.0
    floor_thk = 2.5
    tray_depth = 52.0
    corner_r = 4.0
    scoop_width = 12.0
    scoop_height = 38.0
    scoop_depth = 10.0


# =============================================================================
# DESIGN
# =============================================================================


class BatteryBox(Design):
    holder = AA6Holder()

    @variant(fn=48, default=True)
    def print(self):
        return self.holder

    @variant(fn=48)
    def display(self):
        h = self.holder
        batteries = union(*[
            _battery_stand_in(h.spec).translate([x, 0, h.floor_thk])
            for x in h.cradle_positions
        ])
        return union(h, batteries)


if __name__ == "__main__":
    run()
