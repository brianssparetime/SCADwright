import pytest

from scadwright import BBox
from scadwright.asserts import assert_bbox_equal, assert_contains, assert_fits_in, assert_no_collision
from scadwright.errors import ValidationError
from scadwright.primitives import cube
# --- assert_fits_in ---


def test_fits_in_size_envelope_pass():
    assert_fits_in(cube([10, 10, 10], center=True), [20, 20, 20])


def test_fits_in_size_envelope_fail():
    with pytest.raises(AssertionError, match="does not fit"):
        assert_fits_in(cube([20, 20, 20], center=True), [10, 10, 10])


def test_fits_in_bbox_envelope():
    env = BBox(min=(0, 0, 0), max=(50, 50, 50))
    assert_fits_in(cube([10, 10, 10]), env)


def test_fits_in_bad_envelope_size():
    with pytest.raises(ValidationError, match="3 elements"):
        assert_fits_in(cube(1), [10, 10])


# --- assert_no_collision ---


def test_no_collision_pass():
    a = cube([5, 5, 5])
    b = cube([5, 5, 5]).translate([10, 0, 0])
    assert_no_collision(a, b)


def test_no_collision_fail():
    a = cube([5, 5, 5])
    b = cube([5, 5, 5]).translate([2, 0, 0])
    with pytest.raises(AssertionError, match="overlap"):
        assert_no_collision(a, b)


# --- assert_contains ---


def test_contains_pass():
    outer = cube([20, 20, 20], center=True)
    inner = cube([5, 5, 5], center=True)
    assert_contains(outer, inner)


def test_contains_fail():
    outer = cube([5, 5, 5], center=True)
    inner = cube([10, 10, 10], center=True)
    with pytest.raises(AssertionError, match="does not contain"):
        assert_contains(outer, inner)


# --- assert_bbox_equal ---


def test_bbox_equal_pass():
    assert_bbox_equal(
        cube([10, 20, 30]),
        BBox(min=(0, 0, 0), max=(10, 20, 30)),
    )


def test_bbox_equal_within_tolerance():
    assert_bbox_equal(
        cube([10, 20, 30.0000000001]),
        BBox(min=(0, 0, 0), max=(10, 20, 30)),
        tol=1e-6,
    )


def test_bbox_equal_fail_shows_axes():
    with pytest.raises(AssertionError, match="max.x"):
        assert_bbox_equal(
            cube([10, 20, 30]),
            BBox(min=(0, 0, 0), max=(99, 20, 30)),
        )
