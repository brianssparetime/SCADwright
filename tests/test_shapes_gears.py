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


def test_spur_gear_too_few_teeth_raises():
    with pytest.raises(ValidationError, match="teeth must be >= 6"):
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
