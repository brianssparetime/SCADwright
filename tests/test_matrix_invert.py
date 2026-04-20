"""Tests for Matrix.invert error reporting and Matrix.determinant (Group 1d)."""

import math

import pytest

from scadwright.matrix import Matrix


def test_singular_invert_includes_matrix_in_message():
    m = Matrix.scale(1.0, 0.0, 1.0)  # Y collapsed → singular.
    with pytest.raises(ValueError, match="singular"):
        m.invert()
    try:
        m.invert()
    except ValueError as e:
        # The offending matrix should be in the message for debuggability.
        assert "0.000" in str(e) or "0.0" in str(e)


def test_determinant_identity():
    assert Matrix.identity().determinant() == pytest.approx(1.0)


def test_determinant_scale():
    # det(scale(a,b,c)) = a*b*c (translation doesn't affect det).
    assert Matrix.scale(2.0, 3.0, 4.0).determinant() == pytest.approx(24.0)


def test_determinant_translate_is_one():
    assert Matrix.translate(5, -3, 17).determinant() == pytest.approx(1.0)


def test_determinant_rotation_is_one():
    # Proper rotations preserve volume and orientation.
    m = Matrix.rotate_z(37) @ Matrix.rotate_x(12) @ Matrix.rotate_y(-50)
    assert m.determinant() == pytest.approx(1.0, abs=1e-9)


def test_determinant_mirror_is_negative_one():
    # Reflection flips orientation.
    assert Matrix.mirror((1, 0, 0)).determinant() == pytest.approx(-1.0)


def test_determinant_zero_for_singular():
    assert Matrix.scale(1, 0, 1).determinant() == pytest.approx(0.0)


def test_is_invertible():
    assert Matrix.identity().is_invertible()
    assert Matrix.scale(2, 3, 4).is_invertible()
    assert not Matrix.scale(1, 0, 1).is_invertible()


def test_invert_matches_inverse_scale():
    m = Matrix.scale(2.0, 4.0, 5.0)
    inv = m.invert()
    p = inv @ m
    for i in range(4):
        for j in range(4):
            expected = 1.0 if i == j else 0.0
            assert abs(p.elements[i][j] - expected) < 1e-12
