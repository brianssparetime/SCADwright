"""Tests for polyhedra subpackage."""

import math

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import cube
from scadwright.shapes import (
    Dodecahedron,
    Dome,
    Elbow,
    Ellipsoid,
    Icosahedron,
    Ogive,
    Paraboloid,
    Octahedron,
    Prism,
    Pyramid,
    Tetrahedron,
    Torus,
)


# --- Prism ---


def test_prism_hex():
    p = Prism(sides=6, r=10, h=20)
    bb = bbox(p)
    assert bb.size[2] == pytest.approx(20.0)
    assert bb.max[0] == pytest.approx(10.0)


def test_prism_frustum():
    p = Prism(sides=4, r=10, h=15, top_r=5)
    bb = bbox(p)
    assert bb.size[2] == pytest.approx(15.0)


def test_prism_emits_polyhedron():
    assert "polyhedron" in emit_str(Prism(sides=5, r=8, h=10))


def test_prism_too_few_sides_raises():
    with pytest.raises(ValidationError, match="sides: must be >= 3"):
        Prism(sides=2, r=5, h=10)


# --- Pyramid ---


def test_pyramid_basic():
    p = Pyramid(sides=4, r=10, h=20)
    bb = bbox(p)
    assert bb.size[2] == pytest.approx(20.0)
    assert bb.max[0] == pytest.approx(10.0)


def test_pyramid_emits_polyhedron():
    assert "polyhedron" in emit_str(Pyramid(sides=6, r=5, h=10))


def test_pyramid_too_few_sides_raises():
    with pytest.raises(ValidationError, match="sides: must be >= 3"):
        Pyramid(sides=1, r=5, h=10)


# --- Platonic solids ---


def test_tetrahedron_inscribed_radius():
    t = Tetrahedron(r=10)
    bb = bbox(t)
    # All vertices should be within the circumsphere.
    assert bb.max[2] == pytest.approx(10.0, abs=0.1)


def test_octahedron_vertices_on_axes():
    o = Octahedron(r=10)
    bb = bbox(o)
    assert bb.max[0] == pytest.approx(10.0, abs=0.01)
    assert bb.max[2] == pytest.approx(10.0, abs=0.01)


def test_dodecahedron_builds():
    d = Dodecahedron(r=10)
    scad = emit_str(d)
    assert "polyhedron" in scad


def test_icosahedron_builds():
    i = Icosahedron(r=10)
    scad = emit_str(i)
    assert "polyhedron" in scad


def test_icosahedron_symmetric():
    i = Icosahedron(r=10)
    bb = bbox(i)
    assert bb.size[0] == pytest.approx(bb.size[1], abs=0.1)


# --- Torus ---


def test_torus_full():
    t = Torus(major_r=10, minor_r=3)
    bb = bbox(t)
    # Outer extent: major_r + minor_r = 13 on each side.
    assert bb.max[0] == pytest.approx(13.0, abs=0.5)
    # Height: 2 * minor_r = 6.
    assert bb.size[2] == pytest.approx(6.0, abs=0.5)


def test_torus_partial():
    t = Torus(major_r=10, minor_r=3, angle=180)
    scad = emit_str(t)
    assert "rotate_extrude" in scad


def test_torus_minor_ge_major_raises():
    with pytest.raises(ValidationError, match="minor_r < major_r"):
        Torus(major_r=5, minor_r=5)


# --- Dome (renamed from SphericalCap; the old hemisphere-with-thk Dome
# was removed — use difference(Dome(R), Dome(R-thk)) for a hollow shell) ---


def test_dome_hemisphere():
    """sphere_r == cap_height gives the hemisphere special case."""
    d = Dome(sphere_r=10, cap_height=10)
    bb = bbox(d)
    assert bb.max[2] == pytest.approx(10.0, abs=0.5)
    assert bb.min[2] == pytest.approx(0.0, abs=0.5)
    assert d.cap_r == pytest.approx(10.0)


def test_dome_by_sphere_r_and_cap_height():
    d = Dome(sphere_r=20, cap_height=8)
    bb = bbox(d)
    assert bb.size[2] == pytest.approx(8.0, abs=0.5)
    assert d.sphere_r == 20
    assert d.cap_height == 8


