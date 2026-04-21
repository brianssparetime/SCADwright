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


def test_spur_gear_published_radii_match_formula():
    """pitch_r = m·n/2; outer_r = pitch_r + m; root_r = pitch_r - 1.25m;
    base_r = pitch_r * cos(pressure_angle°)."""
    for module, teeth, pa in [(1, 20, 20.0), (1.5, 32, 14.5), (3, 12, 25.0)]:
        g = SpurGear(module=module, teeth=teeth, h=5, pressure_angle=pa)
        pitch_r = module * teeth / 2
        assert g.pitch_r == pytest.approx(pitch_r)
        assert g.outer_r == pytest.approx(pitch_r + module)
        assert g.root_r == pytest.approx(pitch_r - 1.25 * module)
        assert g.base_r == pytest.approx(pitch_r * math.cos(math.radians(pa)))


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


# --- pure-math: involute_point, involute_intersect_angle, gear_dimensions ---


def test_involute_point_starts_at_base_circle():
    """At t=0, the involute originates at (base_r, 0)."""
    from scadwright.shapes.gears.involute import involute_point

    x, y = involute_point(base_r=10.0, angle=0.0)
    assert x == pytest.approx(10.0)
    assert y == pytest.approx(0.0)


def test_involute_intersect_angle_clamps_at_base_circle():
    """Targets at or inside the base circle return 0 — the involute
    can't intersect any radius smaller than the base."""
    from scadwright.shapes.gears.involute import involute_intersect_angle

    assert involute_intersect_angle(base_r=10.0, target_r=10.0) == 0.0
    assert involute_intersect_angle(base_r=10.0, target_r=5.0) == 0.0


def test_involute_intersect_angle_known_value():
    """t = sqrt((target/base)^2 - 1). For target=2*base, t = sqrt(3)."""
    from scadwright.shapes.gears.involute import involute_intersect_angle

    assert involute_intersect_angle(base_r=10.0, target_r=20.0) == pytest.approx(math.sqrt(3))


def test_gear_dimensions_pitch_r_scales_linearly_in_module_and_teeth():
    pr_base, _, _, _ = gear_dimensions(module=1, teeth=20)
    pr_mod2, _, _, _ = gear_dimensions(module=2, teeth=20)
    pr_t40, _, _, _ = gear_dimensions(module=1, teeth=40)
    assert pr_mod2 == pytest.approx(2 * pr_base)
    assert pr_t40 == pytest.approx(2 * pr_base)


def test_gear_dimensions_base_pitch_ratio_is_cos_pressure_angle():
    for pa in (14.5, 20.0, 25.0):
        pr, br, _, _ = gear_dimensions(module=1, teeth=20, pressure_angle=pa)
        assert br / pr == pytest.approx(math.cos(math.radians(pa)))
