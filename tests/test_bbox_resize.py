"""Tests for Resize bbox with per-axis `auto` semantics (MajorReview Group 1a)."""

import pytest

from scadwright import bbox
from scadwright.primitives import cube, square
def _approx(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def test_resize_all_axes_explicit():
    bb = bbox(cube([1, 2, 3]).resize([10, 20, 30]))
    assert _approx(bb.min, (0, 0, 0))
    assert _approx(bb.max, (10, 20, 30))


def test_resize_zero_axis_no_auto_leaves_alone():
    # Y target = 0, auto=False → Y stays at its child extent (2).
    bb = bbox(cube([1, 2, 3]).resize([10, 0, 0]))
    assert _approx(bb.min, (0, 0, 0))
    assert _approx(bb.max, (10, 2, 3))


def test_resize_zero_axis_auto_copies_max_explicit_scale():
    # X: scale=10, Y=0 with auto → should use scale=10, Z=0 no auto → stays.
    bb = bbox(
        cube([1, 2, 3]).resize([10, 0, 0], auto=[False, True, False])
    )
    assert _approx(bb.min, (0, 0, 0))
    assert _approx(bb.max, (10, 20, 3))


def test_resize_auto_all_axes():
    # Only X is explicit; Y and Z inherit the scale of 10.
    bb = bbox(cube([1, 2, 3]).resize([10, 0, 0], auto=True))
    assert _approx(bb.min, (0, 0, 0))
    assert _approx(bb.max, (10, 20, 30))


def test_resize_multiple_explicit_auto_takes_max():
    # X: scale=10, Y: scale=5, Z auto → Z should use max = 10.
    bb = bbox(
        cube([1, 2, 3]).resize([10, 10, 0], auto=[False, False, True])
    )
    assert _approx(bb.min, (0, 0, 0))
    assert _approx(bb.max, (10, 10, 30))


def test_resize_zero_extent_child_axis_unchanged():
    # A 2D square has zero Z extent; resize should never divide by zero.
    bb = bbox(square([4, 4]).resize([8, 8, 0]))
    assert _approx(bb.min, (0, 0, 0))
    assert _approx(bb.max, (8, 8, 0))


def test_resize_auto_with_no_explicit_scale_stays_identity():
    # All new_size entries are 0: nothing explicit, auto has no reference.
    bb = bbox(cube([2, 3, 4]).resize([0, 0, 0], auto=True))
    assert _approx(bb.min, (0, 0, 0))
    assert _approx(bb.max, (2, 3, 4))