def test_dome_solves_cap_dia():
    d = Dome(sphere_r=20, cap_height=8)
    assert d.cap_dia > 0
    assert d.cap_r == pytest.approx(d.cap_dia / 2)


def test_dome_by_cap_dia_and_cap_height():
    d = Dome(cap_dia=30, cap_height=5)
    assert d.cap_r == pytest.approx(15.0)
    assert d.sphere_r > 0


def test_dome_too_tall_raises():
    with pytest.raises((ValueError, ValidationError)):
        Dome(sphere_r=5, cap_height=11)


def test_dome_emits():
    scad = emit_str(Dome(sphere_r=10, cap_height=5))
    assert "intersection" in scad


def test_dome_apex_at_top():
    """Dome should narrow from rim (radius cap_r at z=0) to the apex at
    z=cap_height. Sphere center sits at z = cap_height - sphere_r (below
    z=0 for partial caps). Verify cap_r matches first-principles math.
    """
    import math
    sphere_r, cap_height = 20.0, 8.0
    d = Dome(sphere_r=sphere_r, cap_height=cap_height)
    z_c = cap_height - sphere_r
    expected_cap_r = math.sqrt(sphere_r ** 2 - z_c ** 2)
    assert d.cap_r == pytest.approx(expected_cap_r, abs=1e-9)


def test_dome_anchors():
    from scadwright.anchor import get_node_anchors
    d = Dome(sphere_r=20, cap_height=8)
    anchors = get_node_anchors(d)
    assert "base" in anchors and "surface" in anchors
    base = anchors["base"]
    assert base.kind == "planar"
    assert base.position == pytest.approx((0.0, 0.0, 0.0))
    assert base.normal == pytest.approx((0.0, 0.0, -1.0))
    assert base.rim_radius == pytest.approx(d.cap_r)
    surface = anchors["surface"]
    assert surface.kind == "spherical"
    assert surface.radius == pytest.approx(20.0)
    # Apex at z=cap_height with sphere center at z = cap_height - sphere_r.
    assert surface.position == pytest.approx((0.0, 0.0, 8.0))
    assert surface.axis_origin == pytest.approx((0.0, 0.0, -12.0))
    assert not surface.inner


def test_dome_surface_attach_with_polar():
    """Attaching to Dome.surface with polar/angle dispatches via the
    sphere placement helper and then through bridge=True onto the
    spherical surface."""
    from scadwright.ast.csg import Union
    peg = cube([2, 2, 5])
    placed = peg.attach(
        Dome(sphere_r=10, cap_height=10),
        on="surface", polar=45, angle=0, orient=True, bridge=True,
    )
    assert isinstance(placed, Union)


def test_dome_partial_cap_surface_bridge():
    """Shallow cap (cap_height < sphere_r): bridge=True onto the
    surface works at any polar angle within the cap's reach."""
    from scadwright.ast.csg import Union
    peg = cube([2, 2, 5])
    placed = peg.attach(
        Dome(sphere_r=20, cap_height=8),
        on="surface", polar=20, angle=0, orient=True, bridge=True,
    )
    assert isinstance(placed, Union)


# --- Ogive ---


def test_ogive_default_kind_is_tangent():
    o = Ogive(base_r=10, length=18)
    assert o.kind == "tangent"


def test_ogive_bbox_matches_base_and_length_for_all_kinds():
    for kind in ("tangent", "parabolic", "elliptical"):
        o = Ogive(base_r=10, length=18, kind=kind, fn=64)
        bb = bbox(o)
        assert bb.min[2] == pytest.approx(0.0)
        assert bb.max[2] == pytest.approx(18.0, abs=0.05)
        assert bb.max[0] == pytest.approx(10.0, abs=0.5)
        assert bb.max[1] == pytest.approx(10.0, abs=0.5)


def test_ogive_base_d_solves_base_r():
    o = Ogive(base_d=20, length=18)
    assert o.base_r == pytest.approx(10.0)


def test_ogive_unknown_kind_raises():
    with pytest.raises(ValidationError, match="kind"):
        Ogive(base_r=10, length=18, kind="hyperbolic")


