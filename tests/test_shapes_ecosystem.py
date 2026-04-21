"""Tests for ecosystem shapes: Gridfinity, extrusion profiles."""

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import ExtrusionProfile, GridfinityBase, GridfinityBin


# --- GridfinityBase ---


def test_gridfinity_base_1x1():
    b = GridfinityBase(grid_x=1, grid_y=1)
    bb = bbox(b)
    assert bb.size[0] == pytest.approx(42.0, abs=0.5)
    assert bb.size[1] == pytest.approx(42.0, abs=0.5)


def test_gridfinity_base_3x2():
    b = GridfinityBase(grid_x=3, grid_y=2)
    bb = bbox(b)
    assert bb.size[0] == pytest.approx(126.0, abs=0.5)
    assert bb.size[1] == pytest.approx(84.0, abs=0.5)


def test_gridfinity_base_emits():
    scad = emit_str(GridfinityBase(grid_x=2, grid_y=2))
    assert "difference" in scad


def test_gridfinity_base_invalid_raises():
    with pytest.raises(ValidationError, match="grid_x: must be >= 1"):
        GridfinityBase(grid_x=0, grid_y=1)


# --- GridfinityBin ---


def test_gridfinity_bin_builds():
    b = GridfinityBin(grid_x=1, grid_y=1, height_units=3)
    scad = emit_str(b)
    assert "difference" in scad


def test_gridfinity_bin_with_dividers():
    b = GridfinityBin(grid_x=2, grid_y=1, height_units=3, dividers_x=2)
    scad = emit_str(b)
    assert "union" in scad


def test_gridfinity_bin_publishes_dims():
    b = GridfinityBin(grid_x=2, grid_y=1, height_units=3)
    assert b.outer_w == pytest.approx(83.5, abs=0.5)
    assert b.total_h == pytest.approx(25.4, abs=0.5)


# --- ExtrusionProfile ---


def test_extrusion_profile_2020():
    p = ExtrusionProfile(size=20)
    scad = emit_str(p)
    assert "difference" in scad


def test_extrusion_profile_bbox():
    p = ExtrusionProfile(size=20)
    bb = bbox(p)
    assert bb.size[0] == pytest.approx(20.0, abs=0.1)
    assert bb.size[1] == pytest.approx(20.0, abs=0.1)


def test_extrusion_profile_multi_slot():
    p = ExtrusionProfile(size=40, slots=2)
    scad = emit_str(p)
    assert "difference" in scad
