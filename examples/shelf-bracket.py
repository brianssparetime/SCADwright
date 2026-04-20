"""Triangular shelf-support bracket, designed specifically to showcase
scadwright's equation-solving feature.

The bracket is a right-triangular gusset mounted to a wall. Its
geometry is fully described by four mutually-constrained values:

    rise   — length of the vertical arm (on the wall)
    run    — length of the horizontal arm (supporting the shelf)
    hyp    — length of the diagonal strut
    angle  — base angle at the corner, between horizontal and diagonal

These four are related by two equations (pythagorean + trigonometric).
With four variables and two equations, the user specifies any two and
the framework solves the remaining two. Three equivalent ways to call it:

    TriangularBracket(run=120, angle=30, thk=4)       # I want a 120mm-deep shelf at 30 deg
    TriangularBracket(rise=60, run=120, thk=4)        # I have a 60mm wall and 120mm shelf
    TriangularBracket(hyp=140, angle=45, thk=4)       # I have a 140mm diagonal strut at 45 deg

Also shows:
- Published component dimensions feeding a Design that uses them to
  position wall-mount and shelf screw holes.
- Multi-instantiation: a few brackets in one scene with different
  concrete sizes, to visualize how the equation-driven geometry adapts.
- Concrete subclasses per common shelf size.

Run:
    python examples/shelf-bracket.py
    scadwright build examples/shelf-bracket.py --variant=display
"""

from math import cos, radians, sin

from scadwright import Component, Param
from scadwright.boolops import difference, union
from scadwright.design import Design, run, variant
from scadwright.primitives import cube, cylinder, polygon
from scadwright.transforms import transform


# =============================================================================
# GLOBALS
# =============================================================================

EPS = 0.01


# =============================================================================
# REUSABLE: bracket Component + custom verb
# =============================================================================


@transform("mount_hole", inline=True)
def mount_hole(node, *, at, d, length=200):
    """Drill a through-hole at 2D position `at` along the node's z-axis."""
    x, y = at
    return difference(
        node,
        cylinder(h=length, d=d, center=True).translate([x, y, 0]),
    )


class TriangularBracket(Component):
    """Right-triangular gusset bracket. Four dimensional Params (rise,
    run, hyp, angle) with two equations; specify any two and the
    framework solves the rest.

    Geometry is a 2D right triangle extruded along z by `thk`. The
    vertical arm goes up from the origin; the horizontal arm goes out
    along +x; the diagonal strut closes the triangle.
    """

    equations = [
        "rise**2 + run**2 == hyp**2",
        "rise == run * tan(angle * pi / 180)",
        "rise, run, hyp, angle, thk, mount_hole_d, mount_inset > 0",
    ]
    n_wall_holes = Param(int, positive=True)
    n_shelf_holes = Param(int, positive=True)

    def setup(self):                                       # framework hook: optional, runs after Params are set
        usable = self.rise - 2 * self.mount_inset
        if self.n_wall_holes == 1:
            ys = [self.rise / 2]
        else:
            step = usable / (self.n_wall_holes - 1)
            ys = [self.mount_inset + i * step for i in range(self.n_wall_holes)]
        self.wall_hole_positions = tuple((-self.thk / 2 - EPS, y) for y in ys)

        usable = self.run - 2 * self.mount_inset
        if self.n_shelf_holes == 1:
            xs = [self.run / 2]
        else:
            step = usable / (self.n_shelf_holes - 1)
            xs = [self.mount_inset + i * step for i in range(self.n_shelf_holes)]
        self.shelf_hole_positions = tuple((x, self.rise + self.thk / 2 + EPS) for x in xs)

    def build(self):                                       # framework hook: required; returns the shape
        profile = polygon(points=[
            (0, 0),
            (self.run, 0),
            (0, self.rise),
        ])
        bracket = profile.linear_extrude(height=self.thk)
        bracket = bracket.rotate([90, 0, 0]).translate([0, self.thk, 0])

        wall_holes = union(*[
            cylinder(h=self.thk * 3, d=self.mount_hole_d, center=True)
                .rotate([90, 0, 0])
                .translate([EPS, self.thk / 2, y])
            for (_, y) in self.wall_hole_positions
        ])
        shelf_holes = union(*[
            cylinder(h=self.rise, d=self.mount_hole_d)
                .translate([x, self.thk / 2, self.rise - self.thk])
            for (x, _) in self.shelf_hole_positions
        ])

        return difference(bracket, wall_holes, shelf_holes)


# =============================================================================
# CONCRETE: a few bracket sizes for this project
# =============================================================================


class ShelfBracket120(TriangularBracket):
    run = 120.0
    angle = 30.0
    thk = 5.0
    mount_hole_d = 4.5
    mount_inset = 8.0
    n_wall_holes = 3
    n_shelf_holes = 2


class DeepBracket(TriangularBracket):
    rise = 80.0
    run = 160.0
    thk = 6.0
    mount_hole_d = 4.5
    mount_inset = 10.0
    n_wall_holes = 3
    n_shelf_holes = 2


class CornerBracket(TriangularBracket):
    hyp = 100.0
    angle = 45.0
    thk = 4.0
    mount_hole_d = 3.5
    mount_inset = 6.0
    n_wall_holes = 2
    n_shelf_holes = 2


# =============================================================================
# DESIGN: three brackets laid out to show equation-driven variety
# =============================================================================


class BracketSet(Design):
    a = ShelfBracket120()
    b = DeepBracket()
    c = CornerBracket()

    @variant(fn=32, default=True)
    def print(self):
        return union(
            self.a,
            self.b.right(self.a.run + 20),
            self.c.right(self.a.run + self.b.run + 40),
        )

    @variant(fn=32)
    def display(self):
        return union(
            self.a,
            self.b.right(self.a.run + 30),
            self.c.right(self.a.run + self.b.run + 60),
        )


if __name__ == "__main__":
    run()