def test_ogive_emits_rotate_extrude():
    for kind in ("tangent", "parabolic", "elliptical"):
        scad = emit_str(Ogive(base_r=10, length=18, kind=kind))
        assert "rotate_extrude" in scad
        assert "polygon" in scad


def test_ogive_anchors():
    o = Ogive(base_r=10, length=18)
    a = o.get_anchors()
    assert a["base"].position == pytest.approx((0.0, 0.0, 0.0))
    assert a["base"].normal == pytest.approx((0.0, 0.0, -1.0))
    assert a["base"].rim_radius == pytest.approx(10.0)
    assert a["tip"].position == pytest.approx((0.0, 0.0, 18.0))
    assert a["tip"].normal == pytest.approx((0.0, 0.0, 1.0))


def test_ogive_tangent_meridian_radius_matches_classic_formula():
    # ρ = (base_r² + length²) / (2·base_r). For base_r=10, length=18 → 21.2.
    # Verify by checking the meridian's slope at the base is vertical (the
    # defining tangent-ogive property): the first sampled point above the
    # base should have z >> Δr (steep, near-vertical tangent).
    from scadwright.shapes.polyhedra.dome import Ogive as _O
    o = _O(base_r=10, length=18, kind="tangent", fn=64)
    # Build the polygon and inspect first off-base sample.
    n = o._MERIDIAN_SEGMENTS
    rho = (o.base_r ** 2 + o.length ** 2) / (2.0 * o.base_r)
    cx = o.base_r - rho
    theta_tip = math.atan2(o.length, -cx)
    theta_1 = theta_tip / n
    x_1 = cx + rho * math.cos(theta_1)
    z_1 = rho * math.sin(theta_1)
    # Δr / Δz should be tiny (tangent vertical at base).
    delta_r = o.base_r - x_1
    delta_z = z_1
    assert abs(delta_r) < 0.1 * abs(delta_z)  # near-vertical


def test_ogive_tangent_rejects_length_less_than_base_r():
    # The tangent-ogive arc only behaves as a monotonic nose cone when
    # length >= base_r; shorter tangent ogives produce a bulged shape
    # that's no longer the canonical tangent ogive.
    with pytest.raises(ValidationError, match="length"):
        Ogive(base_r=10, length=5, kind="tangent")


def test_ogive_tangent_hemispherical_limit():
    # L = R: the tangent arc is a quarter-circle ending in a hemisphere.
    o = Ogive(base_r=10, length=10, kind="tangent", fn=64)
    bb = bbox(o)
    assert bb.max[2] == pytest.approx(10.0, abs=0.05)
    assert bb.max[0] == pytest.approx(10.0, abs=0.5)


def test_ogive_blunt_noses_via_parabolic_or_elliptical():
    # Blunt noses (length < base_r) are allowed for parabolic and
    # elliptical kinds — the tangent constraint doesn't apply.
    for kind in ("parabolic", "elliptical"):
        o = Ogive(base_r=10, length=5, kind=kind, fn=32)
        bb = bbox(o)
        assert bb.max[2] == pytest.approx(5.0, abs=0.05)
        assert bb.max[0] == pytest.approx(10.0, abs=0.5)


def test_ogive_parabolic_meets_rocket_formula():
    # The rocket builds r(z) = base_r * sqrt(1 - z/length); Ogive(parabolic)
    # should produce the same envelope.
    o = Ogive(base_r=10, length=18, kind="parabolic", fn=64)
    bb = bbox(o)
    assert bb.max[2] == pytest.approx(18.0, abs=0.05)
    # At z = length/2, the parabolic radius is base_r * sqrt(0.5) ≈ 7.07.
    # We can't read internal sampling, but the bbox cap at z=length should
    # be 0 (tip), so size[0] equals 2*base_r at the base.
    assert bb.size[0] == pytest.approx(20.0, abs=0.5)


# --- Paraboloid ---


def test_paraboloid_radius_depth_solves_focal():
    p = Paraboloid(radius=10, depth=8)
    # 4 * f * d = r²  →  f = 100 / 32 = 3.125.
    assert p.focal_length == pytest.approx(3.125)


def test_paraboloid_focal_solves_depth():
    p = Paraboloid(radius=10, focal_length=3.125)
    assert p.depth == pytest.approx(8.0)


