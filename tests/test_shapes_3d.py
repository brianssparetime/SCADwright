"""Tests for basic 3D shapes added alongside Tube/Funnel/RoundedBox."""

import math

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import Capsule, PieSlice, Prismoid, RectTube, Wedge


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
