"""3D shape library: Tube, Funnel, RoundedBox, FilletRing, UShapeChannel,
Capsule, RectTube, Prismoid, Wedge, PieSlice.
"""

from __future__ import annotations

import math

from scadwright.boolops import difference, hull, minkowski, union
from scadwright.component.anchors import anchor
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.extrusions import linear_extrude
from scadwright.primitives import circle, cube, cylinder, polygon, polyhedron, sphere
from scadwright.shapes.two_d import Sector


class Tube(Component):
    """Hollow cylinder. Provide h plus any two of (id, od, thk); the third is solved.

    od = outer diameter, id = inner diameter, thk = wall thickness.
    """

    equations = [
        "od = id + 2*thk",
        "h, id, od, thk > 0",
    ]

    outer_wall = anchor(
        at="od/2, 0, h/2",
        normal=(1.0, 0.0, 0.0),
        kind="cylindrical",
        surface_params={"axis": (0.0, 0.0, 1.0), "radius": "od/2", "length": "h"},
    )
    inner_wall = anchor(
        at="id/2, 0, h/2",
        normal=(-1.0, 0.0, 0.0),
        kind="cylindrical",
        surface_params={
            "axis": (0.0, 0.0, 1.0),
            "radius": "id/2",
            "length": "h",
            "inner": True,
        },
    )
    top = anchor(
        at="0, 0, h",
        normal=(0.0, 0.0, 1.0),
        kind="planar",
        surface_params={"axis": (0.0, 0.0, 1.0), "rim_radius": "od/2"},
    )
    bottom = anchor(
        at="0, 0, 0",
        normal=(0.0, 0.0, -1.0),
        kind="planar",
        surface_params={"axis": (0.0, 0.0, -1.0), "rim_radius": "od/2"},
    )

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
        "bot_od = bot_id + 2*thk",
        "top_od = top_id + 2*thk",
        "h, thk, bot_id, bot_od, top_id, top_od > 0",
    ]

    outer_wall = anchor(
        at="(bot_od + top_od) / 4.0, 0, h/2",
        normal=(1.0, 0.0, 0.0),
        kind="conical",
        surface_params={
            "axis": (0.0, 0.0, 1.0),
            "r1": "bot_od/2.0",
            "r2": "top_od/2.0",
            "length": "h",
        },
    )
    inner_wall = anchor(
        at="(bot_id + top_id) / 4.0, 0, h/2",
        normal=(-1.0, 0.0, 0.0),
        kind="conical",
        surface_params={
            "axis": (0.0, 0.0, 1.0),
            "r1": "bot_id/2.0",
            "r2": "top_id/2.0",
            "length": "h",
            "inner": True,
        },
    )
    top = anchor(
        at="0, 0, h",
        normal=(0.0, 0.0, 1.0),
        kind="planar",
        surface_params={"axis": (0.0, 0.0, 1.0), "rim_radius": "top_od/2"},
    )
    bottom = anchor(
        at="0, 0, 0",
        normal=(0.0, 0.0, -1.0),
        kind="planar",
        surface_params={"axis": (0.0, 0.0, -1.0), "rim_radius": "bot_od/2"},
    )

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
    equations = [
        "r > 0",
        "len(size) == 3",
        "all(s > 2 * r for s in size)",
    ]

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

    Both variants share the same `base_angle` slope on the matching
    cone surface, so they lie on parallel cones for equal
    (id, od, base_angle). They differ in height: the outwards form
    extends the cone all the way to the apex (height
    `tan(base_angle) * od/2`); the inwards form is just the wedge between
    id and od (height `tan(base_angle) * (od - id) / 2`).
    """

    equations = [
        "id, od > 0",
        "base_angle > 0",
        "base_angle < 90",
        "id < od",
    ]
    slant = Param(str, default="outwards", one_of=("outwards", "inwards"))

    def build(self):
        angle_rad = math.radians(self.base_angle)

        if self.slant == "outwards":
            cone_h = math.tan(angle_rad) * (self.od / 2.0)
            cone = cylinder(h=cone_h, r1=self.od / 2.0, r2=0)
            cut_h = math.tan(angle_rad) * (self.id / 2.0)
            cutter = cylinder(h=cut_h, r=self.id / 2.0).through(cone)
            return difference(cone, cutter)

        # slant == "inwards": manual EPS here is the style-guide-allowed
        # "non-axis-aligned cutter" edge case — cutter's side face is
        # slanted, so through() can't detect the coincident faces.
        eps = 0.001 * max(self.od, 1.0)
        h = math.tan(angle_rad) * (self.od - self.id) / 2.0
        outer = cylinder(h=h, r=self.od / 2.0)
        cutter = cylinder(
            h=h + 2 * eps,
            r1=self.id / 2.0,
            r2=self.od / 2.0 + eps,
        ).down(eps)
        return difference(outer, cutter)


class Capsule(Component):
    """Pill / stadium solid: a cylinder with hemispherical caps on both ends.

    ``length`` is the total end-to-end distance along +z (hemispheres
    included); ``r`` is the radius of the hemispheres and the cylindrical
    body. The straight-section height ``straight_length`` is computed at
    construction from ``length`` and ``r``. Anchors ``base`` (z=0) and
    ``tip`` (z=length) point outward in ±z.

    Always built along z, like Tube/Funnel/Helix/etc. For a horizontal
    capsule, rotate the result: ``Capsule(r=3, length=20).rotate([0, 90, 0])``.
    """

    equations = [
        "straight_length = length - 2 * r",
        "r, length > 0",
        "straight_length > 0",
    ]

    base = anchor(at=(0, 0, 0), normal=(0, 0, -1))
    tip = anchor(at="0, 0, length", normal=(0, 0, 1))

    def build(self):
        body = cylinder(h=self.straight_length, r=self.r).up(self.r)
        bot = sphere(r=self.r).up(self.r)
        top = sphere(r=self.r).up(self.r + self.straight_length)
        return union(body, bot, top)


class RectTube(Component):
    """Rectangular hollow tube.

    Outer rectangle ``outer_w`` x ``outer_d``, inner rectangle
    ``inner_w`` x ``inner_d``, ``wall_thk`` all-around wall thickness. The
    two cross-section equations couple outer and inner by ``wall_thk``, so
    any combination of (outer, inner, wall_thk) that fixes two of the three
    per-axis dimensions is sufficient.
    """

    equations = [
        "outer_w = inner_w + 2 * wall_thk",
        "outer_d = inner_d + 2 * wall_thk",
        "h, outer_w, outer_d, inner_w, inner_d, wall_thk > 0",
    ]

    def build(self):
        outer = cube([self.outer_w, self.outer_d, self.h], center="xy")
        inner = cube([self.inner_w, self.inner_d, self.h], center="xy").through(outer)
        return difference(outer, inner)


class Prismoid(Component):
    """Rectangular frustum with independent top dimensions and optional shift.

    Base rectangle ``bot_w`` x ``bot_d`` sits on z=0; top rectangle
    ``top_w`` x ``top_d`` sits at z=``h``, offset from the base center by
    ``shift=(dx, dy)``. A square frustum (all four top/bottom equal) with
    ``shift=(0, 0)`` is the common case; an offset top is useful for
    transition parts between off-axis features.

    Publishes a ``top_face`` anchor at the geometric center of the top
    face (shift-aware), distinct from the bbox-derived ``top`` anchor
    which would mislead when ``shift`` is non-zero.

    For a rectangular pyramid (pointed apex), use ``Pyramid`` with
    ``sides=4`` — ``Prismoid`` requires positive top dimensions to avoid
    degenerate polyhedron faces.
    """

    equations = [
        "bot_w, bot_d, top_w, top_d, h > 0",
    ]
    shift = Param(tuple, default=(0.0, 0.0))

    top_face = anchor(at="shift[0], shift[1], h", normal=(0, 0, 1))

    def build(self):
        x_b, y_b = self.bot_w / 2.0, self.bot_d / 2.0
        x_t, y_t = self.top_w / 2.0, self.top_d / 2.0
        sx, sy = float(self.shift[0]), float(self.shift[1])
        h = self.h
        points = [
            (-x_b, -y_b, 0.0),
            (+x_b, -y_b, 0.0),
            (+x_b, +y_b, 0.0),
            (-x_b, +y_b, 0.0),
            (-x_t + sx, -y_t + sy, h),
            (+x_t + sx, -y_t + sy, h),
            (+x_t + sx, +y_t + sy, h),
            (-x_t + sx, +y_t + sy, h),
        ]
        faces = [
            [3, 2, 1, 0],     # bottom (reversed winding for -z outward normal)
            [4, 5, 6, 7],     # top
            [0, 1, 5, 4],     # -y
            [1, 2, 6, 5],     # +x
            [2, 3, 7, 6],     # +y
            [3, 0, 4, 7],     # -x
        ]
        return polyhedron(points=points, faces=faces)


class Wedge(Component):
    """Right-triangular prism. Also serves as the standard rib / gusset shape.

    Cross-section is a right triangle with legs along +x (``base_w``) and
    +y (``base_h``); extruded ``thk`` along +z with the right-angle vertex
    at the origin.

    Pass ``fillet=r`` to soften all three corners. Note that rounding an
    acute corner by radius *r* pulls the tangent point back by roughly
    *r* / sin(α/2) from the vertex, so for a shallow wedge (large
    base_w / base_h ratio) even a small fillet visibly shrinks the x and y
    envelope. Useful where the hypotenuse-end tips don't need to reach the
    full ``base_w`` / ``base_h`` corners (rib gussets, ramp edges).
    """

    # `?fillet` auto-declares as Param(float, default=None); the
    # rules skip silently when it is unset.
    equations = [
        "base_w, base_h, thk > 0",
        "?fillet > 0",
        "?fillet < base_w / 2",
        "?fillet < base_h / 2",
    ]

    def build(self):
        if self.fillet is None:
            profile = polygon(points=[
                (0.0, 0.0),
                (self.base_w, 0.0),
                (0.0, self.base_h),
            ])
        else:
            # Each rounding circle is placed where the inset lines (each edge
            # moved inward by `fillet`) intersect; its radius exactly equals
            # the fillet, so the three common tangents of the circle pair hit
            # the original triangle's three edges. Hull gives the filleted
            # region between them.
            d = self.fillet
            L = math.sqrt(self.base_w ** 2 + self.base_h ** 2)
            c1 = circle(r=d).translate([d, d, 0])
            c2 = circle(r=d).translate(
                [self.base_w - d * (self.base_w + L) / self.base_h, d, 0]
            )
            c3 = circle(r=d).translate(
                [d, self.base_h - d * (self.base_h + L) / self.base_w, 0]
            )
            profile = hull(c1, c2, c3)
        return linear_extrude(profile, height=self.thk)


class PieSlice(Component):
    """Cylindrical sector: a Sector profile extruded along +z.

    Produces a 3D wedge of a disc. Convenience over writing
    ``Sector(r, angles).linear_extrude(height=h)`` inline.
    """

    equations = ["r, h > 0"]
    angles = Param(tuple)

    def build(self):
        return Sector(r=self.r, angles=self.angles).linear_extrude(height=self.h)


class UShapeChannel(Component):
    """U-channel: three-sided rectangular tube open on one side.

    Six dimensional Params with two equations; specify any three
    (e.g. channel_width + wall_thk + channel_height) and the framework
    solves the rest.  Set `n_shape=True` to flip the opening downward.
    """

    equations = [
        "outer_width = channel_width + 2 * wall_thk",
        "outer_height = channel_height + wall_thk",
        "bottom_width = outer_width",
        "channel_width, channel_height, outer_width, outer_height, wall_thk, channel_length > 0",
    ]
    n_shape = Param(bool, default=False)

    # Channel opening: top by default, bottom when flipped via n_shape.
    # Both position and normal switch on n_shape — the string-expression
    # form for normal= is what makes this declarable at class scope.
    channel_opening = anchor(
        at="outer_width/2, channel_length/2, 0 if n_shape else outer_height",
        normal="0, 0, -1 if n_shape else 1",
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