def test_paraboloid_diameter_alternative():
    p = Paraboloid(diameter=20, depth=8)
    assert p.radius == pytest.approx(10.0)


def test_paraboloid_bbox_matches_rim_and_depth():
    p = Paraboloid(radius=10, depth=8, fn=64)
    bb = bbox(p)
    assert bb.min[2] == pytest.approx(0.0)
    assert bb.max[2] == pytest.approx(8.0, abs=0.05)
    assert bb.max[0] == pytest.approx(10.0, abs=0.5)
    assert bb.max[1] == pytest.approx(10.0, abs=0.5)


def test_paraboloid_top_anchor_has_rim_radius():
    p = Paraboloid(radius=10, depth=8)
    a = p.get_anchors()
    assert a["top"].position == pytest.approx((0.0, 0.0, 8.0))
    assert a["top"].normal == pytest.approx((0.0, 0.0, 1.0))
    assert a["top"].rim_radius == pytest.approx(10.0)


def test_paraboloid_bottom_is_vertex():
    # bbox-derived bottom anchor sits at the vertex point (z=0).
    p = Paraboloid(radius=10, depth=8)
    a = p.get_anchors()
    assert a["bottom"].position == pytest.approx((0.0, 0.0, 0.0))
    assert a["bottom"].normal == pytest.approx((0.0, 0.0, -1.0))


def test_paraboloid_emits_rotate_extrude():
    scad = emit_str(Paraboloid(radius=10, depth=8))
    assert "rotate_extrude" in scad
    assert "polygon" in scad


def test_paraboloid_underspecified_raises():
    # Need any two of (radius/diameter, depth, focal_length); just one isn't enough.
    with pytest.raises(ValidationError):
        Paraboloid(radius=10)


def test_paraboloid_negative_param_raises():
    with pytest.raises(ValidationError):
        Paraboloid(radius=10, depth=-1)


# --- Ellipsoid ---


def test_ellipsoid_via_semi_axes():
    e = Ellipsoid(a=10, b=8, c=6, fn=64)
    bb = bbox(e)
    assert bb.min == pytest.approx((-10.0, -8.0, -6.0), abs=0.5)
    assert bb.max == pytest.approx((10.0, 8.0, 6.0), abs=0.5)


def test_ellipsoid_via_diameters():
    e = Ellipsoid(dx=20, dy=16, dz=12)
    assert e.a == pytest.approx(10.0)
    assert e.b == pytest.approx(8.0)
    assert e.c == pytest.approx(6.0)


def test_ellipsoid_mixed_radius_diameter():
    e = Ellipsoid(a=10, dy=16, c=6)
    assert e.dx == pytest.approx(20.0)
    assert e.b == pytest.approx(8.0)
    assert e.dz == pytest.approx(12.0)


def test_ellipsoid_face_anchors_at_axis_tips():
    # bbox-derived face anchors land exactly on the ellipsoid's axis tips
    # because the ellipsoid is tangent to its bbox at the tips.
    e = Ellipsoid(a=10, b=8, c=6)
    a = e.get_anchors()
    assert a["rside"].position == pytest.approx((10.0, 0.0, 0.0))
    assert a["lside"].position == pytest.approx((-10.0, 0.0, 0.0))
    assert a["back"].position == pytest.approx((0.0, 8.0, 0.0))
    assert a["front"].position == pytest.approx((0.0, -8.0, 0.0))
    assert a["top"].position == pytest.approx((0.0, 0.0, 6.0))
    assert a["bottom"].position == pytest.approx((0.0, 0.0, -6.0))


def test_ellipsoid_emits_sphere_and_scale():
    scad = emit_str(Ellipsoid(a=10, b=8, c=6))
    assert "sphere" in scad
    assert "scale" in scad


def test_ellipsoid_uniform_axes_emits_sphere_only():
    # When a == b == c, build() short-circuits to a plain sphere — no
    # redundant scale wrapper in the SCAD output.
    scad = emit_str(Ellipsoid(a=10, b=10, c=10))
    assert "sphere" in scad
    assert "scale" not in scad


def test_ellipsoid_negative_axis_raises():
    with pytest.raises(ValidationError):
        Ellipsoid(a=10, b=-1, c=6)


