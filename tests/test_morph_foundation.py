"""Foundation tests for morph: Matrix decomposition helpers.

Covers the building blocks the walker and emit chain depend on. None of
the public morph API is tested here — that lives in the other test
modules.
"""

from __future__ import annotations

import math

import pytest

from scadwright import Matrix


def _approx_eq(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# Matrix.decompose_scale
# ---------------------------------------------------------------------------


def test_decompose_scale_identity():
    assert _approx_eq(Matrix.identity().decompose_scale(), (1.0, 1.0, 1.0))


def test_decompose_scale_pure_scale():
    m = Matrix.scale(2, 3, 4)
    assert _approx_eq(m.decompose_scale(), (2.0, 3.0, 4.0))


def test_decompose_scale_rotation_alone_is_unity():
    m = Matrix.rotate_z(37)
    assert _approx_eq(m.decompose_scale(), (1.0, 1.0, 1.0))


def test_decompose_scale_translate_only():
    m = Matrix.translate(5, 6, 7)
    assert _approx_eq(m.decompose_scale(), (1.0, 1.0, 1.0))


def test_decompose_scale_composed_rotate_then_scale():
    # Compose so the scale block is rotated: the column norms should still
    # recover the original scale factors.
    m = Matrix.rotate_z(45) @ Matrix.scale(2, 3, 4)
    assert _approx_eq(m.decompose_scale(), (2.0, 3.0, 4.0))


# ---------------------------------------------------------------------------
# Matrix.decompose_rotation_axis_angle
# ---------------------------------------------------------------------------


def test_decompose_rotation_identity():
    axis, angle = Matrix.identity().decompose_rotation_axis_angle()
    assert angle == 0.0
    # Axis is arbitrary at identity; check it's a unit vector.
    assert math.isclose(sum(a * a for a in axis), 1.0, abs_tol=1e-9)


def test_decompose_rotation_pure_z_90():
    axis, angle = Matrix.rotate_z(90).decompose_rotation_axis_angle()
    assert _approx_eq(axis, (0.0, 0.0, 1.0), tol=1e-9)
    assert math.isclose(angle, 90.0, abs_tol=1e-9)


def test_decompose_rotation_pure_x_45():
    axis, angle = Matrix.rotate_x(45).decompose_rotation_axis_angle()
    assert _approx_eq(axis, (1.0, 0.0, 0.0), tol=1e-9)
    assert math.isclose(angle, 45.0, abs_tol=1e-9)


def test_decompose_rotation_pure_y_negative():
    # Negative angle: matrix is the same as rotate_y(360 - 30); the axis-angle
    # form returned has |angle| in [0, 180] with a corresponding axis sign.
    axis, angle = Matrix.rotate_y(-30).decompose_rotation_axis_angle()
    # rotate_y(-30) is the same rotation as rotate_y(30) about the -Y axis.
    assert _approx_eq(axis, (0.0, -1.0, 0.0), tol=1e-9)
    assert math.isclose(angle, 30.0, abs_tol=1e-9)


def test_decompose_rotation_180_about_x():
    # 180° rotations are sign-ambiguous; the routine returns one of the two.
    # Either (1, 0, 0) or (-1, 0, 0) at angle 180° is valid.
    axis, angle = Matrix.rotate_x(180).decompose_rotation_axis_angle()
    assert math.isclose(angle, 180.0, abs_tol=1e-6)
    assert math.isclose(abs(axis[0]), 1.0, abs_tol=1e-9)
    assert math.isclose(axis[1], 0.0, abs_tol=1e-9)
    assert math.isclose(axis[2], 0.0, abs_tol=1e-9)


def test_decompose_rotation_180_about_y():
    axis, angle = Matrix.rotate_y(180).decompose_rotation_axis_angle()
    assert math.isclose(angle, 180.0, abs_tol=1e-6)
    assert math.isclose(axis[0], 0.0, abs_tol=1e-9)
    assert math.isclose(abs(axis[1]), 1.0, abs_tol=1e-9)
    assert math.isclose(axis[2], 0.0, abs_tol=1e-9)


def test_decompose_rotation_180_about_z():
    axis, angle = Matrix.rotate_z(180).decompose_rotation_axis_angle()
    assert math.isclose(angle, 180.0, abs_tol=1e-6)
    assert math.isclose(axis[0], 0.0, abs_tol=1e-9)
    assert math.isclose(axis[1], 0.0, abs_tol=1e-9)
    assert math.isclose(abs(axis[2]), 1.0, abs_tol=1e-9)


def test_decompose_rotation_arbitrary_axis_roundtrip():
    # Reconstructing the matrix from the decomposed axis-angle should
    # reproduce the original.
    original = Matrix.rotate_axis_angle(37.5, (0.3, 0.5, 0.8))
    axis, angle = original.decompose_rotation_axis_angle()
    reconstructed = Matrix.rotate_axis_angle(angle, axis)
    for r_row, o_row in zip(reconstructed.elements, original.elements):
        for r, o in zip(r_row, o_row):
            assert math.isclose(r, o, abs_tol=1e-9)


def test_decompose_rotation_with_scale_strips_scale():
    # rotate_z(60) then scale(3): decompose_scale recovers (3, 3, 3),
    # decompose_rotation_axis_angle recovers the original rotation.
    m = Matrix.rotate_z(60) @ Matrix.scale(3)
    sx, sy, sz = m.decompose_scale()
    assert _approx_eq((sx, sy, sz), (3.0, 3.0, 3.0))
    axis, angle = m.decompose_rotation_axis_angle()
    assert _approx_eq(axis, (0.0, 0.0, 1.0), tol=1e-9)
    assert math.isclose(angle, 60.0, abs_tol=1e-9)


def test_decompose_rotation_with_nonuniform_scale_roundtrip():
    # The doc says: column-normalize, then convert. For a rotate ∘ scale
    # composition with non-uniform scale, the column normalization recovers
    # the rotation correctly because each column was independently scaled.
    rot = Matrix.rotate_axis_angle(50, (0.0, 0.0, 1.0))
    m = rot @ Matrix.scale(2, 5, 1.5)
    sx, sy, sz = m.decompose_scale()
    assert _approx_eq((sx, sy, sz), (2.0, 5.0, 1.5))
    axis, angle = m.decompose_rotation_axis_angle()
    reconstructed = Matrix.rotate_axis_angle(angle, axis)
    for r_row, o_row in zip(reconstructed.elements, rot.elements):
        for r, o in zip(r_row, o_row):
            assert math.isclose(r, o, abs_tol=1e-9)


def test_decompose_rotation_zero_column_raises():
    # A degenerate matrix (column with zero norm) can't have rotation extracted.
    m = Matrix(((0.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0)))
    with pytest.raises(ValueError, match="zero-length column"):
        m.decompose_rotation_axis_angle()
