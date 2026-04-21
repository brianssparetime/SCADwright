"""Tests for gears subpackage."""

import math

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import (
    BevelGear,
    Rack,
    RingGear,
    SpurGear,
    Worm,
    WormGear,
    gear_dimensions,
)


# --- involute math ---


def test_gear_dimensions_m1_20t():
    pr, br, otr, rr = gear_dimensions(module=1, teeth=20)
    assert pr == pytest.approx(10.0)
    assert otr == pytest.approx(11.0)  # pitch_r + module
    assert rr == pytest.approx(8.75)   # pitch_r - 1.25*module
    assert br == pytest.approx(10 * math.cos(math.radians(20)), abs=0.01)


# --- SpurGear ---


def test_spur_gear_builds():
    g = SpurGear(module=2, teeth=20, h=5)
    scad = emit_str(g)
    assert "linear_extrude" in scad


def test_spur_gear_publishes_radii():
    g = SpurGear(module=2, teeth=20, h=5)
    assert g.pitch_r == pytest.approx(20.0)
    assert g.outer_r == pytest.approx(22.0)


def test_spur_gear_bbox_reasonable():
    g = SpurGear(module=2, teeth=20, h=5)
    bb = bbox(g)
    # Outer diameter ~44, height 5.
    assert bb.size[0] == pytest.approx(44.0, abs=2.0)
    assert bb.size[2] == pytest.approx(5.0, abs=0.1)


def test_spur_gear_helical():
    g = SpurGear(module=2, teeth=20, h=5, helix_angle=15)
    scad = emit_str(g)
    assert "twist" in scad


def _extract_twist(scad: str) -> float:
    """Pull the numeric twist value out of a linear_extrude SCAD line."""
    import re

    m = re.search(r"twist\s*=\s*(-?\d+\.?\d*)", scad)
    assert m, f"no twist= in SCAD output:\n{scad}"
    return float(m.group(1))


def test_spur_gear_helical_twist_value_correct():
    """Twist must be 360 * h * tan(beta) / (pi * pitch_d), not just helix_angle."""
    # m=2, teeth=20 -> pitch_d=40. h=10, beta=15 deg.
    # Expected: 360 * 10 * tan(15 deg) / (pi * 40) = 7.6727...
    g = SpurGear(module=2, teeth=20, h=10, helix_angle=15)
    twist = _extract_twist(emit_str(g))
    expected = 360.0 * 10 * math.tan(math.radians(15)) / (math.pi * 40)
    assert twist == pytest.approx(expected, rel=1e-4)
    assert twist == pytest.approx(7.6727, abs=0.01)  # sanity


def test_spur_gear_helical_twist_scales_with_height():
    """Doubling h should double the total twist."""
    g_short = SpurGear(module=2, teeth=20, h=10, helix_angle=15)
    g_tall = SpurGear(module=2, teeth=20, h=20, helix_angle=15)
    twist_short = _extract_twist(emit_str(g_short))
    twist_tall = _extract_twist(emit_str(g_tall))
    assert twist_tall == pytest.approx(2 * twist_short, rel=1e-4)


def test_spur_gear_helical_twist_depends_on_pitch_d():
    """Larger pitch_d (more teeth) gives smaller twist for same h, beta."""
    g_small = SpurGear(module=2, teeth=20, h=10, helix_angle=15)  # pitch_d = 40
    g_large = SpurGear(module=2, teeth=40, h=10, helix_angle=15)  # pitch_d = 80
    twist_small = _extract_twist(emit_str(g_small))
    twist_large = _extract_twist(emit_str(g_large))
    # 2x pitch_d -> half the twist.
    assert twist_large == pytest.approx(twist_small / 2, rel=1e-4)


def test_spur_gear_negative_helix_angle_gives_negative_twist():
    g = SpurGear(module=2, teeth=20, h=10, helix_angle=-15)
    twist = _extract_twist(emit_str(g))
    assert twist < 0


def test_spur_gear_too_few_teeth_raises():
    with pytest.raises(ValidationError, match="teeth: must be >= 6"):
        SpurGear(module=1, teeth=3, h=5)


# --- Rack ---


def test_rack_builds():
    r = Rack(module=2, teeth=10, length=62.8, h=5)
    scad = emit_str(r)
    assert "linear_extrude" in scad


def test_rack_bbox():
    r = Rack(module=2, teeth=10, length=62.8, h=5)
    bb = bbox(r)
    assert bb.size[0] == pytest.approx(62.8, abs=1.0)
    assert bb.size[2] == pytest.approx(5.0, abs=0.1)


# --- RingGear ---


def test_ring_gear_builds():
    rg = RingGear(module=2, teeth=30, h=5, rim_thk=3)
    scad = emit_str(rg)
    assert "linear_extrude" in scad


def test_ring_gear_publishes_radii():
    rg = RingGear(module=2, teeth=30, h=5, rim_thk=3)
    assert rg.pitch_r == pytest.approx(30.0)


# --- BevelGear ---


def test_bevel_gear_builds():
    bg = BevelGear(module=2, teeth=20, h=5)
    scad = emit_str(bg)
    assert "linear_extrude" in scad
    assert "scale" in scad


def test_bevel_gear_publishes_radii():
    bg = BevelGear(module=2, teeth=20, h=5)
    assert bg.pitch_r == pytest.approx(20.0)


# --- Worm ---


def test_worm_builds():
    w = Worm(module=2, length=20, shaft_r=5)
    scad = emit_str(w)
    assert "polyhedron" in scad


def test_worm_publishes_pitch():
    w = Worm(module=2, length=20, shaft_r=5)
    assert w.pitch == pytest.approx(2 * math.pi)


# --- WormGear ---


def test_worm_gear_builds():
    wg = WormGear(module=2, teeth=30, h=5)
    scad = emit_str(wg)
    assert "linear_extrude" in scad