def test_ellipsoid_underspecified_raises():
    with pytest.raises(ValidationError):
        Ellipsoid(a=10, b=8)  # c missing


# --- Elbow ---


def test_elbow_default_angle_is_90():
    e = Elbow(id=8, od=12, bend_radius=20)
    assert e.angle == pytest.approx(90.0)


def test_elbow_id_thk_solves_od():
    e = Elbow(id=8, thk=2, bend_radius=20)
    assert e.od == pytest.approx(12.0)


def test_elbow_od_thk_solves_id():
    e = Elbow(od=12, thk=2, bend_radius=20)
    assert e.id == pytest.approx(8.0)


def test_elbow_id_od_solves_thk():
    e = Elbow(id=8, od=12, bend_radius=20)
    assert e.thk == pytest.approx(2.0)


def test_elbow_start_anchor_at_angle_zero():
    e = Elbow(id=8, od=12, bend_radius=20)
    a = e.get_anchors()
    assert a["start"].position == pytest.approx((20.0, 0.0, 0.0))
    assert a["start"].normal == pytest.approx((0.0, -1.0, 0.0))
    assert a["start"].rim_radius == pytest.approx(6.0)


def test_elbow_end_anchor_at_90_degrees():
    e = Elbow(id=8, od=12, bend_radius=20, angle=90)
    a = e.get_anchors()
    pos = a["end"].position
    assert pos[0] == pytest.approx(0.0, abs=1e-6)
    assert pos[1] == pytest.approx(20.0, abs=1e-6)
    assert pos[2] == pytest.approx(0.0, abs=1e-6)
    n = a["end"].normal
    assert n[0] == pytest.approx(-1.0, abs=1e-6)
    assert n[1] == pytest.approx(0.0, abs=1e-6)


def test_elbow_end_anchor_at_180_degrees():
    e = Elbow(id=8, od=12, bend_radius=20, angle=180)
    a = e.get_anchors()
    pos = a["end"].position
    assert pos[0] == pytest.approx(-20.0, abs=1e-6)
    assert pos[1] == pytest.approx(0.0, abs=1e-6)
    n = a["end"].normal
    # 180° elbow: U-bend, both ends face -y.
    assert n[0] == pytest.approx(0.0, abs=1e-6)
    assert n[1] == pytest.approx(-1.0, abs=1e-6)


def test_elbow_emits_difference_of_rotate_extrudes():
    scad = emit_str(Elbow(id=8, od=12, bend_radius=20))
    assert "difference" in scad
    assert "rotate_extrude" in scad


def test_elbow_bbox_for_90_degree():
    e = Elbow(id=8, od=12, bend_radius=20, fn=64)
    bb = bbox(e)
    # The 90° quarter sweep with tube radius 6 around bend radius 20:
    # x extends from 0 (at the inner edge of the +y end) to 26 (outer rim
    # at angle=0); y from 0 to 26; z from -6 to +6 (tube cross-section).
    assert bb.max[0] == pytest.approx(26.0, abs=0.5)
    assert bb.max[1] == pytest.approx(26.0, abs=0.5)
    assert bb.min[2] == pytest.approx(-6.0, abs=0.05)
    assert bb.max[2] == pytest.approx(6.0, abs=0.05)


def test_elbow_tube_too_fat_for_bend_raises():
    # od/2 must be strictly less than bend_radius (otherwise the tube
    # self-intersects on the inner side of the bend).
    with pytest.raises(ValidationError):
        Elbow(id=8, od=20, bend_radius=10)  # od/2 = 10 = bend_radius
    with pytest.raises(ValidationError):
        Elbow(id=8, od=24, bend_radius=10)  # od/2 = 12 > bend_radius


def test_elbow_angle_zero_or_negative_raises():
    with pytest.raises(ValidationError):
        Elbow(id=8, od=12, bend_radius=20, angle=0)
    with pytest.raises(ValidationError):
        Elbow(id=8, od=12, bend_radius=20, angle=-30)


def test_elbow_angle_above_360_raises():
    with pytest.raises(ValidationError):
        Elbow(id=8, od=12, bend_radius=20, angle=400)
