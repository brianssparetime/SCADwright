"""Wall-mount coat hook: plate + J-hook assembled via named anchors.

Demonstrates class-scope `anchor()` on reusable Components, and
`attach(parent, face="anchor_name", fuse=True)` picking a specific
mount point on the parent. The plate publishes two anchors (one for
the hook, one for future extensibility) and the hook publishes one
(its attachment base) so the Design's `attach()` call reads like
plain English.

Run:
    python examples/wall-hook.py                     # display variant (default)
    scadwright build examples/wall-hook.py --variant=print
"""

from scadwright import Component, anchor, bbox
from scadwright.boolops import difference, union
from scadwright.design import Design, run, variant
from scadwright.primitives import cylinder
from scadwright.shapes import Torus, rounded_rect


# =============================================================================
# REUSABLE: generic wall plate + J-hook
# =============================================================================


class WallPlate(Component):
    """Rectangular wall mounting plate with two countersunk screw holes
    and a front-face anchor where an accessory attaches."""

    equations = [
        "w, h, thk, corner_r, screw_d, screw_head_d, screw_head_depth > 0",
        "screw_d < screw_head_d",
        "screw_head_depth < thk",
    ]

    # Front-face anchor at the plate's center, pointing +Z. A hook, peg,
    # holder, or other accessory attaches here with its own -Z base anchor.
    hook_mount = anchor(at="0, 0, thk", normal=(0, 0, 1))

    # A second anchor published purely for extensibility -- unused by this
    # example. A future subclass could attach a decorative cap or a cable
    # clip along the top edge without rewriting `WallPlate`.
    top_edge = anchor(at="0, h/2, thk/2", normal=(0, 1, 0))

    def build(self):                                       # framework hook: required; returns the shape
        slab = rounded_rect(self.w, self.h, r=self.corner_r).linear_extrude(height=self.thk)
        screw_y = self.h / 2 - 2 * self.corner_r
        cutters = []
        for y in (+screw_y, -screw_y):
            cutters.append(
                cylinder(h=self.thk, d=self.screw_d)
                    .forward(y)
                    .through(slab, axis="z")
            )
            cutters.append(
                cylinder(h=self.screw_head_depth, d=self.screw_head_d)
                    .translate([0, y, self.thk - self.screw_head_depth])
                    .through(slab, axis="z")
            )
        return difference(slab, *cutters)


class JHook(Component):
    """A J-hook: vertical stem, quarter-torus elbow, perpendicular tip."""

    equations = [
        "stem_d, stem_len, tip_len, elbow_r > 0",
        "elbow_r > stem_d / 2",                           # bend must clear the tube's inner edge
    ]

    # Base of the stem, pointing -Z so attach() mates cleanly with a +Z
    # face anchor on the parent.
    base = anchor(at="0, 0, 0", normal=(0, 0, -1))

    def build(self):                                       # framework hook: required; returns the shape
        R = self.elbow_r
        stem = cylinder(h=self.stem_len, d=self.stem_d)
        # Quarter-torus elbow: Torus natively sweeps in the XY plane, so
        # rotate it into the XZ plane and translate so its "stem" end lands
        # at the top of the stem.
        elbow = (
            Torus(major_r=R, minor_r=self.stem_d / 2, angle=90)
            .rotate([90, 0, 0])
            .translate([-R, 0, self.stem_len])
        )
        # Tip continues the elbow's outgoing tangent (-X direction) from the
        # far end of the bend.
        tip = (
            cylinder(h=self.tip_len, d=self.stem_d)
            .rotate([0, -90, 0])
            .translate([-R, 0, self.stem_len + R])
        )
        return union(stem, elbow, tip)


# =============================================================================
# CONCRETE: a small coat-hook-sized design
# =============================================================================


class MyWallPlate(WallPlate):
    w = 40
    h = 80
    thk = 4
    corner_r = 4
    screw_d = 4
    screw_head_d = 8
    screw_head_depth = 2.0


class MyJHook(JHook):
    stem_d = 6
    stem_len = 25
    tip_len = 18
    elbow_r = 8


# =============================================================================
# DESIGN
# =============================================================================


class CoatHook(Design):
    plate = MyWallPlate()
    hook = MyJHook()

    @variant(fn=48, default=True)
    def display(self):                                  # user-chosen variant name
        # Hook attaches at the plate's `hook_mount` anchor. The plate's
        # anchor normal is +Z and the hook's `base` normal is -Z, so the
        # default `attach()` behavior (opposing normals) needs no
        # `orient=True`; it just places the hook's origin at the plate's
        # anchor point.
        return union(
            self.plate,
            self.hook.attach(self.plate, face="hook_mount", fuse=True),
        )

    @variant(fn=48)
    def print(self):                                    # user-chosen variant name
        # Plate's back face already sits at z=0. Lay the hook on its side
        # (stem along -Y, tip along +X) and place it to the right of the
        # plate so both parts print together.
        plate_w = bbox(self.plate).size[0]
        return union(
            self.plate,
            self.hook.rotate([90, 0, 0]).right(plate_w / 2 + 20),
        )


if __name__ == "__main__":
    run()
