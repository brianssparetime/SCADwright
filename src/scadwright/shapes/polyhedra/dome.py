"""Dome, Ogive, Paraboloid, and Ellipsoid Components."""

from __future__ import annotations

import math

from scadwright.boolops import difference, intersection
from scadwright.component.anchors import anchor
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.extrusions import rotate_extrude
from scadwright.primitives import cylinder, polygon, sphere


class Dome(Component):
    """A portion of a sphere sliced by a plane — solid only.

    The cap sits with its flat face on z=0 and the curved surface rising
    in +z. Four dimensional parameters linked by two equations; supply any
    consistent pair and the framework solves the rest::

        Dome(sphere_r=15, cap_height=15)    # hemisphere
        Dome(cap_dia=30, cap_height=15)     # same hemisphere, diameter form
        Dome(sphere_r=20, cap_height=8)     # shallow cap
        Dome(cap_dia=30, sphere_r=18)       # solver derives cap_height

    Solid only. For a hollow shell, build it from two domes::

        outer = Dome(sphere_r=15, cap_height=15)
        inner = Dome(sphere_r=13, cap_height=13)
        shell = difference(outer, inner)

    Anchors:

    - ``base`` — center of the flat z=0 face, normal ``-z``, with
      ``rim_radius=cap_r`` for ``attach(angle=, at_radial=)`` and
      ``add_text(on="base", ...)`` arc-on-rim.
    - ``surface`` — entry point for the curved cap surface (kind
      ``spherical``). The underlying sphere is centered at
      ``z = cap_height - sphere_r`` (below the flat face when the cap
      is less than a hemisphere). Use ``attach(polar=, angle=)`` to
      land anywhere on the cap; the apex (``polar=0``) is at
      ``(0, 0, cap_height)``. Polar angles past the cap's edge land in
      empty space — the framework doesn't clamp.
    """

    equations = """
        cap_r = cap_dia / 2
        cap_r**2 = cap_height * (2 * sphere_r - cap_height)
        cap_height, cap_dia, cap_r, sphere_r > 0
        cap_height <= 2 * sphere_r
    """

    base = anchor(
        at=(0.0, 0.0, 0.0),
        normal=(0.0, 0.0, -1.0),
        kind="planar",
        surface_params={
            "axis": (0.0, 0.0, 1.0),
            "meridian_zero": (1.0, 0.0, 0.0),
            "rim_radius": "cap_r",
        },
    )
    surface = anchor(
        at="0, 0, cap_height",
        normal=(0.0, 0.0, 1.0),
        kind="spherical",
        surface_params={
            "axis": (0.0, 0.0, 1.0),
            "axis_origin": "(0.0, 0.0, cap_height - sphere_r)",
            "meridian_zero": (1.0, 0.0, 0.0),
            "radius": "sphere_r",
        },
    )

    def build(self):
        # Sphere center sits at z = cap_height - sphere_r (below z=0 when
        # cap_height < sphere_r), so the sphere's apex lands at z=cap_height.
        # The clip cylinder bounds the cap to z in [0, cap_height]; rim at
        # z=0 has radius cap_r per the cap equation.
        s = sphere(r=self.sphere_r).down(self.sphere_r - self.cap_height)
        clip = cylinder(h=self.cap_height, r=self.sphere_r + 0.01)
        return intersection(s, clip)


