"""Tests for ``loft`` and ``resample_profile``."""

import math

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import (
    circle_profile,
    loft,
    polygon_profile,
    resample_profile,
    square_profile,
)


# --- loft: ruled mode ---


def test_loft_two_section_circle_to_square():
    """Two-section straight loft along +Z. Circle r=5 at z=0, square
    8×8 at z=10. Bbox xy is dominated by the circle (r=5 > 8/2)."""
    sections = [
        circle_profile(5, segments=24),
        resample_profile(square_profile(8), 24),
    ]
    path = [(0, 0, 0), (0, 0, 10)]
    shape = loft(sections, path)
    bb = bbox(shape)
    assert bb.min[2] == pytest.approx(0.0)
    assert bb.max[2] == pytest.approx(10.0)
    # xy is dominated by the circle (r=5 wider than the square's r=4).
    assert bb.min[0] == pytest.approx(-5.0, abs=0.1)
    assert bb.max[0] == pytest.approx(5.0, abs=0.1)


def test_loft_three_section_taper():
    """Three circles of decreasing radius along a curved 3D path. The
    sections sit perpendicular to the path tangent, so a tilted first
    section can dip below z=0 — the bbox z range is generally wider
    than the path's z range."""
    sections = [
        circle_profile(5, segments=16),
        circle_profile(3, segments=16),
        circle_profile(1, segments=16),
    ]
    path = [(0, 0, 0), (5, 0, 5), (5, 5, 10)]
    shape = loft(sections, path)
    bb = bbox(shape)
    # Path z range is 0..10, sections add some overshoot (≤ first
    # section's radius in each direction). Check the bbox at least
    # covers the path's z range.
    assert bb.min[2] <= 0.0
    assert bb.max[2] >= 10.0


def test_loft_closed_ring():
    """closed=True connects the last section back to the first; no end
    caps are emitted."""
    sections = [
        circle_profile(2, segments=12),
        circle_profile(3, segments=12),
        circle_profile(2, segments=12),
        circle_profile(3, segments=12),
    ]
    # A square-ish ring path in the XY plane.
    path = [(10, 0, 0), (0, 10, 0), (-10, 0, 0), (0, -10, 0)]
    shape = loft(sections, path, closed=True)
    scad = emit_str(shape)
    assert "polyhedron" in scad


def test_loft_path_extrude_equivalence_for_constant_section():
    """Lofting the same profile at every path point produces the same
    polyhedron structure as path_extrude — bbox should match."""
    from scadwright.shapes import path_extrude
    profile = circle_profile(2, segments=12)
    path = [(0, 0, 0), (0, 0, 5), (0, 0, 10)]
    via_loft = loft([profile, profile, profile], path)
    via_extrude = path_extrude(profile, path)
    assert bbox(via_loft).min == pytest.approx(bbox(via_extrude).min, abs=0.01)
    assert bbox(via_loft).max == pytest.approx(bbox(via_extrude).max, abs=0.01)


# --- loft: smooth mode ---


def test_loft_smooth_produces_denser_mesh():
    """smooth=True samples sub-sections via Catmull-Rom, producing more
    triangles than the ruled version with the same input sections."""
    sections = [
        circle_profile(5, segments=12),
        circle_profile(3, segments=12),
        circle_profile(7, segments=12),
    ]
    path = [(0, 0, 0), (0, 0, 5), (0, 0, 10)]
    ruled = loft(sections, path, smooth=False)
    smooth = loft(sections, path, smooth=True, smooth_steps=8)
    # The smooth polyhedron should have many more triangles than ruled.
    # SCAD output line count is a proxy.
    assert emit_str(smooth).count("[") > emit_str(ruled).count("[")


def test_loft_smooth_passes_through_input_sections():
    """Catmull-Rom passes through control points. The smooth loft's
    bbox should at least cover the input sections' bbox (modulo a small
    overshoot from spline curvature)."""
    sections = [
        circle_profile(5, segments=12),
        circle_profile(3, segments=12),
        circle_profile(5, segments=12),
    ]
    path = [(0, 0, 0), (0, 0, 5), (0, 0, 10)]
    smooth = loft(sections, path, smooth=True)
    bb = bbox(smooth)
    # x/y extent at least covers the widest section (r=5).
    assert bb.max[0] >= 5.0 - 0.01
    assert bb.min[0] <= -5.0 + 0.01


# --- error paths ---


