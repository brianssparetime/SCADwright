"""Tests for multmatrix transform."""

import pytest

from scadwright import Matrix, bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import cube
from scadwright.transforms import multmatrix as multmatrix_fn


def test_multmatrix_identity_emit():
    out = emit_str(cube(10).multmatrix(Matrix.identity()))
    assert "multmatrix([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])" in out


def test_multmatrix_translate_matches_translate_bbox():
    a = bbox(cube(10).multmatrix(Matrix.translate(5, 0, 0)))
    b = bbox(cube(10).translate([5, 0, 0]))
    assert a.min == b.min and a.max == b.max


def test_multmatrix_scale_matches_scale_bbox():
    a = bbox(cube(10).multmatrix(Matrix.scale(2, 3, 1)))
    b = bbox(cube(10).scale([2, 3, 1]))
    assert a.min == b.min and a.max == b.max


def test_multmatrix_accepts_list_of_lists():
    m_list = [
        [1, 0, 0, 5],
        [0, 1, 0, 0],
        [0, 0, 1, 0],
        [0, 0, 0, 1],
    ]
    t = cube(10).multmatrix(m_list)
    bb = bbox(t)
    assert bb.min[0] == 5 and bb.max[0] == 15


def test_multmatrix_accepts_3x4():
    m_3x4 = [
        [1, 0, 0, 0],
        [0, 1, 0, 5],
        [0, 0, 1, 0],
    ]
    bb = bbox(cube(10).multmatrix(m_3x4))
    assert bb.min[1] == 5 and bb.max[1] == 15


def test_multmatrix_accepts_4x3():
    m_4x3 = [
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
        [0, 0, 0],   # last row padded to [0,0,0,1]
    ]
    # This is a 4x3 shape — the loop at Node.multmatrix pads each row to length 4.
    # Expected: identity. So bbox unchanged.
    bb = bbox(cube(10).multmatrix(m_4x3))
    assert bb.min == (0, 0, 0) and bb.max == (10, 10, 10)


def test_multmatrix_rejects_wrong_shape():
    with pytest.raises(ValidationError, match="must be 4x4"):
        cube(10).multmatrix([[1, 2], [3, 4]])


def test_multmatrix_rejects_non_iterable():
    with pytest.raises(ValidationError, match="expected a Matrix"):
        cube(10).multmatrix(42)


def test_multmatrix_shear_expands_bbox():
    # Shear x by y: x' = x + 0.5*y. For a unit cube at origin, y in [0,10] adds [0,5] to x.
    shear = Matrix((
        (1.0, 0.5, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))
    bb = bbox(cube(10).multmatrix(shear))
    # X extends from 0 to 10+5=15.
    assert bb.max[0] == pytest.approx(15.0)
    assert bb.min[0] == pytest.approx(0.0)


def test_standalone_matches_chained():
    a = multmatrix_fn(cube(10), Matrix.translate(1, 2, 3))
    b = cube(10).multmatrix(Matrix.translate(1, 2, 3))
    assert type(a) is type(b)
    assert a.matrix.elements == b.matrix.elements


def test_multmatrix_composes_with_other_transforms():
    # Translate inside multmatrix: bbox reflects both.
    inner = cube(10).translate([1, 0, 0])
    bb = bbox(inner.multmatrix(Matrix.translate(2, 0, 0)))
    assert bb.min[0] == 3 and bb.max[0] == 13
