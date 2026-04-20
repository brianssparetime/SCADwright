"""Tests for curves subpackage: paths, sweep, helix, spring."""

import math

import pytest

from scadwright import bbox, emit_str
from scadwright.shapes.curves import (
    Helix,
    Spring,
    bezier_path,
    catmull_rom_path,
    circle_profile,
    helix_path,
    path_extrude,
)


# --- path generators ---


def test_helix_path_basic():
    path = helix_path(r=10, pitch=5, turns=2)
    assert len(path) > 10
    # First point at (r, 0, 0).
    assert path[0] == pytest.approx((10, 0, 0), abs=0.01)
    # Last point at z = turns * pitch.
    assert path[-1][2] == pytest.approx(10.0, abs=0.01)


def test_helix_path_radius():
    path = helix_path(r=10, pitch=5, turns=1)
    for x, y, z in path:
        r = math.sqrt(x**2 + y**2)
        assert r == pytest.approx(10.0, abs=0.01)


def test_bezier_path_endpoints():
    pts = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
    path = bezier_path(pts, steps=10)
    assert path[0] == pytest.approx((0, 0, 0))
    assert path[-1] == pytest.approx((0, 10, 0))


def test_bezier_path_wrong_count_raises():
    with pytest.raises(ValueError, match="exactly 4"):
        bezier_path([(0, 0, 0), (1, 0, 0)])


def test_catmull_rom_passes_through_points():
    pts = [(0, 0, 0), (10, 5, 0), (20, 0, 0), (30, 5, 0)]
    path = catmull_rom_path(pts, steps_per_segment=8)
    # The curve should pass through (or very near) each input point.
    for pt in pts:
        dists = [math.sqrt(sum((a - b) ** 2 for a, b in zip(pt, p))) for p in path]
        assert min(dists) < 0.1


def test_catmull_rom_two_points():
    path = catmull_rom_path([(0, 0, 0), (10, 0, 0)], steps_per_segment=4)
    assert len(path) == 5
    assert path[0] == pytest.approx((0, 0, 0))
    assert path[-1] == pytest.approx((10, 0, 0))


def test_catmull_rom_too_few_raises():
    with pytest.raises(ValueError, match="at least 2"):
        catmull_rom_path([(0, 0, 0)])


# --- circle_profile ---


def test_circle_profile():
    prof = circle_profile(5, segments=8)
    assert len(prof) == 8
    for x, y in prof:
        assert math.sqrt(x**2 + y**2) == pytest.approx(5.0, abs=0.01)


# --- path_extrude ---


def test_path_extrude_straight():
    """Sweep a square along a straight z-axis path."""
    profile = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
    path = [(0, 0, 0), (0, 0, 10)]
    result = path_extrude(profile, path)
    bb = bbox(result)
    assert bb.size[2] == pytest.approx(10.0, abs=0.1)


def test_path_extrude_emits_valid_scad():
    profile = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
    path = [(0, 0, 0), (0, 0, 5), (5, 0, 10)]
    result = path_extrude(profile, path)
    scad = emit_str(result)
    assert "polyhedron" in scad


def test_path_extrude_closed():
    """Closed sweep (torus-like): no end caps."""
    profile = circle_profile(1, segments=8)
    path = [
        (10 * math.cos(a), 10 * math.sin(a), 0)
        for a in [i * 2 * math.pi / 20 for i in range(20)]
    ]
    result = path_extrude(profile, path, closed=True)
    scad = emit_str(result)
    assert "polyhedron" in scad


def test_path_extrude_too_few_profile_raises():
    with pytest.raises(ValueError, match="at least 3"):
        path_extrude([(0, 0), (1, 0)], [(0, 0, 0), (0, 0, 1)])


def test_path_extrude_too_few_path_raises():
    with pytest.raises(ValueError, match="at least 2"):
        path_extrude([(1, 0), (0, 1), (-1, 0)], [(0, 0, 0)])


# --- Helix Component ---


def test_helix_builds():
    h = Helix(r=10, wire_r=1, pitch=5, turns=3)
    scad = emit_str(h)
    assert "polyhedron" in scad


def test_helix_bbox_reasonable():
    h = Helix(r=10, wire_r=1, pitch=5, turns=2)
    bb = bbox(h)
    # Helix radius 10 + wire radius 1 -> extent ~22 in x and y.
    assert bb.size[0] == pytest.approx(22.0, abs=1.0)
    assert bb.size[1] == pytest.approx(22.0, abs=1.0)
    # Height: 2 turns * pitch 5 = 10, plus wire radius top/bottom.
    assert bb.size[2] == pytest.approx(12.0, abs=1.0)


def test_helix_attributes():
    h = Helix(r=10, wire_r=1, pitch=5, turns=3)
    assert h.r == 10
    assert h.wire_r == 1
    assert h.pitch == 5
    assert h.turns == 3


# --- Spring Component ---


def test_spring_builds():
    s = Spring(r=8, wire_r=0.5, pitch=3, turns=5)
    scad = emit_str(s)
    assert "polyhedron" in scad


def test_spring_flat_ends():
    s = Spring(r=8, wire_r=0.5, pitch=3, turns=5, flat_ends=True)
    bb = bbox(s)
    # With flat ends, bottom and top should be near z=0 and z=turns*pitch.
    assert bb.min[2] == pytest.approx(-0.5, abs=1.0)
    assert bb.max[2] == pytest.approx(15.5, abs=1.0)


def test_spring_no_flat_ends():
    s = Spring(r=8, wire_r=0.5, pitch=3, turns=5, flat_ends=False)
    scad = emit_str(s)
    assert "polyhedron" in scad
