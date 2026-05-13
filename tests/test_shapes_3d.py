"""Tests for basic 3D shapes added alongside Tube/Funnel/RoundedBox."""

import math
import warnings

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import (
    Barrel,
    BarrelDegeneracyWarning,
    Capsule,
    PieSlice,
    Prismoid,
    RectTube,
    Wedge,
)


# --- Capsule ---


def test_capsule_straight_length_solved():
    c = Capsule(r=3, length=20)
    assert c.straight_length == pytest.approx(14.0)


def test_capsule_bbox():
    c = Capsule(r=3, length=20, fn=64)
    bb = bbox(c)
    assert bb.size[0] == pytest.approx(6.0, abs=0.2)
    assert bb.size[1] == pytest.approx(6.0, abs=0.2)
    assert bb.size[2] == pytest.approx(20.0, abs=0.2)


def test_capsule_emits_union():
    scad = emit_str(Capsule(r=3, length=20))
    assert "union" in scad
    assert "sphere" in scad
    assert "cylinder" in scad


def test_capsule_too_short_raises():
    # length must be > 2*r (straight_length > 0).
    with pytest.raises(ValidationError, match="straight_length"):
        Capsule(r=5, length=5)


def test_capsule_anchors():
    c = Capsule(r=3, length=20)
    anchors = c.get_anchors()
    assert anchors["base"].position == pytest.approx((0.0, 0.0, 0.0))
    assert anchors["base"].normal == pytest.approx((0.0, 0.0, -1.0))
    assert anchors["tip"].position == pytest.approx((0.0, 0.0, 20.0))
    assert anchors["tip"].normal == pytest.approx((0.0, 0.0, 1.0))


# --- RectTube ---


def test_rect_tube_solves_inner():
    t = RectTube(outer_w=30, outer_d=20, wall_thk=2, h=10)
    assert t.inner_w == pytest.approx(26.0)
    assert t.inner_d == pytest.approx(16.0)


def test_rect_tube_solves_outer():
    t = RectTube(inner_w=20, inner_d=12, wall_thk=3, h=10)
    assert t.outer_w == pytest.approx(26.0)
    assert t.outer_d == pytest.approx(18.0)


def test_rect_tube_bbox():
    t = RectTube(outer_w=30, outer_d=20, wall_thk=2, h=10)
    bb = bbox(t)
    assert bb.size[0] == pytest.approx(30.0)
    assert bb.size[1] == pytest.approx(20.0)
    assert bb.size[2] == pytest.approx(10.0)


def test_rect_tube_emits_difference():
    assert "difference" in emit_str(RectTube(outer_w=30, outer_d=20, wall_thk=2, h=10))


def test_rect_tube_over_specified_inconsistent_raises():
    with pytest.raises(ValidationError):
        RectTube(outer_w=5, inner_w=10, wall_thk=1, outer_d=20, inner_d=18, h=10)


def test_rect_tube_underspecified_raises():
    with pytest.raises(ValidationError):
        RectTube(outer_w=30, h=10)


# --- Prismoid ---


def test_prismoid_square_frustum_bbox():
    p = Prismoid(bot_w=20, bot_d=20, top_w=10, top_d=10, h=15)
    bb = bbox(p)
    assert bb.size[0] == pytest.approx(20.0)
    assert bb.size[1] == pytest.approx(20.0)
    assert bb.size[2] == pytest.approx(15.0)


def test_prismoid_shifted_top_bbox_extends():
    # Shifted top pushes the bbox in +x.
    p = Prismoid(bot_w=20, bot_d=20, top_w=10, top_d=10, h=15, shift=(8, 0))
    bb = bbox(p)
    assert bb.max[0] == pytest.approx(13.0, abs=0.1)  # 8 + 10/2


def test_prismoid_emits_polyhedron():
    assert "polyhedron" in emit_str(Prismoid(bot_w=20, bot_d=20, top_w=10, top_d=10, h=15))


