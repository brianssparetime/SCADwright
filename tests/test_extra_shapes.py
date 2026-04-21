import math

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import FilletRing, UShapeChannel


def test_fillet_ring_outwards_emits():
    r = FilletRing(id=10, od=20, base_angle=30, fn=24)
    out = emit_str(r)
    assert "difference" in out
    assert "cylinder" in out


def test_fillet_ring_inwards_emits():
    r = FilletRing(id=10, od=20, base_angle=30, slant="inwards", fn=24)
    out = emit_str(r)
    assert "difference" in out
    assert "cylinder" in out


def test_fillet_ring_slant_default_is_outwards():
    default = FilletRing(id=10, od=20, base_angle=30)
    outer = FilletRing(id=10, od=20, base_angle=30, slant="outwards")
    assert emit_str(default) == emit_str(outer)


def test_fillet_ring_inwards_differs_from_outwards():
    outer = emit_str(FilletRing(id=10, od=20, base_angle=30, slant="outwards"))
    inner = emit_str(FilletRing(id=10, od=20, base_angle=30, slant="inwards"))
    assert outer != inner


def test_fillet_ring_outwards_height_matches_full_cone():
    """Outwards slant = cone-minus-inner-cylinder; height extends all
    the way to the cone apex: `tan(base_angle) * od/2`."""
    r = FilletRing(id=10, od=20, base_angle=30, fn=64)
    expected_h = math.tan(math.radians(30)) * 20 / 2  # ≈ 5.774
    assert bbox(r).size[2] == pytest.approx(expected_h, abs=0.05)


def test_fillet_ring_inwards_height_is_wedge_only():
    """Inwards slant is just the wedge between id and od; height is
    `tan(base_angle) * (od - id) / 2`."""
    r = FilletRing(id=10, od=20, base_angle=30, slant="inwards", fn=64)
    expected_h = math.tan(math.radians(30)) * (20 - 10) / 2  # ≈ 2.887
    assert bbox(r).size[2] == pytest.approx(expected_h, abs=0.05)


def test_fillet_ring_bad_slant_raises():
    with pytest.raises(ValidationError):
        FilletRing(id=10, od=20, base_angle=30, slant="sideways")


def test_fillet_ring_id_ge_od_raises():
    with pytest.raises(ValidationError):
        FilletRing(id=20, od=10, base_angle=30)


def test_fillet_ring_bad_angle_raises():
    with pytest.raises(ValidationError):
        FilletRing(id=5, od=10, base_angle=120)


def test_ushape_channel_emits():
    u = UShapeChannel(wall_thk=2, channel_length=20, channel_width=10, channel_height=8)
    out = emit_str(u)
    assert "difference" in out
    assert "cube" in out


def test_ushape_channel_n_variant():
    u = UShapeChannel(wall_thk=2, channel_length=20, channel_width=10, channel_height=8, n_shape=True)
    out = emit_str(u)
    # Just confirm it builds; geometry differs from default.
    assert "cube" in out
