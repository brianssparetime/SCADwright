"""Enclosure: box with a snap-on lid. Chamfered bottom edges, rounded
vertical corners, centering lip, and 4 corner screws into pylons.

Demonstrates:
- Equations relating outer/inner dimensions so the user specifies
  whichever they have and the framework solves the rest.
- Cross-component dimension sharing: the `Lid` takes a `Box` instance
  as a Param and reads `box.outer_w`, `box.pylon_positions`, etc.
- A custom transform `.chamfer_top(c=...)`.
- Generator-style `build()`.

Run:
    python examples/box-and-lid.py
    scadwright build examples/box-and-lid.py --variant=display
"""

from collections import namedtuple

from scadwright import Component, Param, bbox
from scadwright.boolops import difference, hull, intersection, union
from scadwright.design import Design, run, variant
from scadwright.primitives import cube, cylinder
from scadwright.shapes import RoundedBox, Tube, rounded_rect
from scadwright.transforms import transform


# =============================================================================
# GLOBALS
# =============================================================================

EPS = 0.01


# =============================================================================
# REUSABLE: custom transform + fastener spec
# =============================================================================


@transform("chamfer_top", inline=True)
def chamfer_top(node, *, c):
    """Chamfer the +z edges of a shape by `c` at 45 deg, using its bbox."""
    b = bbox(node)
    w, l, _ = b.size
    cx, cy, _ = b.center
    big = max(w, l) + 10.0
    bot = cube([big, big, EPS]).translate([cx - big / 2, cy - big / 2, b.min[2] - 0.5])
    mid_top = cube([w, l, EPS]).translate([cx - w / 2, cy - l / 2, b.max[2] - c])
    top = cube([w - 2 * c, l - 2 * c, EPS]).translate(
        [cx - (w - 2 * c) / 2, cy - (l - 2 * c) / 2, b.max[2]]
    )
    return intersection(node, hull(bot, mid_top, top))


ScrewSpec = namedtuple("ScrewSpec", "d head_d head_depth")
M3 = ScrewSpec(d=3.2, head_d=6.0, head_depth=1.8)


# =============================================================================
# REUSABLE: generic box + lid Components
# =============================================================================


class Box(Component):
    """Open-top box with chamfered bottom edges, rounded vertical corners,
    a centering lip at the rim, and four corner screw pylons.

    Publishes outer dimensions and pylon positions so a mating Lid can
    read them directly.
    """

    equations = [
        "inner_w == outer_w - 2 * wall_thk",
        "inner_l == outer_l - 2 * wall_thk",
        "inner_h == height - floor_thk",
        "outer_w, outer_l, inner_w, inner_l, inner_h > 0",
        "wall_thk, floor_thk, height, pylon_od, corner_inset > 0",
        "corner_r, chamfer, lip_height, lip_clearance >= 0",
    ]
    screw = Param(ScrewSpec)

    def setup(self):                                       # framework hook: only for cross-Component published values
        self.inner_corner_r = max(self.corner_r - self.wall_thk, 0.5)
        i = self.corner_inset
        self.pylon_positions = tuple(
            (sx * (self.outer_w / 2 - i), sy * (self.outer_l / 2 - i))
            for sx in (+1, -1) for sy in (+1, -1)
        )

    def build(self):                                       # framework hook: required; returns the shape
        w, l, h = self.outer_w, self.outer_l, self.height
        r, c = self.corner_r, self.chamfer

        def slab(sw, sl, z):
            return rounded_rect(sw, sl, r=r).linear_extrude(height=EPS).up(z)

        # Outer shell: chamfered bottom, straight top (the top is open
        # and has a lip, so it needs a clean vertical rim).
        if c > 0:
            outer = hull(
                slab(w - 2 * c, l - 2 * c, 0),
                slab(w, l, c),
                slab(w, l, h - EPS),
            )
        else:
            outer = rounded_rect(w, l, r=r).linear_extrude(height=h)

        # Inner cavity: straight walls, no chamfer.
        ir = self.inner_corner_r
        inner = (
            rounded_rect(self.inner_w, self.inner_l, r=ir)
            .linear_extrude(height=h)
            .up(self.floor_thk)
        )
        yield difference(outer, inner)

        # Screw pylons rising from the floor.
        pylon_h = h - self.floor_thk - 0.5
        for px, py in self.pylon_positions:
            yield (
                Tube(h=pylon_h, od=self.pylon_od, id=self.screw.d)
                .chamfer_top(c=0.8)
                .translate([px, py, self.floor_thk])
            )

        # Centering lip at the rim.
        if self.lip_height > 0:
            lc = self.lip_clearance
            lip_r = max(self.inner_corner_r - lc, 0.5)
            lip = (
                rounded_rect(self.inner_w - 2 * lc, self.inner_l - 2 * lc, r=lip_r)
                .linear_extrude(height=self.lip_height)
                .up(h - EPS)
            )
            yield lip