def test_prismoid_zero_top_raises():
    with pytest.raises(ValidationError, match="top_w"):
        Prismoid(bot_w=20, bot_d=20, top_w=0, top_d=10, h=15)


def test_prismoid_top_face_anchor_default():
    p = Prismoid(bot_w=20, bot_d=20, top_w=10, top_d=10, h=15)
    assert p.get_anchors()["top_face"].position == pytest.approx((0.0, 0.0, 15.0))


def test_prismoid_top_face_anchor_respects_shift():
    p = Prismoid(bot_w=20, bot_d=20, top_w=10, top_d=10, h=15, shift=(5, 3))
    assert p.get_anchors()["top_face"].position == pytest.approx((5.0, 3.0, 15.0))


# --- Wedge ---


def test_wedge_no_fillet_bbox():
    w = Wedge(base_w=10, base_h=6, thk=20)
    bb = bbox(w)
    assert bb.size[0] == pytest.approx(10.0)
    assert bb.size[1] == pytest.approx(6.0)
    assert bb.size[2] == pytest.approx(20.0)


def test_wedge_no_fillet_emits_polygon():
    scad = emit_str(Wedge(base_w=10, base_h=6, thk=20))
    assert "linear_extrude" in scad
    assert "polygon" in scad


def test_wedge_filleted_smaller_envelope():
    # Rounding acute corners pulls the tangent points inward — bbox shrinks.
    plain = Wedge(base_w=10, base_h=6, thk=20)
    filleted = Wedge(base_w=10, base_h=6, thk=20, fillet=1)
    assert bbox(filleted).size[0] < bbox(plain).size[0]
    assert bbox(filleted).size[1] < bbox(plain).size[1]


def test_wedge_filleted_emits_hull():
    assert "hull" in emit_str(Wedge(base_w=10, base_h=6, thk=20, fillet=1))


def test_wedge_fillet_too_big_raises():
    # fillet < base_h/2 = 3; 4 > 3 triggers the cross-constraint.
    with pytest.raises(ValidationError, match="fillet < base_h"):
        Wedge(base_w=10, base_h=6, thk=20, fillet=4)


def test_wedge_negative_fillet_raises():
    with pytest.raises(ValidationError):
        Wedge(base_w=10, base_h=6, thk=20, fillet=-1)


# --- PieSlice ---


def test_pieslice_bbox():
    p = PieSlice(r=10, angles=(0, 90), h=5, fn=64)
    bb = bbox(p)
    assert bb.size[2] == pytest.approx(5.0)
    # For a 0-90 slice the bbox spans the upper-right quadrant.
    assert bb.max[0] == pytest.approx(10.0, abs=0.5)
    assert bb.max[1] == pytest.approx(10.0, abs=0.5)


def test_pieslice_emits_linear_extrude():
    scad = emit_str(PieSlice(r=10, angles=(0, 120), h=5))
    assert "linear_extrude" in scad
    assert "intersection" in scad  # inherited from Sector


def test_pieslice_bad_h_raises():
    with pytest.raises(ValidationError):
        PieSlice(r=10, angles=(0, 90), h=-1)


# --- Barrel ---


def test_barrel_convex_solves_bulge():
    b = Barrel(h=80, end_d=50, mid_d=64)
    assert b.end_r == pytest.approx(25.0)
    assert b.mid_r == pytest.approx(32.0)
    assert b.bulge == pytest.approx(7.0)


def test_barrel_convex_via_bulge():
    b = Barrel(h=80, end_r=25, bulge=7)
    assert b.mid_r == pytest.approx(32.0)
    assert b.mid_d == pytest.approx(64.0)
    assert b.end_d == pytest.approx(50.0)


def test_barrel_concave_solves_negative_bulge():
    b = Barrel(h=80, end_d=50, mid_d=42)
    assert b.bulge == pytest.approx(-4.0)


