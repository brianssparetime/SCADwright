"""Wall-mount coat hook: plate + J-hook assembled via named anchors.

Both Components declare named anchors on the class. The Design joins
them with `attach(parent, on=..., using_anchor=...)`, which picks
a specific anchor on each side. The plate offers two anchors (one for
the hook, one for future use); the hook offers `base` on the stem
axis. A tenon at the bottom of the stem drops into a matching socket
on the plate, keying the parts together.

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
    """Rectangular wall mounting plate with two countersunk screw holes,
    a center socket that receives the hook's tenon, and a front-face
    anchor where an accessory attaches."""

    equations = """
        w, h, thk, corner_r, screw_d, screw_head_d, screw_head_depth > 0
        mount_d, mount_depth > 0
        screw_d < screw_head_d
        screw_head_depth < thk
        mount_depth < thk
    """

    # Front-face anchor at the plate's center, pointing +Z. A hook, peg,
    # holder, or other accessory attaches here with its own -Z base anchor.
    hook_mount = anchor(at="0, 0, thk", normal=(0, 0, 1))

    # A second anchor, not used by this example but available for future
    # subclasses. A decorative cap or cable clip could attach along the top
    # edge without rewriting `WallPlate`.
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
        # Blind socket at the center of the plate's top face. The hook's
        # tenon drops into this hole on assembly, keying the two parts
        # together so the bend resists rotation as well as pull-out.
        cutters.append(
            cylinder(h=self.mount_depth, d=self.mount_d)
                .up(self.thk - self.mount_depth)
        )
        return difference(slab, *cutters)


class JHook(Component):
    """A J-hook with a tenon stub at the base: vertical stem, quarter-torus
    elbow, perpendicular tip. The tenon plugs into a matching socket in
    the wall plate."""

    equations = """
        stem_d, stem_len, tip_len, elbow_r, tenon_len > 0
        elbow_r > stem_d / 2                              # bend must clear the tube's inner edge
    """

    # Base of the stem at the top of the tenon. The tenon extends below
    # z=0; the visible stem starts at z=0 and rises to z=stem_len. -Z
    # normal so attach() mates cleanly with a +Z face anchor on the parent.
    base = anchor(at="0, 0, 0", normal=(0, 0, -1))

    def build(self):                                       # framework hook: required; returns the shape
        R = self.elbow_r
        # Stem extends below z=0 by `tenon_len`; that lower stub seats
        # inside the plate's socket when the parts are assembled.
        stem = (
            cylinder(h=self.stem_len + self.tenon_len, d=self.stem_d)
            .down(self.tenon_len)
        )
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
    mount_d = 6                 # matches MyJHook.stem_d
    mount_depth = 2.5


class MyJHook(JHook):
    stem_d = 6
    stem_len = 25
    tip_len = 18
    elbow_r = 8
    tenon_len = 2.5             # matches MyWallPlate.mount_depth


# =============================================================================
# DESIGN
# =============================================================================


class CoatHook(Design):
    plate = MyWallPlate()
    hook = MyJHook()

    @variant(fn=48, default=True)
    def display(self):                                  # user-chosen variant name
        # Both anchors are named: `on="hook_mount"` picks the plate's
        # mounting anchor, `using_anchor="base"` picks the hook's own
        # base anchor (at the stem axis, not the bbox center). The
        # plate's normal is +Z and the hook's `base` is -Z, so the
        # default `attach()` behavior (opposing normals) needs no
        # `orient=True`. `bond="shift"` adds an eps overlap by shifting
        # the hook into the plate — the regular `fuse=True` overlap
        # path needs the anchor on the outermost face, and the tenon
        # sits below the base anchor.
        return union(
            self.plate,
            self.hook.attach(self.plate, on="hook_mount", using_anchor="base", bond="shift"),
        )

    @variant(fn=48)
    def print(self):                                    # user-chosen variant name
        # Plate's back face already sits at z=0. Lay the hook on its side
        # and place it clear of the plate with a visible gap, so the two
        # parts read as separate prints rather than an assembled hook
        # sticking off the edge.
        plate_bb = bbox(self.plate)
        laid_hook = self.hook.rotate([90, 0, 0])
        hook_min_x = bbox(laid_hook).min[0]
        gap = 15
        return union(
            self.plate,
            laid_hook.right(plate_bb.max[0] + gap - hook_min_x),
        )


if __name__ == "__main__":
    run()