class Lid(Component):
    """Cover sized to mate on top of a Box. Chamfered top edges, with an
    underside cavity that receives the box's centering lip. Screw holes
    at the pylon positions with countersunk heads.

    Reads all mating dimensions off the Box instance.
    """

    box = Param(Box)
    equations = ["height > 0"]

    def build(self):                                       # framework hook: required; returns the shape
        b = self.box
        w, l, h = b.outer_w, b.outer_l, self.height
        r, c = b.corner_r, b.chamfer

        def slab(sw, sl, z):
            return rounded_rect(sw, sl, r=r).linear_extrude(height=EPS).up(z)

        # Outer shell: straight bottom rim (mates against box), chamfered top.
        if c > 0:
            outer = hull(
                slab(w, l, 0),
                slab(w, l, h - c),
                slab(w - 2 * c, l - 2 * c, h - EPS),
            )
        else:
            outer = rounded_rect(w, l, r=r).linear_extrude(height=h)

        # Underside cavity to receive the box's lip.
        if b.lip_height > 0:
            lc = b.lip_clearance
            cavity_w = b.inner_w - 2 * lc + 2 * lc   # same as inner_w: lip fits inside
            cavity_l = b.inner_l - 2 * lc + 2 * lc
            cavity_r = b.inner_corner_r
            cavity = (
                rounded_rect(cavity_w, cavity_l, r=cavity_r)
                .linear_extrude(height=b.lip_height + EPS)
                .down(EPS)
            )
            outer = difference(outer, cavity)

        # Screw holes aligned with box pylons.
        s = b.screw
        cutters = []
        for px, py in b.pylon_positions:
            # Through-shaft.
            cutters.append(
                cylinder(h=h + 2, d=s.d).translate([px, py, -1])
            )
            # Countersunk head bore from the top.
            cutters.append(
                cylinder(h=s.head_depth + EPS, d=s.head_d)
                .translate([px, py, h - s.head_depth])
            )

        return difference(outer, *cutters)


# =============================================================================
# CONCRETE: the design being built
# =============================================================================


class MyBox(Box):
    outer_w = 60
    outer_l = 40
    height = 40
    corner_r = 4
    chamfer = 2
    wall_thk = 2.5
    floor_thk = 2.5
    pylon_od = 7
    screw = M3
    corner_inset = 8
    lip_height = 2
    lip_clearance = 0.3


class MyLid(Lid):
    height = 10


# =============================================================================
# DESIGN: shared parts + variant methods
# =============================================================================


class BoxAndLid(Design):
    box = MyBox()
    lid = MyLid(box=box)

    @variant(fn=48, default=True)
    def print(self):
        return union(
            self.box,
            self.lid.flip("z").up(self.lid.height).right(self.box.outer_w + 15),
        )

    @variant(fn=48)
    def display(self):
        # Lid floats one lid-height above the box so the box's centering
        # lip is visible between them.
        return union(
            self.box,
            self.lid.up(self.box.height + self.lid.height),
        )


if __name__ == "__main__":
    run()
