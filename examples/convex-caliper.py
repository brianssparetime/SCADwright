"""Convex caliper: a worked example of equation-driven geometry.

Defines a SphericalCap Component inline to demonstrate the equation
solver (the same Component is available pre-made from the shape library
as ``from scadwright.shapes import SphericalCap``).

A spherical cap is the portion of a sphere sliced off by a plane.  Six
parameters describe it — cap_height, cap_dia, cap_r, sphere_dia,
sphere_r, and slice_ratio — linked by four equations.  Specify any two
and the framework solves the rest:

    SphericalCap(sphere_r=20, cap_height=8)
    SphericalCap(cap_dia=30, slice_ratio=0.25)
    SphericalCap(sphere_dia=50, cap_r=12)

Run:
    python examples/convex-caliper.py
"""

from scadwright import Component, Param
from scadwright.boolops import intersection, union
from scadwright.design import Design, run, variant
from scadwright.primitives import cylinder, sphere
from scadwright.shapes import UShapeChannel

EPS = 0.01


class SphericalCap(Component):
    """A portion of a sphere sliced off by a plane.

    Note: this Component is available pre-made from the shape library
    as ``from scadwright.shapes import SphericalCap``. It is defined here
    inline as a worked example of equation-driven geometry.

    The cap sits with its flat face on z=0 and the dome rising in +z.
    Six dimensional Params with four equations; specify any two and the
    framework solves the remaining four.
    """

    equations = [
        "cap_r == cap_dia / 2",
        "sphere_r == sphere_dia / 2",
        "cap_r**2 == cap_height * (2 * sphere_r - cap_height)",
        "slice_ratio == cap_height**2 * (3 * sphere_r - cap_height) / (4 * sphere_r**3)",
        "cap_height, cap_dia, cap_r, sphere_dia, sphere_r, slice_ratio > 0",
    ]

    def setup(self):                                    # framework hook: runs after Params are set
        if self.cap_height > 2 * self.sphere_r:
            raise ValueError(
                f"cap_height ({self.cap_height}) cannot exceed the sphere "
                f"diameter ({2 * self.sphere_r})"
            )

    def build(self):                                    # framework hook: returns the shape
        s = sphere(r=self.sphere_r).translate(
            [0, 0, self.sphere_r - self.cap_height],
        )
        clip = cylinder(
            h=self.cap_height,
            r=self.sphere_r + EPS,
        )
        return intersection(s, clip)



#  CONCRETE SECTION

prong_length = 30
prong_width = 2.6
prong_height = 10
wall_thk = 3

feeler_length = 30
cap_height = 5

MyU = UShapeChannel(wall_thk=wall_thk,
                    channel_length=prong_length,
                    channel_width=prong_width,
                    channel_height=prong_height,
                    n_shape=True,
                    center="xy")

cyl_h = feeler_length - cap_height - prong_height
cyl = cylinder(r=MyU.bottom_width / 2, h=cyl_h).attach(MyU)
MyCap = SphericalCap(cap_dia=MyU.bottom_width, cap_height=cap_height).attach(cyl)

part = union(MyU, cyl, MyCap)


# =============================================================================
# DESIGN: layout variants
# =============================================================================


class ConvexCaliper(Design):

    @variant(fn=48, default=False)
    def display(self):                                  # user-chosen variant name
        return part

    @variant(fn=48, default=True)
    def print(self):                                    # user-chosen variant name
        print_space = 10
        print_offset = print_space + MyU.outer_width / 2
        return union(part.right(print_offset), part.left(print_offset))


if __name__ == "__main__":
    run()