def test_barrel_convex_bbox_reaches_mid_radius():
    b = Barrel(h=80, end_d=50, mid_d=64)
    bb = bbox(b)
    assert bb.max[0] == pytest.approx(32.0, abs=0.05)
    assert bb.size[2] == pytest.approx(80.0)
    assert bb.min[2] == pytest.approx(0.0)


def test_barrel_concave_bbox_reaches_end_radius():
    b = Barrel(h=80, end_d=50, mid_d=42)
    bb = bbox(b)
    assert bb.max[0] == pytest.approx(25.0, abs=0.05)
    assert bb.size[2] == pytest.approx(80.0)


def test_barrel_solid_emits_rotate_extrude():
    scad = emit_str(Barrel(h=80, end_d=50, mid_d=64))
    assert "rotate_extrude" in scad
    assert "polygon" in scad


def test_barrel_hollow_emits_difference():
    scad = emit_str(Barrel(h=80, end_d=50, mid_d=64, thk=3))
    assert "difference" in scad
    assert "rotate_extrude" in scad


def test_barrel_hollow_outer_envelope_unchanged():
    solid = bbox(Barrel(h=80, end_d=50, mid_d=64))
    hollow = bbox(Barrel(h=80, end_d=50, mid_d=64, thk=3))
    assert hollow.max == pytest.approx(solid.max)
    assert hollow.min == pytest.approx(solid.min)


def test_barrel_thk_too_thick_raises():
    # thk must be strictly less than the smaller of end_r and mid_r.
    with pytest.raises(ValidationError, match="thk"):
        Barrel(h=80, end_d=50, mid_d=42, thk=22)  # mid_r = 21


def test_barrel_anchors():
    b = Barrel(h=80, end_d=50, mid_d=64)
    anchors = b.get_anchors()
    assert anchors["bottom"].position == pytest.approx((0.0, 0.0, 0.0))
    assert anchors["bottom"].normal == pytest.approx((0.0, 0.0, -1.0))
    assert anchors["top"].position == pytest.approx((0.0, 0.0, 80.0))
    assert anchors["top"].normal == pytest.approx((0.0, 0.0, 1.0))
    # outer_wall reference position is at the equator on the +X meridian.
    assert anchors["outer_wall"].position == pytest.approx((32.0, 0.0, 40.0))
    assert anchors["outer_wall"].normal == pytest.approx((1.0, 0.0, 0.0))
    assert anchors["outer_wall"].kind == "meridional"


def test_barrel_bulge_zero_silently_emits_cylinder():
    # bulge=0 path is the silent fallback: a plain cylinder, no warning.
    with warnings.catch_warnings():
        warnings.simplefilter("error", BarrelDegeneracyWarning)
        b = Barrel(h=80, end_d=50, bulge=0)
        scad = emit_str(b)
    assert "cylinder" in scad
    assert "rotate_extrude" not in scad


def test_barrel_bulge_zero_hollow_silently_emits_tube():
    with warnings.catch_warnings():
        warnings.simplefilter("error", BarrelDegeneracyWarning)
        scad = emit_str(Barrel(h=80, end_d=50, bulge=0, thk=3))
    assert "cylinder" in scad
    assert "difference" in scad
    assert "rotate_extrude" not in scad


def test_barrel_pinched_waist_warns():
    # mid_r near zero relative to end_r should emit BarrelDegeneracyWarning
    # but still build successfully.
    b = Barrel(h=80, end_r=50, mid_r=1e-9)
    with pytest.warns(BarrelDegeneracyWarning, match="pinches"):
        bb = bbox(b)
    assert bb.size[2] == pytest.approx(80.0)


def test_barrel_negative_mid_r_raises():
    with pytest.raises(ValidationError, match="mid_r"):
        Barrel(h=80, end_r=25, bulge=-30)  # would force mid_r = -5


# --- Barrel meridional anchor: at_z evaluation along the arc ---