class Ogive(Component):
    """Pointed nose cone — solid of revolution with a chosen meridian.

    The base sits on z=0 (radius ``base_r``) and the tip sits at
    z=``length`` (radius 0). ``kind`` selects the meridian shape:

    - ``"tangent"`` (default) — circular arc tangent to the base
      cylinder at z=0. The classic rocketry tangent ogive; the meridian
      smoothly continues a cylinder of radius ``base_r`` below the base.
      Arc radius ``ρ = (base_r² + length²) / (2·base_r)``.
    - ``"parabolic"`` — ``r(z) = base_r · √(1 − z/length)`` (the n=½
      power-series ogive used by the rocket example).
    - ``"elliptical"`` — half-ellipse meridian:
      ``r(z) = base_r · √(1 − (z/length)²)``.

    Tip is a vertex, not a face — the ``tip`` anchor is a point. The
    base ``rim_radius`` matches Tube/Funnel/Dome rims, so
    ``add_text(on="base")`` arc-on-rim works out of the box::

        Ogive(base_r=10, length=18)                      # tangent (default)
        Ogive(base_r=10, length=18, kind="parabolic")    # rocket-nose flavor
        Ogive(base_d=20, length=18, kind="elliptical")   # blunt-nose half-ellipse
    """

    equations = """
        base_r = base_d / 2
        base_r, base_d, length > 0
        ?kind:str = ?kind or "tangent"
        kind in ("tangent", "parabolic", "elliptical")
        length >= (base_r if kind == "tangent" else 0)
    """

    base = anchor(
        at=(0.0, 0.0, 0.0),
        normal=(0.0, 0.0, -1.0),
        kind="planar",
        surface_params={
            "axis": (0.0, 0.0, 1.0),
            "meridian_zero": (1.0, 0.0, 0.0),
            "rim_radius": "base_r",
        },
    )
    tip = anchor(at="0, 0, length", normal=(0.0, 0.0, 1.0))

    _MERIDIAN_SEGMENTS = 64

    def build(self):
        n = self._MERIDIAN_SEGMENTS
        L = self.length
        R = self.base_r
        # Profile is a closed polygon: axis-base, base-rim, meridian arc
        # to tip-on-axis, back along axis. Walking from (0, 0) outward to
        # (R, 0) keeps the polygon CCW so rotate_extrude produces an
        # outward-facing solid without explicit normal flip.
        pts: list[tuple[float, float]] = [(0.0, 0.0), (R, 0.0)]
        if self.kind == "tangent":
            # Circular arc from (R, 0) to (0, L), tangent to the cylinder
            # r=R at z=0. Center on the z=0 line at (R - rho, 0); arc
            # angle from 0 (at base, (R, 0)) to theta_tip (where the arc
            # reaches the axis at (0, L)). The atan2 form handles both
            # long ogives (L > R, sweep < 90°) and short ones (L < R,
            # sweep > 90°) without branching.
            rho = (R * R + L * L) / (2.0 * R)
            cx = R - rho
            theta_tip = math.atan2(L, -cx)
            for i in range(1, n + 1):
                theta = theta_tip * i / n
                x = cx + rho * math.cos(theta)
                z = rho * math.sin(theta)
                pts.append((x, z))
        elif self.kind == "parabolic":
            # r(z) = R * sqrt(1 - z/L). Sample by z.
            for i in range(1, n + 1):
                z = L * i / n
                t = max(0.0, 1.0 - z / L)
                r = R * math.sqrt(t)
                pts.append((r, z))
        else:  # "elliptical"
            for i in range(1, n + 1):
                z = L * i / n
                t = max(0.0, 1.0 - (z / L) ** 2)
                r = R * math.sqrt(t)
                pts.append((r, z))
        # Last sampled point should be (0, L) by construction; guard
        # floating-point so the polygon closes cleanly on the axis.
        pts[-1] = (0.0, L)
        return rotate_extrude(polygon(points=pts))

    def tight_bbox(self):
        # The polygon's outer extent in the radial direction is base_r at
        # z=0; rotate_extrude sweeps that to a full disc. z spans [0, L].
        from scadwright.bbox import bbox
        return bbox(self)


