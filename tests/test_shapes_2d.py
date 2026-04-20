import pytest

from scadwright import emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import Arc, RoundedEndsArc, RoundedSlot, Sector, regular_polygon, rounded_rect, rounded_square
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