def test_barrel_outer_wall_at_z_lands_on_meridian_convex():
    from scadwright.ast.placement import _apply_attach_at_z
    b = Barrel(h=80, end_d=50, mid_d=64)  # convex bulge=7
    ow = b.get_anchors()["outer_wall"]
    # Equator: pos at mid_r, normal pure radial.
    assert ow.position == pytest.approx((32.0, 0.0, 40.0))
    assert ow.normal == pytest.approx((1.0, 0.0, 0.0))
    # Rims: pos at end_r at z=0 and z=h; normal tilts away from axis.
    bot = _apply_attach_at_z(ow, -40.0, None)
    assert bot.position == pytest.approx((25.0, 0.0, 0.0), abs=1e-6)
    assert bot.normal[0] > 0 and bot.normal[2] < 0  # outward-and-down
    top = _apply_attach_at_z(ow, 40.0, None)
    assert top.position == pytest.approx((25.0, 0.0, 80.0), abs=1e-6)
    assert top.normal[0] > 0 and top.normal[2] > 0  # outward-and-up


def test_barrel_outer_wall_at_z_lands_on_meridian_concave():
    from scadwright.ast.placement import _apply_attach_at_z
    b = Barrel(h=80, end_d=50, mid_d=42)  # concave bulge=-4
    ow = b.get_anchors()["outer_wall"]
    assert ow.position == pytest.approx((21.0, 0.0, 40.0))
    bot = _apply_attach_at_z(ow, -40.0, None)
    assert bot.position == pytest.approx((25.0, 0.0, 0.0), abs=1e-6)
    # Concave above-equator: surface flares outward, so normal tilts down.
    top = _apply_attach_at_z(ow, 40.0, None)
    assert top.position == pytest.approx((25.0, 0.0, 80.0), abs=1e-6)
    assert top.normal[0] > 0 and top.normal[2] < 0


def test_barrel_outer_wall_at_z_then_angle():
    from scadwright.ast.placement import _apply_attach_angle, _apply_attach_at_z
    b = Barrel(h=80, end_d=50, mid_d=64)
    ow = b.get_anchors()["outer_wall"]
    shifted = _apply_attach_at_z(ow, 20.0, None)
    # Rotate 90° around the central axis: x-position becomes y-position.
    rotated = _apply_attach_angle(shifted, 90, None, None)
    assert rotated.position[0] == pytest.approx(0.0, abs=1e-6)
    assert rotated.position[1] == pytest.approx(shifted.position[0], abs=1e-6)
    assert rotated.position[2] == pytest.approx(60.0, abs=1e-6)


def test_barrel_outer_wall_at_z_out_of_range_raises():
    from scadwright.ast.placement import _apply_attach_at_z
    b = Barrel(h=80, end_d=50, mid_d=64)
    ow = b.get_anchors()["outer_wall"]
    with pytest.raises(ValidationError, match="outside the meridional"):
        _apply_attach_at_z(ow, 50.0, None)  # h/2 = 40, so 50 > range


def test_barrel_inner_wall_anchor_exists_only_when_hollow():
    solid = Barrel(h=80, end_d=50, mid_d=64)
    hollow = Barrel(h=80, end_d=50, mid_d=64, thk=3)
    # inner_wall is declared on both, but the position references thk —
    # solid resolves to the placeholder (0, 0, h/2).
    assert hollow.get_anchors()["inner_wall"].position == pytest.approx((29.0, 0.0, 40.0))


def test_barrel_inner_wall_normal_points_into_bore():
    from scadwright.ast.placement import _apply_attach_at_z
    b = Barrel(h=80, end_d=50, mid_d=64, thk=3)
    iw = b.get_anchors()["inner_wall"]
    assert iw.normal == pytest.approx((-1.0, 0.0, 0.0))
    # At the top rim, inner wall radius = end_r - thk = 22.
    top = _apply_attach_at_z(iw, 40.0, None)
    assert top.position == pytest.approx((22.0, 0.0, 80.0), abs=1e-6)
    # Inner-wall normal mirrors the outer-wall normal (points into the bore).
    assert top.normal[0] < 0


