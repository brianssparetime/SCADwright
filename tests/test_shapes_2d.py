import math

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import (
    Annulus,
    Arc,
    CircularSegment,
    Keyhole,
    RoundedEndsArc,
    RoundedSlot,
    Sector,
    Star,
    Teardrop,
    regular_polygon,
    rounded_rect,
    rounded_square,
)
def test_rounded_rect_emits():
    out = emit_str(rounded_rect(20, 10, 2, fn=12))
    assert "minkowski" in out
    assert "circle" in out
    assert "square" in out


def test_rounded_rect_zero_radius_falls_back():
    out = emit_str(rounded_rect(20, 10, 0))
    assert "minkowski" not in out
    assert "square" in out


def test_rounded_square_scalar():
    a = rounded_square(10, 2, fn=8)
    out = emit_str(a)
    assert "minkowski" in out


def test_regular_polygon_vertex_count():
    p = regular_polygon(sides=6, r=5)
    out = emit_str(p)
    assert "polygon" in out
    # 6 vertices
    assert out.count("[") >= 6


def test_regular_polygon_too_few_sides_raises():
    with pytest.raises(ValidationError):
        regular_polygon(sides=2, r=5)


def test_sector_component():
    s = Sector(r=10, angles=(0, 90), fn=24)
    assert s.r == 10.0
    out = emit_str(s)
    assert "intersection" in out
    assert "circle" in out
    assert "polygon" in out


def test_arc_derived_attrs():
    a = Arc(r=10, angles=(0, 90), width=2, fn=24)
    assert a.inner_r == 9.0
    assert a.outer_r == 11.0


def test_rounded_slot_emit():
    s = RoundedSlot(length=20, width=4, fn=16)
    out = emit_str(s)
    assert "square([16, 4]" in out
    assert "circle(r=2" in out


def test_rounded_slot_when_length_equals_width_is_circle():
    s = RoundedSlot(length=4, width=4, fn=16)
    out = emit_str(s)
    assert "square" not in out  # rect_length == 0, falls back to circle


def test_rounded_ends_arc():
    a = RoundedEndsArc(r=10, angles=(0, 90), width=1, end_r=0.5, fn=24)
    out = emit_str(a)
    assert "union" in out


# --- Teardrop ---


def test_teardrop_default_tip_angle():
    t = Teardrop(r=5)
    # tip_height = r / cos(45°) = r * sqrt(2)
    assert t.tip_height == pytest.approx(5 * math.sqrt(2))


def test_teardrop_custom_tip_angle():
    t = Teardrop(r=10, tip_angle=30)
    assert t.tip_height == pytest.approx(10 / math.cos(math.radians(30)))


def test_teardrop_bbox_untruncated():
    t = Teardrop(r=5, fn=64)
    bb = bbox(t)
    # y from -r to tip_height
    assert bb.min[1] == pytest.approx(-5.0, abs=0.1)
    assert bb.max[1] == pytest.approx(5 * math.sqrt(2), abs=0.1)


def test_teardrop_truncated_shorter_than_untruncated():
    untrunc = Teardrop(r=5, fn=64)
    trunc = Teardrop(r=5, cap_h=5.5, fn=64)
    assert bbox(trunc).size[1] < bbox(untrunc).size[1]


def test_teardrop_emits_union():
    assert "union" in emit_str(Teardrop(r=5))


def test_teardrop_bad_tip_angle_raises():
    with pytest.raises(ValidationError, match="tip_angle"):
        Teardrop(r=5, tip_angle=90)


def test_teardrop_cap_below_circle_raises():
    with pytest.raises(ValidationError, match="cap_h > r"):
        Teardrop(r=5, cap_h=3)


def test_teardrop_cap_above_tip_raises():
    with pytest.raises(ValidationError, match="cap_h < tip_height"):
        Teardrop(r=5, cap_h=10)


def test_teardrop_no_cap_skips_cap_constraints():
    # cap_h=None must not fire cap_h constraints even though tip_height is set.
    t = Teardrop(r=5)
    assert t.cap_h is None


# --- Keyhole ---


def test_keyhole_builds():
    k = Keyhole(r_big=5, r_slot=2, slot_length=10, fn=32)
    out = emit_str(k)
    assert "union" in out
    assert "hull" in out


def test_keyhole_bbox():
    k = Keyhole(r_big=5, r_slot=2, slot_length=10, fn=64)
    bb = bbox(k)
    # Width: head diameter (= 2 * r_big = 10), wider than slot.
    assert bb.size[0] == pytest.approx(10.0, abs=0.5)
    # Height: from head top (+r_big) to slot bottom (-slot_length - r_slot).
    assert bb.max[1] == pytest.approx(5.0, abs=0.5)
    assert bb.min[1] == pytest.approx(-12.0, abs=0.5)


def test_keyhole_slot_wider_than_head_raises():
    with pytest.raises(ValidationError, match="r_slot < r_big"):
        Keyhole(r_big=3, r_slot=5, slot_length=10)


def test_keyhole_missing_param_raises():
    with pytest.raises(ValidationError):
        Keyhole(r_big=5, r_slot=2)


# --- CircularSegment ---


def test_circular_segment_radius_height():
    s = CircularSegment(circle_r=10, height=4)
    # chord_r² = h(2R - h) = 4 * 16 = 64 → chord_r = 8 → chord = 16.
    assert s.chord == pytest.approx(16.0)
    # angle: h = R(1 - cos(angle/2)) → cos(angle/2) = 1 - 4/10 = 0.6
    # → angle/2 = acos(0.6) ≈ 53.13° → angle ≈ 106.26°.
    assert s.angle == pytest.approx(2 * math.degrees(math.acos(0.6)))


