import math

import pytest

from scadwright import Matrix
def _approx_eq(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def test_identity_compose_is_no_op():
    i = Matrix.identity()
    t = Matrix.translate(1, 2, 3)
    assert (i @ t) == t
    assert (t @ i) == t


def test_translate_compose_additive():
    a = Matrix.translate(1, 0, 0)
    b = Matrix.translate(2, 0, 0)
    assert _approx_eq((a @ b).translation, (3, 0, 0))


def test_scale_apply_point():
    s = Matrix.scale(2)
    assert _approx_eq(s.apply_point((1, 2, 3)), (2, 4, 6))


def test_scale_per_axis():
    s = Matrix.scale(2, 3, 4)
    assert _approx_eq(s.apply_point((1, 1, 1)), (2, 3, 4))


def test_rotate_z_90deg_takes_x_to_y():
    r = Matrix.rotate_z(90)
    p = r.apply_point((1, 0, 0))
    assert _approx_eq(p, (0, 1, 0), tol=1e-9)


def test_rotate_x_90deg_takes_y_to_z():
    r = Matrix.rotate_x(90)
    p = r.apply_point((0, 1, 0))
    assert _approx_eq(p, (0, 0, 1), tol=1e-9)


def test_rotate_y_90deg_takes_z_to_x():
    r = Matrix.rotate_y(90)
    p = r.apply_point((0, 0, 1))
    assert _approx_eq(p, (1, 0, 0), tol=1e-9)


def test_rotate_axis_angle_around_z_matches_rotate_z():
    a = Matrix.rotate_z(45)
    b = Matrix.rotate_axis_angle(45, (0, 0, 1))
    pa = a.apply_point((1, 0, 0))
    pb = b.apply_point((1, 0, 0))
    assert _approx_eq(pa, pb, tol=1e-9)


def test_mirror_x_negates_x():
    m = Matrix.mirror((1, 0, 0))
    p = m.apply_point((5, 6, 7))
    assert _approx_eq(p, (-5, 6, 7))


def test_invert_round_trip():
    t = Matrix.translate(1, 2, 3) @ Matrix.rotate_z(30) @ Matrix.scale(2, 3, 4)
    inv = t.invert()
    p = (1.0, 2.0, 3.0)
    back = inv.apply_point(t.apply_point(p))
    assert _approx_eq(back, p, tol=1e-9)


def test_singular_matrix_raises():
    # All-zero matrix is singular.
    m = Matrix(((0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0)))
    with pytest.raises(ValueError, match="singular"):
        m.invert()


def test_compose_associativity():
    a = Matrix.translate(1, 2, 3)
    b = Matrix.rotate_z(45)
    c = Matrix.scale(2)
    p = (1.0, 1.0, 1.0)
    left = (a @ (b @ c)).apply_point(p)
    right = ((a @ b) @ c).apply_point(p)
    assert _approx_eq(left, right, tol=1e-9)


def test_rotate_euler_zyx_order():
    """SCAD's rotate([x,y,z]) applies Rx then Ry then Rz — pinning the
    composition order so it doesn't silently flip."""
    m = Matrix.rotate_euler(0, 0, 90)
    assert _approx_eq(m.apply_point((1, 0, 0)), (0, 1, 0), tol=1e-9)