def test_barrel_attach_peg_to_outer_wall():
    from scadwright import bbox as _bbox
    from scadwright.primitives import cube
    b = Barrel(h=80, end_d=50, mid_d=64)
    peg = cube([4, 4, 4]).attach(b, on="outer_wall", using_anchor="lside")
    bb = _bbox(peg)
    # lside (at x=0) lands at the equator surface (32, 0, 40); cube center
    # ends up at +x of the surface.
    assert bb.min[0] == pytest.approx(32.0, abs=1e-3)
    assert bb.size == pytest.approx((4.0, 4.0, 4.0), abs=1e-3)


def test_barrel_attach_peg_with_at_z_and_angle():
    from scadwright import bbox as _bbox
    from scadwright.primitives import cube
    b = Barrel(h=80, end_d=50, mid_d=64)
    # Attach at the upper-quarter meridian rotated 90° (default orient=False
    # leaves the cube axis-aligned; only the lside anchor is moved onto
    # the surface point).
    peg = cube([4, 4, 4]).attach(
        b, on="outer_wall", using_anchor="lside", at_z=20, angle=90,
    )
    bb = _bbox(peg)
    # Surface point at at_z=20, angle=90: x=0, y≈30.29, z=60.
    # Cube's lside (x=0 face, y-center=2, z-center=2) lands there; cube
    # extends +x and is y-centered/z-centered on (30.29, 60).
    assert bb.min[0] == pytest.approx(0.0, abs=1e-3)
    assert bb.max[0] == pytest.approx(4.0, abs=1e-3)
    assert bb.min[1] == pytest.approx(30.29 - 2.0, abs=0.05)
    assert bb.max[1] == pytest.approx(30.29 + 2.0, abs=0.05)
    assert bb.min[2] == pytest.approx(58.0, abs=1e-3)


def test_barrel_add_text_outer_wall_renders():
    # Text wrapping on the curved meridian builds without error and the
    # bbox doesn't grow past the host (engraved text sinks into the wall).
    from scadwright import bbox as _bbox
    b = Barrel(h=80, end_d=50, mid_d=64, fn=64)
    labeled = b.add_text(
        label="SCAD-1", on="outer_wall", angle=0,
        font_size=4, spacing=1.6, relief=-0.4,
    )
    bb = _bbox(labeled)
    assert bb.size[2] == pytest.approx(80.0, abs=0.5)


def test_barrel_add_text_outer_wall_at_z_above_equator():
    from scadwright import bbox as _bbox
    b = Barrel(h=80, end_d=50, mid_d=64, fn=64)
    # Engraved label above the equator — should still render cleanly.
    labeled = b.add_text(
        label="UPPER", on="outer_wall", angle=0, at_z=20,
        font_size=4, spacing=1.6, relief=-0.4,
    )
    bb = _bbox(labeled)
    assert bb.size[2] == pytest.approx(80.0, abs=0.5)


def test_barrel_attach_under_translate_uses_correct_axis_origin():
    # Translating the barrel should move the axis_origin with it, so attach
    # angle= rotates around the new (world-space) axis line, not the world
    # origin.
    from scadwright import bbox as _bbox
    from scadwright.primitives import cube
    b = Barrel(h=80, end_d=50, mid_d=64).translate([100, 0, 0])
    peg = cube([4, 4, 4]).attach(b, on="outer_wall", using_anchor="lside", angle=180)
    bb = _bbox(peg)
    # At angle=180 around axis at (100, 0, 40), the equator surface is at
    # (100 - 32, 0, 40) = (68, 0, 40). Lside lands there; without orient,
    # the cube extends +x from x=68 (axis-aligned).
    assert bb.min[0] == pytest.approx(68.0, abs=1e-3)
    assert bb.max[0] == pytest.approx(72.0, abs=1e-3)
    assert bb.min[1] == pytest.approx(-2.0, abs=1e-3)
