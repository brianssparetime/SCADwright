"""3D shape library: Tube, Funnel, RoundedBox, FilletRing, UShapeChannel."""

from __future__ import annotations

from scadwright.boolops import difference, minkowski
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder, sphere


class Tube(Component):
    """Hollow cylinder. Provide h plus any two of (id, od, thk); the third is solved.

    od = outer diameter, id = inner diameter, thk = wall thickness.
    """

    equations = [
        "od == id + 2*thk",
        "h, id, od, thk > 0",
    ]

    def build(self):
        outer = cylinder(h=self.h, r=self.od / 2.0)
        inner = cylinder(h=self.h, r=self.id / 2.0).through(outer)
        return difference(outer, inner)


class Funnel(Component):
    """Tapered tube (truncated cone with wall thickness).

    Provide h and thk, plus one of (bot_id, bot_od) and one of (top_id, top_od).
    The framework solves for the missing diameters.
    """

    equations = [
        "bot_od == bot_id + 2*thk",
        "top_od == top_id + 2*thk",
        "h, thk, bot_id, bot_od, top_id, top_od > 0",
    ]

    def build(self):
        outer = cylinder(
            h=self.h,
            r1=self.bot_od / 2.0,
            r2=self.top_od / 2.0,
        )
        inner = cylinder(
            h=self.h,
            r1=self.bot_id / 2.0,
            r2=self.top_id / 2.0,
        ).through(outer)
        return difference(outer, inner)


class RoundedBox(Component):
    """Box with all edges rounded by a sphere of radius `r`.

    Implementation: minkowski(cube(size - 2r), sphere(r)). Centered on origin.
    """

    size = Param(tuple)  # (x, y, z)
    equations = ["r > 0"]

    def setup(self):
        if len(self.size) != 3:
            raise ValidationError(f"RoundedBox: size must be a 3-tuple, got {self.size!r}")
        for i, s in enumerate(self.size):
            if s <= 2 * self.r:
                raise ValidationError(
                    f"RoundedBox: size[{i}]={s} must be > 2*r={2*self.r}"
                )

    def build(self):
        x, y, z = self.size
        inner = cube(
            [x - 2 * self.r, y - 2 * self.r, z - 2 * self.r], center=True
        )
        return minkowski(inner, sphere(r=self.r))


class FilletRing(Component):
    """Right-triangle-cross-section ring between `id` and `od`.

    `slant` picks which wall is the sloped face:

    - `"outwards"` (default) — outer wall is the slope, inner wall is a
      straight cylinder at id/2. Built as a cone at `od` truncated by a
      cylinder at `id`.
    - `"inwards"` — outer wall is straight at od/2, inner wall slopes
      outward from id/2 at z=0 to od/2 at z=h.

    Both variants have height `tan(base_angle) * (od - id) / 2` and a
    matching slope of `base_angle` degrees from horizontal, so they lie on
    parallel cone surfaces for equal (id, od, base_angle).
    """

    equations = [
        "id, od > 0",
        "base_angle > 0",
        "base_angle < 90",
        "id < od",
    ]
    slant = Param(str, default="outwards", one_of=("outwards", "inwards"))

    def build(self):
        import math as _m

        angle_rad = _m.radians(self.base_angle)
        eps = 0.001 * max(self.od, 1.0)

        if self.slant == "outwards":
            cone_h = _m.tan(angle_rad) * (self.od / 2.0)
            cone = cylinder(h=cone_h, r1=self.od / 2.0, r2=0)
            cut_h = _m.tan(angle_rad) * (self.id / 2.0)
            cutter = cylinder(h=cut_h, r=self.id / 2.0).through(cone)
            return difference(cone, cutter)

        # slant == "inwards"
        h = _m.tan(angle_rad) * (self.od - self.id) / 2.0
        outer = cylinder(h=h, r=self.od / 2.0)
        cutter = cylinder(
            h=h + 2 * eps,
            r1=self.id / 2.0,
            r2=self.od / 2.0 + eps,
        ).down(eps)
        return difference(outer, cutter)


class UShapeChannel(Component):
    """U-channel: three-sided rectangular tube open on one side.

    Six dimensional Params with two equations; specify any three
    (e.g. channel_width + wall_thk + channel_height) and the framework
    solves the rest.  Set `n_shape=True` to flip the opening downward.
    """

    equations = [
        "outer_width == channel_width + 2 * wall_thk",
        "outer_height == channel_height + wall_thk",
        "bottom_width == outer_width",
        "channel_width, channel_height, outer_width, outer_height, wall_thk, channel_length > 0",
    ]
    n_shape = Param(bool, default=False)

    def setup(self):
        # Channel opening: center of the open top (or bottom if n_shape).
        open_z = 0.0 if self.n_shape else self.outer_height
        open_normal = (0.0, 0.0, -1.0) if self.n_shape else (0.0, 0.0, 1.0)
        self.anchor(
            "channel_opening",
            position=(self.outer_width / 2, self.channel_length / 2, open_z),
            normal=open_normal,
        )

    def build(self):
        EPS = 0.02
        outer = cube([self.outer_width, self.channel_length, self.outer_height])
        cutter = cube(
            [self.channel_width, self.channel_length + EPS, self.channel_height + EPS],
        ).translate([self.wall_thk, -EPS / 2, self.wall_thk])
        shape = difference(outer, cutter)
        if self.n_shape:
            shape = shape.flip("z").up(self.outer_height)
        return shape