def test_loft_closed_smooth_ring():
    """closed=True with smooth=True produces a periodic Catmull-Rom
    track per vertex — the smoothed mesh wraps cleanly with no end
    caps and exactly ``n_sect * n_profile * 2`` side triangles."""
    import math
    from scadwright.ast.primitives import Polyhedron
    sections = [
        circle_profile(2, segments=12),
        circle_profile(3, segments=12),
        circle_profile(2, segments=12),
        circle_profile(3, segments=12),
    ]
    # Four-point ring path in the XY plane.
    path = [
        (10 * math.cos(a), 10 * math.sin(a), 0)
        for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)
    ]
    smooth_steps = 8
    shape = loft(sections, path, closed=True, smooth=True, smooth_steps=smooth_steps)
    bb = bbox(shape)
    # The ring sits in z near 0 with the largest cross-section reaching ±3.
    assert bb.min[2] <= -2.5
    assert bb.max[2] >= 2.5

    # Verify no end-cap triangles: for closed=True the face list should
    # be exactly n_sect * n_profile * 2 (each quad split into 2 tris,
    # for every adjacent-section pair around the closed loop).
    poly = shape
    while not isinstance(poly, Polyhedron):
        poly = poly.child
    n_sect = len(sections) * smooth_steps     # closed loop: n * steps samples
    n_profile = len(sections[0])
    expected_face_count = n_sect * n_profile * 2
    assert len(poly.faces) == expected_face_count, (
        f"Expected {expected_face_count} side triangles for "
        f"closed-loop smooth loft, got {len(poly.faces)}"
    )


def test_loft_closed_smooth_two_sections_raises():
    """smooth+closed needs >= 3 sections for a periodic Catmull-Rom."""
    sections = [circle_profile(2, segments=8), circle_profile(3, segments=8)]
    path = [(0, 0, 0), (5, 0, 0)]
    with pytest.raises(ValidationError, match="at least 3"):
        loft(sections, path, smooth=True, closed=True)


def test_loft_mismatched_vertex_counts_raises():
    sections = [
        circle_profile(2, segments=8),
        circle_profile(3, segments=12),
    ]
    path = [(0, 0, 0), (0, 0, 5)]
    with pytest.raises(ValidationError, match="section.*points"):
        loft(sections, path)


def test_loft_sections_path_length_mismatch_raises():
    sections = [circle_profile(2, segments=8), circle_profile(3, segments=8)]
    path = [(0, 0, 0), (0, 0, 5), (0, 0, 10)]
    with pytest.raises(ValidationError, match="same length"):
        loft(sections, path)


def test_loft_too_few_sections_raises():
    sections = [circle_profile(2, segments=8)]
    path = [(0, 0, 0)]
    with pytest.raises(ValidationError, match="at least 2"):
        loft(sections, path)


def test_loft_section_too_few_points_raises():
    sections = [[(0, 0), (1, 0)], [(0, 0), (1, 0)]]
    path = [(0, 0, 0), (0, 0, 5)]
    with pytest.raises(ValidationError, match="at least 3 points"):
        loft(sections, path)


# --- resample_profile ---


def test_resample_profile_returns_n_points():
    src = polygon_profile(sides=4, r=5)
    out = resample_profile(src, 16)
    assert len(out) == 16


def test_resample_profile_preserves_perimeter():
    """Total perimeter of the resampled profile matches the source
    perimeter within floating-point tolerance."""
    src = polygon_profile(sides=6, r=10)
    src_perim = sum(
        math.hypot(src[(i + 1) % len(src)][0] - src[i][0],
                   src[(i + 1) % len(src)][1] - src[i][1])
        for i in range(len(src))
    )
    out = resample_profile(src, 24)
    out_perim = sum(
        math.hypot(out[(i + 1) % len(out)][0] - out[i][0],
                   out[(i + 1) % len(out)][1] - out[i][1])
        for i in range(len(out))
    )
    assert out_perim == pytest.approx(src_perim, rel=1e-6)


def test_resample_profile_first_point_matches_source():
    src = circle_profile(5, segments=12)
    out = resample_profile(src, 24)
    assert out[0] == pytest.approx(src[0])


def test_resample_profile_n_too_small_raises():
    src = circle_profile(5, segments=12)
    with pytest.raises(ValidationError, match="n must be >= 3"):
        resample_profile(src, 2)


def test_resample_profile_source_too_short_raises():
    with pytest.raises(ValidationError, match="at least 3 points"):
        resample_profile([(0, 0), (1, 0)], 8)


def test_resample_profile_lets_loft_mix_profiles():
    """resample_profile is the intended fix for vertex-count
    mismatches between sections."""
    n = 16
    sections = [
        resample_profile(circle_profile(5, segments=24), n),
        resample_profile(square_profile(8), n),
        resample_profile(polygon_profile(sides=6, r=4), n),
    ]
    path = [(0, 0, 0), (0, 0, 5), (0, 0, 10)]
    shape = loft(sections, path)
    bb = bbox(shape)
    assert bb.min[2] == pytest.approx(0.0)
    assert bb.max[2] == pytest.approx(10.0)
