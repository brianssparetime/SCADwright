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
    """fuse=True extends self's contact face into other by EPS, leaving
    the opposite face at its declared position. Local extension on
    Cube preserves the user-facing top dimension exactly."""
    floor = cube([40, 40, 2])
    pylon = cube([5, 5, 10]).attach(floor, fuse=True)
    bb = bbox(pylon)
    # Bottom extended into floor (1.99); top preserved at the declared 12.0
    # (was 11.99 under the old global-shift mechanism).
    assert bb.min[2] == pytest.approx(1.99)
    assert bb.max[2] == pytest.approx(12.0)


def test_attach_fuse_false_is_default():
    """Default fuse=False produces exact contact."""
    floor = cube([40, 40, 2])
    pylon = cube([5, 5, 10]).attach(floor)
    bb = bbox(pylon)
    assert bb.min[2] == pytest.approx(2.0)


def test_attach_fuse_custom_eps():
    """Custom eps controls the extension depth on the contact side; the
    far face stays at its declared position."""
    floor = cube([40, 40, 2])
    pylon = cube([5, 5, 10]).attach(floor, fuse=True, eps=0.05)
    bb = bbox(pylon)
    assert bb.min[2] == pytest.approx(1.95)
    assert bb.max[2] == pytest.approx(12.0)  # top preserved


def test_attach_fuse_bottom_face():
    """fuse on at='top' face: pendant's top face extends upward into
    the ceiling, while the pendant's bottom stays at z=10 (preserved)."""
    ceiling = cube([40, 40, 2]).up(20)
    pendant = cube([5, 5, 10]).attach(ceiling, on="bottom", using_anchor="top", fuse=True)
    bb = bbox(pendant)
    # top face of pendant extended from z=20 up to z=20.01.
    assert bb.max[2] == pytest.approx(20.01)
    # bottom face of pendant preserved at z=10 (was 10.01 under the
    # old global-shift mechanism).
    assert bb.min[2] == pytest.approx(10.0)


def test_attach_fuse_side_face():
    """fuse on a side face: extension on the contact face only; the
    opposite face stays at its declared position."""
    wall = cube([2, 40, 40])
    shelf = cube([20, 30, 3]).attach(wall, on="rside", using_anchor="lside", fuse=True)
    bb = bbox(shelf)
    # Contact face (lside) extended into wall: x=1.99.
    assert bb.min[0] == pytest.approx(1.99)
    # Opposite face (rside) preserved at x=22.0 (= 2 + 20).
    assert bb.max[0] == pytest.approx(22.0)
