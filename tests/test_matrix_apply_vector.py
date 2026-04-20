"""Tests for Matrix.apply_vector — rotation/scale applied, translation ignored."""

import math

import pytest

from scadwright import Matrix


def _approx(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def test_pure_translation_leaves_vector_unchanged():
    m = Matrix.translate(5, -3, 7)
    assert _approx(m.apply_vector((1, 0, 0)), (1, 0, 0))
    assert _approx(m.apply_vector((0, 1, 0)), (0, 1, 0))
    assert _approx(m.apply_vector((2, 3, -4)), (2, 3, -4))


def test_rotate_z_90_maps_x_to_y():
    m = Matrix.rotate_z(90)
    assert _approx(m.apply_vector((1, 0, 0)), (0, 1, 0))


def test_rotate_x_90_maps_y_to_z():
    m = Matrix.rotate_x(90)
    assert _approx(m.apply_vector((0, 1, 0)), (0, 0, 1))


def test_scale_scales_components():
    m = Matrix.scale(2, 3, 4)
    assert _approx(m.apply_vector((1, 1, 1)), (2, 3, 4))


def test_composed_transform_vector_ignores_translation():
    # Rotate 90 around Z, then translate by (10, 0, 0). The composite
    # matrix's translation column is nonzero, but apply_vector skips it.
    m = Matrix.translate(10, 0, 0) @ Matrix.rotate_z(90)
    # apply_point on (1,0,0): rotate -> (0,1,0), translate -> (10,1,0)
    assert _approx(m.apply_point((1, 0, 0)), (10, 1, 0))
    # apply_vector on (1,0,0): rotate only -> (0,1,0)
    assert _approx(m.apply_vector((1, 0, 0)), (0, 1, 0))


def test_apply_vector_equivalent_to_apply_point_minus_origin_point():
    # Alternative way to get the same answer: apply_point(v) - apply_point(0).
    m = Matrix.translate(5, 5, 5) @ Matrix.rotate_z(30) @ Matrix.scale(2, 2, 2)
    v = (1, 0, 0)
    via_vector = m.apply_vector(v)
    via_point = m.apply_point(v)
    origin = m.apply_point((0, 0, 0))
    diff = tuple(via_point[i] - origin[i] for i in range(3))
    assert _approx(via_vector, diff)


def test_docs_example_place_feature_at_other_feature_location():
    # Example the docs will show: "where did this anchor end up after
    # the composed transform, and in which direction does +X point?"
    placement = Matrix.translate(10, 20, 0) @ Matrix.rotate_z(90)
    anchor_world = placement.apply_point((0, 0, 0))
    forward_world = placement.apply_vector((1, 0, 0))
    assert _approx(anchor_world, (10, 20, 0))
    assert _approx(forward_world, (0, 1, 0))
