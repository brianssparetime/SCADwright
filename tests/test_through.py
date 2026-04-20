"""Tests for through() cutter extension and attach(fuse=True) joint overlap."""

import pytest

from scadwright import bbox
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder


# --- through() ---


def test_through_both_ends():
    """Cylinder spanning full height of box: both ends extended."""
    box = cube([20, 20, 10])
    hole = cylinder(h=10, r=3).through(box)
    bb = bbox(hole)
    assert bb.min[2] == pytest.approx(-0.01)
    assert bb.max[2] == pytest.approx(10.01)


def test_through_one_end_top():
    """Counterbore flush with top only: only top extended."""
    box = cube([20, 20, 10])
    bore = cylinder(h=5, r=6).up(5).through(box)
    bb = bbox(bore)
    # Top was at z=10, now z=10.01. Bottom was at z=5, unchanged.
    assert bb.max[2] == pytest.approx(10.01)
    assert bb.min[2] == pytest.approx(5.0)


def test_through_one_end_bottom():
    """Cutter flush with bottom only: only bottom extended."""
    box = cube([20, 20, 10])
    pocket = cylinder(h=5, r=3).through(box)
    bb = bbox(pocket)
    # Bottom was at z=0, now z=-0.01. Top was at z=5, unchanged.
    assert bb.min[2] == pytest.approx(-0.01)
    assert bb.max[2] == pytest.approx(5.0)


def test_through_neither_end():
    """Blind hole: neither end coincident, no-op."""
    box = cube([20, 20, 10])
    pocket = cylinder(h=4, r=3).up(3).through(box)
    bb = bbox(pocket)
    # No change: min=3, max=7.
    assert bb.min[2] == pytest.approx(3.0)
    assert bb.max[2] == pytest.approx(7.0)


def test_through_custom_eps():
    box = cube([20, 20, 10])
    hole = cylinder(h=10, r=3).through(box, eps=0.1)
    bb = bbox(hole)
    assert bb.min[2] == pytest.approx(-0.1)
    assert bb.max[2] == pytest.approx(10.1)


def test_through_custom_axis():
    """Slot cut along x-axis."""
    box = cube([20, 20, 10])
    slot = cube([20, 5, 3]).up(3).through(box, axis="x")
    bb = bbox(slot)
    assert bb.min[0] == pytest.approx(-0.01)
    assert bb.max[0] == pytest.approx(20.01)


def test_through_no_overlap_raises():
    """Cutter entirely outside parent raises error."""
    box = cube([20, 20, 10])
    far_away = cylinder(h=5, r=3).up(50)
    with pytest.raises(ValidationError, match="does not overlap"):
        far_away.through(box)


def test_through_preserves_cross_section():
    """through() only stretches along the cut axis, not perpendicular."""
    box = cube([20, 20, 10])
    hole = cylinder(h=10, r=3).through(box)
    bb = bbox(hole)
    # X and Y extent should be unchanged (diameter 6).
    assert bb.size[0] == pytest.approx(6.0)
    assert bb.size[1] == pytest.approx(6.0)


def test_through_is_harmless_on_blind():
    """Calling through() on a non-coincident cutter returns self."""
    box = cube([20, 20, 10])
    pocket = cylinder(h=4, r=3).up(3)
    result = pocket.through(box)
    assert result is pocket  # Same object, not wrapped.


# --- attach(fuse=True) ---


def test_attach_fuse_extends_into_contact():
    """fuse=True pushes self EPS into other."""
    floor = cube([40, 40, 2])
    pylon = cube([5, 5, 10]).attach(floor, fuse=True)
    bb = bbox(pylon)
    # Without fuse: bottom at z=2. With fuse: bottom at z=1.99 (pushed 0.01 into floor).
    assert bb.min[2] == pytest.approx(1.99)
    assert bb.max[2] == pytest.approx(11.99)


def test_attach_fuse_false_is_default():
    """Default fuse=False produces exact contact."""
    floor = cube([40, 40, 2])
    pylon = cube([5, 5, 10]).attach(floor)
    bb = bbox(pylon)
    assert bb.min[2] == pytest.approx(2.0)


def test_attach_fuse_custom_eps():
    floor = cube([40, 40, 2])
    pylon = cube([5, 5, 10]).attach(floor, fuse=True, eps=0.05)
    bb = bbox(pylon)
    assert bb.min[2] == pytest.approx(1.95)


def test_attach_fuse_bottom_face():
    """fuse on bottom face pushes upward into other."""
    ceiling = cube([40, 40, 2]).up(20)
    pendant = cube([5, 5, 10]).attach(ceiling, face="bottom", at="top", fuse=True)
    bb = bbox(pendant)
    # top face of pendant at z=20, pushed 0.01 up into ceiling -> z=20.01
    assert bb.max[2] == pytest.approx(20.01)


def test_attach_fuse_side_face():
    """fuse on a side face pushes into the side."""
    wall = cube([2, 40, 40])
    shelf = cube([20, 30, 3]).attach(wall, face="rside", at="lside", fuse=True)
    bb = bbox(shelf)
    # Without fuse: lside at x=2. With fuse: pushed 0.01 into wall.
    assert bb.min[0] == pytest.approx(1.99)
