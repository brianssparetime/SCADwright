"""Tests for projection transform (3D -> 2D)."""

import pytest

from scadwright import bbox, emit_str
from scadwright.primitives import cube, sphere
from scadwright.transforms import projection as projection_fn


def test_projection_default_emit():
    out = emit_str(cube(10).projection())
    assert "projection()" in out


def test_projection_cut_emit():
    out = emit_str(cube(10).projection(cut=True))
    assert "projection(cut=true)" in out


def test_projection_bbox_drops_z():
    bb = bbox(cube([10, 20, 30]).projection())
    assert bb.min == (0.0, 0.0, 0.0)
    assert bb.max == (10.0, 20.0, 0.0)


def test_projection_bbox_reflects_translated_child():
    # Translated 3D child: projection covers its XY footprint.
    bb = bbox(cube(10).translate([5, 5, 5]).projection())
    assert bb.min == (5.0, 5.0, 0.0)
    assert bb.max == (15.0, 15.0, 0.0)


def test_projection_cross_section_pattern_emits():
    # Typical use: slice a sphere at z=-5 to get a disc of the sphere at z=-5.
    out = emit_str(
        sphere(r=10, fn=16).translate([0, 0, -5]).projection(cut=True)
    )
    assert "projection(cut=true)" in out
    assert "translate" in out
    assert "sphere" in out


def test_standalone_matches_chained():
    a = projection_fn(cube(10), cut=True)
    b = cube(10).projection(cut=True)
    assert type(a) is type(b)
    assert a.cut == b.cut


def test_projection_inside_linear_extrude_reextrudes():
    # projection(...) extruded back up — nonsense in practice, but AST/bbox should cope.
    part = cube(10).projection().linear_extrude(height=3)
    bb = bbox(part)
    assert bb.max[2] == 3.0
