import pytest

from scadwright.primitives import cube
from scadwright.matrix import to_matrix


def _approx_eq(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def test_translate_node_to_matrix():
    n = cube(1).translate([1, 2, 3])
    m = to_matrix(n)
    assert _approx_eq(m.translation, (1, 2, 3))


def test_rotate_euler_to_matrix():
    n = cube(1).rotate([0, 0, 90])
    m = to_matrix(n)
    p = m.apply_point((1, 0, 0))
    assert _approx_eq(p, (0, 1, 0), tol=1e-9)


def test_rotate_axis_angle_to_matrix():
    n = cube(1).rotate(a=90, v=[0, 0, 1])
    m = to_matrix(n)
    p = m.apply_point((1, 0, 0))
    assert _approx_eq(p, (0, 1, 0), tol=1e-9)


def test_scale_to_matrix():
    n = cube(1).scale(2)
    m = to_matrix(n)
    assert _approx_eq(m.apply_point((1, 1, 1)), (2, 2, 2))


def test_mirror_to_matrix():
    n = cube(1).mirror([1, 0, 0])
    m = to_matrix(n)
    assert _approx_eq(m.apply_point((5, 6, 7)), (-5, 6, 7))


def test_color_is_identity():
    n = cube(1).red()
    m = to_matrix(n)
    assert m.is_identity


def test_resize_raises():
    n = cube(1).resize([10, 10, 10])
    with pytest.raises(ValueError, match="Resize"):
        to_matrix(n)


def test_unsupported_node_raises():
    with pytest.raises(TypeError):
        to_matrix(cube(1))
