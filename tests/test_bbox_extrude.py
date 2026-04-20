"""Tests for extrude bbox correctness (MajorReview Group 1b/1c)."""

import math

from scadwright import bbox
from scadwright.primitives import square
def _approx(a, b, tol=1e-6):
    return all(abs(x - y) < tol for x, y in zip(a, b))


# --- LinearExtrude with twist ---


def test_linear_extrude_no_twist_unchanged():
    # Regression: twist=0 must still produce the tight axis-aligned bbox.
    bb = bbox(square([10, 4]).linear_extrude(height=5))
    assert _approx(bb.min, (0, 0, 0))
    assert _approx(bb.max, (10, 4, 5))


def test_linear_extrude_twist_envelope_is_circumscribed():
    # Centered 10x2 rectangle twisted 90°: at some θ the long axis points in Y,
    # so Y extent must reach ~5 (half the long side). Disc envelope: r=hypot(5,1).
    bb = bbox(
        square([10, 2], center=True).linear_extrude(height=3, twist=90)
    )
    r = math.hypot(5.0, 1.0)
    assert _approx((bb.min[0], bb.min[1]), (-r, -r))
    assert _approx((bb.max[0], bb.max[1]), (r, r))
    assert _approx((bb.min[2], bb.max[2]), (0, 3))


def test_linear_extrude_twist_honors_scale():
    bb = bbox(
        square([10, 2], center=True).linear_extrude(
            height=3, twist=180, scale=2.0
        )
    )
    r = math.hypot(5.0, 1.0) * 2.0
    assert _approx((bb.min[0], bb.min[1]), (-r, -r))
    assert _approx((bb.max[0], bb.max[1]), (r, r))


# --- RotateExtrude with partial angle ---


def test_rotate_extrude_full_sweep_unchanged():
    # Annular profile at x∈[5,10], z∈[0,2], full sweep → disc of radius 10.
    profile = square([5, 2]).translate([5, 0, 0])
    bb = bbox(profile.rotate_extrude(angle=360))
    assert _approx(bb.min, (-10, -10, 0))
    assert _approx(bb.max, (10, 10, 2))


def test_rotate_extrude_90_stays_in_first_quadrant():
    profile = square([5, 2]).translate([5, 0, 0])
    bb = bbox(profile.rotate_extrude(angle=90))
    # Sweep 0..90 with r∈[5,10]: x∈[0,10] (θ=0 at r_outer), y∈[0,10] (θ=90).
    assert _approx(bb.min, (0, 0, 0))
    assert _approx(bb.max, (10, 10, 2))


def test_rotate_extrude_180_covers_upper_half_plane():
    profile = square([5, 2]).translate([5, 0, 0])
    bb = bbox(profile.rotate_extrude(angle=180))
    # x∈[-10,10] (sweeps through θ=180 and θ=0), y∈[0,10].
    assert _approx(bb.min, (-10, 0, 0))
    assert _approx(bb.max, (10, 10, 2))


def test_rotate_extrude_45_small_sector():
    profile = square([5, 2]).translate([5, 0, 0])
    bb = bbox(profile.rotate_extrude(angle=45))
    # No axis crossings inside (0,45). Extremes at θ=0: x=10, y=0;
    # θ=45: x=10 cos45 ≈ 7.07, y=10 sin45 ≈ 7.07.
    # Min x: smaller of 5 cos45 ≈ 3.54 and 5 (at θ=0)... wait r_inner=5 so θ=0
    # gives x=5, θ=45 gives x=5*cos45 ≈ 3.54. So min x = 3.54.
    s = math.sin(math.radians(45))
    c = math.cos(math.radians(45))
    assert _approx(bb.min, (5 * c, 0, 0))
    assert _approx(bb.max, (10, 10 * s, 2))


def test_rotate_extrude_negative_angle_sweeps_clockwise():
    profile = square([5, 2]).translate([5, 0, 0])
    bb = bbox(profile.rotate_extrude(angle=-90))
    # Sweep 0..-90: x∈[0,10] (θ=0), y∈[-10,0] (θ=-90).
    assert _approx(bb.min, (0, -10, 0))
    assert _approx(bb.max, (10, 0, 2))
