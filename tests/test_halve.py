"""Halve: differences out the opposite-sign half along each nonzero axis."""

import pytest

from scadwright import emit_str
from scadwright.composition_helpers import halve
from scadwright.errors import ValidationError
from scadwright.primitives import cube, sphere


def test_halve_plus_y_cuts_minus_y_half():
    # cube(10) has bbox min=(0,0,0) max=(10,10,10) → R=10, size=20.4 (2% margin)
    out = emit_str(cube(10).halve([0, 1, 0]))
    assert "translate([0, -10.2, 0])" in out
    assert "difference() {" in out


def test_halve_minus_y_cuts_plus_y_half():
    out = emit_str(cube(10).halve([0, -1, 0]))
    assert "translate([0, 10.2, 0])" in out


def test_halve_multi_axis_produces_one_cutter_per_nonzero_axis():
    # cube(20, center=True) has bbox min=(-10,-10,-10) max=(10,10,10) → R=10, size=20.4
    out = emit_str(cube(20, center=True).halve([1, 1, 0]))
    assert "translate([-10.2, 0, 0])" in out
    assert "translate([0, -10.2, 0])" in out
    assert out.count("cube([20.4, 20.4, 20.4]") == 2


def test_halve_kwarg_form():
    a = emit_str(cube(1).halve(y=1))
    b = emit_str(cube(1).halve([0, 1, 0]))
    assert a == b


def test_halve_standalone_matches_chained():
    a = emit_str(halve(cube(1), [0, 0, 1]))
    b = emit_str(cube(1).halve([0, 0, 1]))
    assert a == b


def test_halve_size_override():
    out = emit_str(cube(1).halve([1, 0, 0], size=40))
    assert "cube([40, 40, 40]" in out
    assert "translate([-20, 0, 0])" in out


def test_halve_zero_vector_raises():
    with pytest.raises(ValidationError, match="at least one axis"):
        cube(1).halve([0, 0, 0])


def test_halve_negative_size_raises():
    with pytest.raises(ValidationError, match="size must be positive"):
        cube(1).halve([0, 1, 0], size=-5)


def test_halve_keeps_source_location():
    """Difference carries the source location of the halve() call site so
    errors downstream still point to user code."""
    node = cube(1).halve([0, 1, 0])
    assert node.source_location is not None
    assert node.source_location.file.endswith("test_halve.py")


def test_halve_composes_with_translate():
    """Cut planes pass through world origin, so translate-then-halve is
    the way to cut elsewhere. Cutter sizes track the translated bbox."""
    a = emit_str(sphere(r=5, fn=16).translate([10, 0, 0]).halve([1, 0, 0]))
    # Translated sphere bbox: x in [5, 15], y/z in [-5, 5]. R=15, size=30.6.
    assert "difference()" in a
    assert "translate([-15.3, 0, 0])" in a


def test_halve_cutter_size_tracks_part_size():
    """Auto-sized cutter scales with the part: bigger part → bigger cutter,
    smaller part → smaller cutter, and the .scad output stays free of the
    old fixed 10000-unit literals."""
    small = emit_str(cube(2).halve([0, 1, 0]))
    large = emit_str(cube(100).halve([0, 1, 0]))
    assert "10000" not in small
    assert "10000" not in large
    # Small cutter (cube(2) at origin → R=2 → size=4.08) is much smaller
    # than the large one (cube(100) at origin → R=100 → size=204).
    assert "cube([4.08, 4.08, 4.08]" in small
    assert "cube([204, 204, 204]" in large


def test_halve_minimum_cutter_size_for_origin_only_shape():
    """A degenerate bbox (single point at origin) still produces a cutter
    big enough to actually remove geometry on the chosen side."""
    # A 2D circle at origin with r=0 is degenerate; check the floor kicks
    # in for any shape whose extent is small enough that 2*R*1.02 < 1.
    out = emit_str(cube(0.1).halve([0, 1, 0]))
    # cube(0.1) → R=0.1 → 2*0.1*1.02=0.204; floor of 1.0 wins.
    assert "cube([1, 1, 1]" in out
