"""Tests for curves subpackage: paths, sweep, helix, spring."""

import math

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes.curves import (
    Helix,
    Spring,
    arc_path,
    bezier_2d,
    bezier_path,
    catmull_rom_2d,
    catmull_rom_path,
    circle_profile,
    composite_bezier_path,
    helix_path,
    path_extrude,
    polygon_profile,
    rounded_rect_profile,
    square_profile,
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
    with pytest.raises(ValidationError, match="exactly 4"):
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
    with pytest.raises(ValidationError, match="at least 2"):
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
    with pytest.raises(ValidationError, match="at least 3"):
        path_extrude([(0, 0), (1, 0)], [(0, 0, 0), (0, 0, 1)])


def test_path_extrude_too_few_path_raises():
    with pytest.raises(ValidationError, match="at least 2"):
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


def test_spring_flat_ends_geometry_differs():
    """flat_ends adds material at the top/bottom; same params should
    nonetheless produce a different geometry tree."""
    from scadwright import tree_hash

    flat = Spring(r=8, wire_r=0.5, pitch=3, turns=5, flat_ends=True)
    nopad = Spring(r=8, wire_r=0.5, pitch=3, turns=5, flat_ends=False)
    assert tree_hash(flat) != tree_hash(nopad)


# --- composite_bezier_path ---


def test_composite_bezier_single_segment_matches_bezier_path():
    seg = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
    single = bezier_path(seg, steps=16)
    composite = composite_bezier_path([seg], steps_per_segment=16)
    assert single == composite


def test_composite_bezier_two_segments_concatenate():
    seg1 = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
    seg2 = [(0, 10, 0), (-10, 10, 0), (-10, 0, 0), (0, 0, 0)]
    composite = composite_bezier_path([seg1, seg2], steps_per_segment=8)
    # First segment: 9 points (steps_per_segment + 1 inclusive). Second
    # segment: 8 points (skips the duplicated boundary). Total: 17.
    assert len(composite) == 17
    # The closing point of the loop should equal the start.
    assert composite[0] == pytest.approx((0, 0, 0))
    assert composite[-1] == pytest.approx((0, 0, 0))


def test_composite_bezier_mismatched_boundary_raises():
    seg1 = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
    seg2 = [(1, 1, 1), (5, 0, 0), (5, 5, 0), (0, 5, 0)]  # doesn't start at seg1's end
    with pytest.raises(ValidationError, match="C0 continuity"):
        composite_bezier_path([seg1, seg2])


def test_composite_bezier_wrong_segment_size_raises():
    with pytest.raises(ValidationError, match="exactly 4"):
        composite_bezier_path([[(0, 0, 0), (1, 0, 0)]])


def test_composite_bezier_empty_raises():
    with pytest.raises(ValidationError, match="non-empty"):
        composite_bezier_path([])


def test_composite_bezier_boundary_tolerance():
    """Boundary anchors within 1e-6 should pass; outside should raise."""
    seg1 = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
    # Within tolerance: 1e-7 drift is fine.
    seg2_ok = [(1e-7, 10, 0), (-10, 10, 0), (-10, 0, 0), (0, 0, 0)]
    composite_bezier_path([seg1, seg2_ok])  # no raise
    # Outside tolerance: 1e-5 drift is too much.
    seg2_bad = [(1e-5, 10, 0), (-10, 10, 0), (-10, 0, 0), (0, 0, 0)]
    with pytest.raises(ValidationError):
        composite_bezier_path([seg1, seg2_bad])


# --- arc_path ---


def test_arc_path_xy_quarter():
    """0° to 90° in XY plane: starts at (r, 0, 0), ends at (0, r, 0)."""
    arc = arc_path(center=(0, 0, 0), radius=10, start_angle=0, end_angle=90, steps=4)
    assert len(arc) == 5
    assert arc[0] == pytest.approx((10, 0, 0), abs=1e-9)
    assert arc[-1] == pytest.approx((0, 10, 0), abs=1e-9)


def test_arc_path_full_circle_closes():
    """360° arc: last point ≈ first point."""
    arc = arc_path(center=(0, 0, 0), radius=5, start_angle=0, end_angle=360, steps=8)
    assert arc[0] == pytest.approx(arc[-1], abs=1e-9)


def test_arc_path_centered_off_origin():
    arc = arc_path(center=(5, 5, 5), radius=2, start_angle=0, end_angle=90, steps=2)
    # Every point lies on the circle of radius 2 around (5, 5, 5).
    for x, y, z in arc:
        d = math.sqrt((x - 5) ** 2 + (y - 5) ** 2 + (z - 5) ** 2)
        assert d == pytest.approx(2, abs=1e-9)


def test_arc_path_normal_x_yz_plane():
    """normal=(1, 0, 0): arc lies in YZ plane. Reference falls back to +Y."""
    arc = arc_path(
        center=(0, 0, 0), radius=10, start_angle=0, end_angle=90,
        normal=(1, 0, 0), steps=4,
    )
    # 0° points along +Y (the fallback reference); 90° points along +Z.
    assert arc[0] == pytest.approx((0, 10, 0), abs=1e-9)
    assert arc[-1] == pytest.approx((0, 0, 10), abs=1e-9)


def test_arc_path_normal_y_uses_x_reference():
    """normal=(0, 1, 0): +X is perpendicular to normal, so used as reference."""
    arc = arc_path(
        center=(0, 0, 0), radius=10, start_angle=0, end_angle=90,
        normal=(0, 1, 0), steps=4,
    )
    # 0° points along +X; 90° rotates CCW about +Y, landing along -Z.
    assert arc[0] == pytest.approx((10, 0, 0), abs=1e-9)
    assert arc[-1] == pytest.approx((0, 0, -10), abs=1e-9)


def test_arc_path_negative_sweep():
    """end_angle < start_angle sweeps clockwise."""
    arc = arc_path(center=(0, 0, 0), radius=10, start_angle=0, end_angle=-90, steps=2)
    assert arc[-1] == pytest.approx((0, -10, 0), abs=1e-9)


def test_arc_path_zero_radius_raises():
    with pytest.raises(ValidationError, match="radius"):
        arc_path(center=(0, 0, 0), radius=0, start_angle=0, end_angle=90)


def test_arc_path_zero_sweep_raises():
    with pytest.raises(ValidationError, match="zero length"):
        arc_path(center=(0, 0, 0), radius=10, start_angle=45, end_angle=45)


def test_arc_path_zero_normal_raises():
    with pytest.raises(ValidationError, match="non-zero"):
        arc_path(
            center=(0, 0, 0), radius=10, start_angle=0, end_angle=90,
            normal=(0, 0, 0),
        )


# --- profiles ---


def test_square_profile_centered():
    pts = square_profile(10)
    assert len(pts) == 4
    assert pts == [(-5, -5), (5, -5), (5, 5), (-5, 5)]


def test_square_profile_non_centered():
    pts = square_profile((10, 5), center=False)
    assert pts == [(0, 0), (10, 0), (10, 5), (0, 5)]


def test_square_profile_tuple_size():
    pts = square_profile((20, 4))
    # Centered at origin: w=20, h=4.
    assert pts == [(-10, -2), (10, -2), (10, 2), (-10, 2)]


def test_square_profile_invalid_size_raises():
    with pytest.raises(ValidationError):
        square_profile(-1)
    with pytest.raises(ValidationError):
        square_profile((0, 5))


def test_polygon_profile_hexagon():
    pts = polygon_profile(6, 5)
    assert len(pts) == 6
    # First vertex on +X.
    assert pts[0] == pytest.approx((5, 0), abs=1e-9)
    # Each vertex on the circle of radius 5.
    for x, y in pts:
        assert math.sqrt(x * x + y * y) == pytest.approx(5, abs=1e-9)


def test_polygon_profile_rotation():
    pts = polygon_profile(4, 5, rotate=45)
    # 4-gon rotated 45° has first vertex at (5/√2, 5/√2).
    expected = (5 / math.sqrt(2), 5 / math.sqrt(2))
    assert pts[0] == pytest.approx(expected, abs=1e-9)


def test_polygon_profile_too_few_sides_raises():
    with pytest.raises(ValidationError, match="sides"):
        polygon_profile(2, 5)


def test_polygon_profile_invalid_radius_raises():
    with pytest.raises(ValidationError, match="positive"):
        polygon_profile(6, 0)


def test_rounded_rect_profile_basic():
    pts = rounded_rect_profile(20, 10, 2, segments_per_corner=4)
    # 4 corners × (4 + 1 = 5 points each) = 20 points.
    assert len(pts) == 20
    # Bbox should be (-10, -5) to (10, 5).
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert min(xs) == pytest.approx(-10, abs=1e-9)
    assert max(xs) == pytest.approx(10, abs=1e-9)
    assert min(ys) == pytest.approx(-5, abs=1e-9)
    assert max(ys) == pytest.approx(5, abs=1e-9)


def test_rounded_rect_profile_zero_radius_is_rectangle():
    pts = rounded_rect_profile(20, 10, 0)
    assert len(pts) == 4
    assert (-10, -5) in pts
    assert (10, 5) in pts


def test_rounded_rect_profile_radius_too_big_raises():
    with pytest.raises(ValidationError, match="exceeds half"):
        rounded_rect_profile(10, 10, 6)


def test_profiles_compose_with_path_extrude():
    """Each profile should sweep cleanly into a polyhedron via path_extrude."""
    path = [(0, 0, 0), (0, 0, 5), (0, 0, 10)]
    for profile in (
        square_profile(4),
        polygon_profile(6, 3),
        rounded_rect_profile(6, 4, 1),
        circle_profile(2, segments=12),
    ):
        result = path_extrude(profile, path)
        assert "polyhedron" in emit_str(result)


# --- bezier_2d ---


def test_bezier_2d_open_emits_polygon():
    poly = bezier_2d([[(0, 0), (5, 0), (5, 5), (0, 5)]], steps_per_segment=8)
    scad = emit_str(poly)
    assert "polygon" in scad


def test_bezier_2d_closed_loop_validates():
    """Closed loop where last point equals first works."""
    loop = bezier_2d(
        [
            [(0, 0), (5, 0), (5, 5), (0, 5)],
            [(0, 5), (-5, 5), (-5, 0), (0, 0)],
        ],
        closed=True,
        steps_per_segment=4,
    )
    assert "polygon" in emit_str(loop)


def test_bezier_2d_closed_mismatch_raises():
    """closed=True with non-loop curve raises."""
    with pytest.raises(ValidationError, match="closed=True"):
        bezier_2d(
            [[(0, 0), (5, 0), (5, 5), (0, 5)]],  # ends at (0, 5), not (0, 0)
            closed=True,
        )


def test_bezier_2d_extrudes():
    """A closed bezier_2d composes with linear_extrude."""
    loop = bezier_2d(
        [
            [(0, 0), (5, 0), (5, 5), (0, 5)],
            [(0, 5), (-5, 5), (-5, 0), (0, 0)],
        ],
        closed=True,
        steps_per_segment=8,
    )
    solid = loop.linear_extrude(height=3)
    bb = bbox(solid)
    assert bb.size[2] == pytest.approx(3, abs=0.01)


def test_bezier_2d_empty_raises():
    with pytest.raises(ValidationError, match="non-empty"):
        bezier_2d([])


def test_bezier_2d_wrong_segment_size_raises():
    with pytest.raises(ValidationError, match="exactly 4"):
        bezier_2d([[(0, 0), (1, 0)]])


# --- catmull_rom_2d ---


def test_catmull_rom_2d_open():
    poly = catmull_rom_2d([(0, 0), (10, 5), (20, 0), (30, 5)], steps_per_segment=4)
    assert "polygon" in emit_str(poly)


def test_catmull_rom_2d_closed():
    """A closed Catmull-Rom polygon loops back without straight closing edge."""
    poly = catmull_rom_2d(
        [(0, 0), (10, 5), (20, 0), (10, -5)],
        closed=True,
        steps_per_segment=4,
    )
    assert "polygon" in emit_str(poly)


def test_catmull_rom_2d_extrudes():
    poly = catmull_rom_2d([(0, 0), (10, 5), (20, 0), (10, -5)], closed=True)
    solid = poly.linear_extrude(height=2)
    bb = bbox(solid)
    assert bb.size[2] == pytest.approx(2, abs=0.01)


def test_catmull_rom_2d_too_few_raises():
    with pytest.raises(ValidationError, match="at least 2"):
        catmull_rom_2d([(0, 0)])


def test_catmull_rom_2d_closed_too_few_raises():
    with pytest.raises(ValidationError, match="closed=True requires"):
        catmull_rom_2d([(0, 0), (1, 0)], closed=True)