class Ellipsoid(Component):
    """Sphere with three independent semi-axes — centered on the origin.

    ``a``, ``b``, ``c`` are the semi-axes along x, y, z (the three radii).
    Each accepts a diameter alternative (``dx = 2a``, ``dy = 2b``,
    ``dz = 2c``); mix and match per axis::

        Ellipsoid(a=10, b=8, c=6)        # all radii
        Ellipsoid(dx=20, dy=16, dz=12)   # all diameters
        Ellipsoid(a=10, dy=16, c=6)      # mixed

    The bbox-derived face anchors (``top``/``bottom``/``lside``/
    ``rside``/``front``/``back``) sit exactly on the six axis-tip
    points, because an ellipsoid is tangent to its bbox at those tips.

    For a sitting-on-the-ground orientation, chain ``.up(c)``::

        Ellipsoid(a=10, b=8, c=6).up(6)
    """

    equations = """
        a = dx / 2
        b = dy / 2
        c = dz / 2
        a, b, c, dx, dy, dz > 0
    """

    def build(self):
        # Drive the underlying sphere at the largest semi-axis so $fa/$fs
        # produce facet counts matching the ellipsoid's actual size, not
        # a unit sphere. Scaling preserves facet count and stretches
        # uniformly along each axis. If all three axes are equal, the
        # result is a sphere — emit that directly so the SCAD output
        # doesn't carry a redundant scale([1, 1, 1]).
        a, b, c = self.a, self.b, self.c
        if a == b == c:
            return sphere(r=a)
        m = max(a, b, c)
        return sphere(r=m).scale([a / m, b / m, c / m])

    def tight_bbox(self):
        # Ellipsoid is tangent to its bbox at the six axis tips; the
        # bbox-derived extents are tight.
        from scadwright.bbox import bbox
        return bbox(self)


class Paraboloid(Component):
    """Solid bowl-shaped paraboloid (parabolic dish).

    Vertex at the origin, rim at z=``depth`` with radius ``radius``.
    The meridian follows ``r(z) = 2·√(f·z)`` where ``f`` is the focal
    length, related to the rim dimensions by ``4·f·depth = radius²``.
    Specify any consistent pair of (``radius``/``diameter``), ``depth``,
    ``focal_length``; the framework solves the rest::

        Paraboloid(radius=10, depth=8)              # rim r=10, vertex at origin
        Paraboloid(diameter=20, depth=8)            # diameter alternative
        Paraboloid(radius=10, focal_length=3.125)   # depth solved (f·4·d = r²)

    Solid only for v1; a constant-thickness shell isn't a parabolic
    offset of itself, so hollow dishes need an explicit subtract::

        outer = Paraboloid(radius=10, depth=8)
        shell = difference(outer, outer.up(thk))     # rough dish shell

    Anchors: bbox-derived ``bottom`` is the vertex point. Declared
    ``top`` is the rim disk (planar with ``rim_radius=radius``), so
    ``add_text(on="top")`` arc-on-rim works for labels around the rim.

    Distinct from ``Ogive(kind="parabolic")``: that's the same parabola
    with the tip at +z (a nose cone). Paraboloid has the vertex at z=0
    and opens upward (a dish or bowl).
    """

    equations = """
        radius = diameter / 2
        4 * focal_length * depth = radius**2
        radius, diameter, depth, focal_length > 0
    """

    top = anchor(
        at="0, 0, depth",
        normal=(0.0, 0.0, 1.0),
        kind="planar",
        surface_params={
            "axis": (0.0, 0.0, 1.0),
            "meridian_zero": (1.0, 0.0, 0.0),
            "rim_radius": "radius",
        },
    )

    _MERIDIAN_SEGMENTS = 64

    def build(self):
        n = self._MERIDIAN_SEGMENTS
        d = self.depth
        R = self.radius
        f = self.focal_length
        # Meridian: r(z) = 2·sqrt(f·z), z from 0 to depth, sampled
        # uniformly in z. Polygon walks (0, 0) → meridian out to
        # (R, depth) → (0, depth) → close. CCW orientation gives
        # rotate_extrude an outward-facing solid.
        pts: list[tuple[float, float]] = [(0.0, 0.0)]
        for i in range(1, n + 1):
            z = d * i / n
            r = 2.0 * math.sqrt(f * z)
            pts.append((r, z))
        # Force the last point to land exactly on the rim — small
        # floating-point drift from the sqrt sample otherwise.
        pts[-1] = (R, d)
        pts.append((0.0, d))
        return rotate_extrude(polygon(points=pts))

    def tight_bbox(self):
        from scadwright.bbox import bbox
        return bbox(self)