def test_circular_segment_radius_angle():
    s = CircularSegment(circle_r=10, angle=60)
    # h = 10 * (1 - cos(30°)) = 10(1 - √3/2) ≈ 1.34.
    assert s.height == pytest.approx(10 * (1 - math.cos(math.radians(30))))
    # chord = 2R sin(angle/2) = 20 sin(30°) = 10.
    assert s.chord == pytest.approx(10.0)


def test_circular_segment_chord_height():
    s = CircularSegment(chord=12, height=4)
    # chord_r² = h(2R - h) → 36 = 4(2R - 4) → 2R - 4 = 9 → R = 6.5.
    assert s.circle_r == pytest.approx(6.5)


def test_circular_segment_diameter_alias():
    s = CircularSegment(circle_d=20, height=4)
    assert s.circle_r == 10.0


def test_circular_segment_semicircle():
    s = CircularSegment(circle_r=10, angle=180)
    assert s.height == pytest.approx(10.0)
    assert s.chord == pytest.approx(20.0)


def test_circular_segment_emits():
    out = emit_str(CircularSegment(circle_r=10, height=4, fn=32))
    assert "intersection" in out
    assert "circle" in out
    assert "square" in out


def test_circular_segment_height_exceeds_diameter_raises():
    with pytest.raises(ValidationError):
        CircularSegment(circle_r=5, height=12)


# --- Annulus ---


def test_annulus_id_od_solves_thk():
    a = Annulus(id=8, od=12)
    assert a.thk == pytest.approx(2.0)


def test_annulus_id_thk_solves_od():
    a = Annulus(id=8, thk=2)
    assert a.od == pytest.approx(12.0)


def test_annulus_od_thk_solves_id():
    a = Annulus(od=12, thk=2)
    assert a.id == pytest.approx(8.0)


def test_annulus_bbox_matches_od():
    a = Annulus(id=8, od=12, fn=64)
    bb = bbox(a)
    assert bb.min[0] == pytest.approx(-6.0, abs=0.5)
    assert bb.max[0] == pytest.approx(6.0, abs=0.5)
    assert bb.min[1] == pytest.approx(-6.0, abs=0.5)
    assert bb.max[1] == pytest.approx(6.0, abs=0.5)


def test_annulus_emits_difference_of_circles():
    scad = emit_str(Annulus(id=8, od=12))
    assert "difference" in scad
    assert "circle" in scad


def test_annulus_inconsistent_overspec_raises():
    with pytest.raises(ValidationError):
        Annulus(id=8, od=12, thk=3)  # 12 != 8 + 6


def test_annulus_underspec_raises():
    with pytest.raises(ValidationError):
        Annulus(id=8)  # need at least one of (od, thk)


def test_annulus_negative_thk_raises():
    with pytest.raises(ValidationError):
        Annulus(id=8, thk=-1)


def test_annulus_id_at_or_above_od_raises():
    # id must be < od (positive thk requires id < od).
    with pytest.raises(ValidationError):
        Annulus(id=12, od=12)
    with pytest.raises(ValidationError):
        Annulus(id=14, od=12)


# --- Star ---


def test_star_5_point_bbox_top_tip_up():
    # A five-point star with one tip pointing up has max y = r_outer.
    s = Star(points=5, r_outer=10, r_inner=4)
    bb = bbox(s)
    assert bb.max[1] == pytest.approx(10.0, abs=1e-6)
    # Lower tips at angle 234° from +x give y = 10·sin(234°) ≈ −8.09.
    assert bb.min[1] == pytest.approx(10.0 * math.sin(math.radians(234)), abs=1e-6)


def test_star_6_point_bbox_symmetric():
    # An even-pointed star has tips at +y AND −y; bbox y-extent = ±r_outer.
    s = Star(points=6, r_outer=12, r_inner=6)
    bb = bbox(s)
    assert bb.max[1] == pytest.approx(12.0, abs=1e-6)
    assert bb.min[1] == pytest.approx(-12.0, abs=1e-6)


def test_star_d_outer_solves_r_outer():
    s = Star(points=5, d_outer=20, d_inner=8)
    assert s.r_outer == pytest.approx(10.0)
    assert s.r_inner == pytest.approx(4.0)


def test_star_mixed_radius_diameter():
    s = Star(points=5, r_outer=10, d_inner=8)
    assert s.r_inner == pytest.approx(4.0)
    assert s.d_outer == pytest.approx(20.0)


def test_star_emits_polygon():
    scad = emit_str(Star(points=5, r_outer=10, r_inner=4))
    assert "polygon" in scad


def test_star_too_few_points_raises():
    with pytest.raises(ValidationError):
        Star(points=2, r_outer=10, r_inner=4)


def test_star_inner_at_or_above_outer_raises():
    with pytest.raises(ValidationError):
        Star(points=5, r_outer=10, r_inner=10)
    with pytest.raises(ValidationError):
        Star(points=5, r_outer=10, r_inner=12)


def test_star_underspecified_raises():
    with pytest.raises(ValidationError):
        Star(points=5, r_outer=10)  # r_inner / d_inner missing


def test_star_non_integer_points_rejected():
    # `points` is declared int — passing 5.5 should fail.
    with pytest.raises(ValidationError):
        Star(points=5.5, r_outer=10, r_inner=4)
