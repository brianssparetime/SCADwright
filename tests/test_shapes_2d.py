import math

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import (
    Arc,
    Keyhole,
    RoundedEndsArc,
    RoundedSlot,
    Sector,
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
