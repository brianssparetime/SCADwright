"""Enclosure: box with a snap-on lid. Chamfered bottom edges, rounded
vertical corners, centering lip, and 4 corner screws into pylons.

Equations relate outer and inner dimensions so the user specifies
whichever they have and the solver fills in the rest. The `Lid` takes
a `Box` as a parameter and reads its dimensions directly. `build()`
uses `yield` lines to emit each part separately.

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
# REUSABLE: custom transform + fastener spec
# =============================================================================


@transform("chamfer_top", inline=True)
def chamfer_top(node, *, c):
    """Chamfer the +z edges of a shape by `c` at 45 deg, using its bbox.

    The three infinitesimally-thin slabs fed into `hull()` define the
    ideal chamfered volume; `eps` is layer-thickness, not overlap EPS,
    so through() doesn't apply here.
    """
    eps = 0.01
    b = bbox(node)
    w, l, _ = b.size
    cx, cy, _ = b.center
    big = max(w, l) + 10.0
    bot = cube([big, big, eps]).translate([cx - big / 2, cy - big / 2, b.min[2] - 0.5])
    mid_top = cube([w, l, eps]).translate([cx - w / 2, cy - l / 2, b.max[2] - c])
    top = cube([w - 2 * c, l - 2 * c, eps]).translate(
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

    A mating `Lid` can read the outer dimensions and pylon positions
    off this Box directly.
    """

    screw = Param(ScrewSpec)
    equations = """
        inner_w = outer_w - 2 * wall_thk
        inner_l = outer_l - 2 * wall_thk
        inner_h = height - floor_thk
        outer_w, outer_l, inner_w, inner_l, inner_h > 0
        wall_thk, floor_thk, height, pylon_od, corner_inset, lip_thk > 0
        corner_r, chamfer, lip_height, lip_clearance >= 0
        lip_thk < wall_thk
        inner_corner_r = max(corner_r - wall_thk, 0.5)
        pylon_positions = tuple(
            (sx * (outer_w / 2 - corner_inset), sy * (outer_l / 2 - corner_inset))
            for sx in (+1, -1) for sy in (+1, -1)
        )
    """

    def build(self):                                       # framework hook: required; returns the shape
        # Local EPS for the hull-slab trick (layer thickness, not coplanar
        # overlap) and for fusing the lip to the wall top.
        eps = 0.01
        w, l, h = self.outer_w, self.outer_l, self.height
        r, c = self.corner_r, self.chamfer

        def slab(sw, sl, z):
            return rounded_rect(sw, sl, r=r).linear_extrude(height=eps).up(z)

        # Outer shell: chamfered bottom, straight top (the top is open
        # and has a lip, so it needs a clean vertical rim).
        if c > 0:
            outer = hull(
                slab(w - 2 * c, l - 2 * c, 0),
                slab(w, l, c),
                slab(w, l, h - eps),
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

        # Centering lip: a hollow rectangular frame rising from the inner
        # edge of the wall. Its outer footprint matches the inner cavity
        # (inner_w x inner_l), so it's fused to the wall rather than
        # floating over the opening. A matching recess in the lid captures
        # it with `lip_clearance` slack, keeping the lid from sliding.
        if self.lip_height > 0:
            ir = self.inner_corner_r
            solid = (
                rounded_rect(self.inner_w, self.inner_l, r=ir)
                .linear_extrude(height=self.lip_height)
            )
            hole = (
                rounded_rect(
                    self.inner_w - 2 * self.lip_thk,
                    self.inner_l - 2 * self.lip_thk,
                    r=max(ir - self.lip_thk, 0.5),
                )
                .linear_extrude(height=self.lip_height)
                .through(solid)
            )
            yield difference(solid, hole).up(h - eps)


class Lid(Component):
    """Cover sized to mate on top of a Box. Chamfered top edges, with an
    underside cavity that receives the box's centering lip. Screw holes
    at the pylon positions with countersunk heads.

    Reads all mating dimensions off the Box instance.
    """

    box = Param(Box)
    equations = "height > 0"

    def build(self):                                       # framework hook: required; returns the shape
        # Local EPS for the hull-slab trick (layer thickness, not coplanar overlap).
        eps = 0.01
        b = self.box
        w, l, h = b.outer_w, b.outer_l, self.height
        r, c = b.corner_r, b.chamfer

        def slab(sw, sl, z):
            return rounded_rect(sw, sl, r=r).linear_extrude(height=eps).up(z)

        # Outer shell: straight bottom rim (mates against box), chamfered top.
        if c > 0:
            outer = hull(
                slab(w, l, 0),
                slab(w, l, h - c),
                slab(w - 2 * c, l - 2 * c, h - eps),
            )
        else:
            outer = rounded_rect(w, l, r=r).linear_extrude(height=h)

        # Underside recess sized to capture the box's lip with lip_clearance
        # slack all around.
        if b.lip_height > 0:
            lc = b.lip_clearance
            cavity = (
                rounded_rect(
                    b.inner_w + 2 * lc,
                    b.inner_l + 2 * lc,
                    r=b.inner_corner_r + lc,
                )
                .linear_extrude(height=b.lip_height)
                .through(outer, axis="z")
            )
            outer = difference(outer, cavity)

        # Screw holes aligned with box pylons.
        s = b.screw
        cutters = []
        for px, py in b.pylon_positions:
            # Through-shaft; .through() extends past both top and bottom faces.
            cutters.append(
                cylinder(h=h, d=s.d).translate([px, py, 0]).through(outer, axis="z")
            )
            # Countersunk head bore from the top face.
            cutters.append(
                cylinder(h=s.head_depth, d=s.head_d)
                .translate([px, py, h - s.head_depth])
                .through(outer, axis="z")
            )

        return difference(outer, *cutters).add_text(
            label="LID", relief=0.5, on="top", font_size=12,
        )


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
    lip_thk = 1.2
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
