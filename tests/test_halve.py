"""Halve: differences out the opposite-sign half along each nonzero axis."""

import pytest

from scadwright import emit_str
from scadwright.composition_helpers import halve
from scadwright.errors import ValidationError
from scadwright.primitives import cube, sphere


def test_halve_plus_y_cuts_minus_y_half():
    out = emit_str(cube(10).halve([0, 1, 0]))
    # Cutter translated -size/2 in y
    assert "translate([0, -5000, 0])" in out
    assert "difference() {" in out


def test_halve_minus_y_cuts_plus_y_half():
    out = emit_str(cube(10).halve([0, -1, 0]))
    assert "translate([0, 5000, 0])" in out


def test_halve_multi_axis_produces_one_cutter_per_nonzero_axis():
    out = emit_str(cube(20, center=True).halve([1, 1, 0]))
    # Two translated cubes: one for x, one for y.
    assert "translate([-5000, 0, 0])" in out
    assert "translate([0, -5000, 0])" in out
    # Exactly two cutter cubes in the difference besides the subject.
    assert out.count("cube([10000, 10000, 10000]") == 2


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
    the way to cut elsewhere."""
    a = emit_str(sphere(r=5, fn=16).translate([10, 0, 0]).halve([1, 0, 0]))
    # Kept side is +x (subject is wholly +x after translate); output
    # emits as difference of the translated sphere minus a cutter.
    assert "difference()" in a
    assert "translate([-5000, 0, 0])" in a
