"""Tests for curve-based transforms: along_curve, bend, twist_copy."""

import math

import pytest

from scadwright import bbox, emit_str
from scadwright.primitives import cube, cylinder, sphere
from scadwright.shapes.curves.paths import helix_path

# Importing shapes triggers transform registration.
import scadwright.shapes  # noqa: F401


# --- along_curve ---


def test_along_curve_places_copies():
    path = [(0, 0, 0), (10, 0, 0), (20, 0, 0)]
    result = cube(2).along_curve(path=path, count=3)
    bb = bbox(result)
    # 3 cubes at x=0, x=10, x=20; each is 2 wide.
    assert bb.min[0] == pytest.approx(0.0, abs=1.0)
    assert bb.max[0] == pytest.approx(22.0, abs=1.0)


def test_along_curve_single_copy():
    path = [(0, 0, 0), (10, 0, 0)]
    result = sphere(r=1).along_curve(path=path, count=1)
    bb = bbox(result)
    assert bb.center[0] == pytest.approx(0.0, abs=0.5)


def test_along_curve_emits():
    path = [(0, 0, 0), (0, 0, 10), (0, 0, 20)]
    result = cube(1).along_curve(path=path, count=5)
    scad = emit_str(result)
    assert "union" in scad


# --- bend ---


def test_bend_wraps_geometry():
    bar = cube([2, 2, 20])
    bent = bar.bend(radius=10)
    scad = emit_str(bent)
    assert "union" in scad


def test_bend_bbox_differs_from_original():
    bar = cube([2, 2, 20])
    bent = bar.bend(radius=10)
    bb_orig = bbox(bar)
    bb_bent = bbox(bent)
    # The bent shape should have different extents than the straight bar.
    assert bb_bent.size[0] != pytest.approx(bb_orig.size[0], abs=0.5)


# --- twist_copy ---


def test_twist_copy_stacks():
    blade = cube([10, 2, 1])
    fan = blade.twist_copy(angle=45, count=4)
    bb = bbox(fan)
    # 4 copies stacked, each 1 unit tall.
    assert bb.size[2] == pytest.approx(4.0, abs=0.5)


def test_twist_copy_single():
    result = cube(5).twist_copy(angle=90, count=1)
    bb = bbox(result)
    assert bb.size[2] == pytest.approx(5.0, abs=0.1)


def test_twist_copy_emits():
    result = cube([5, 1, 2]).twist_copy(angle=30, count=6)
    scad = emit_str(result)
    assert "union" in scad
