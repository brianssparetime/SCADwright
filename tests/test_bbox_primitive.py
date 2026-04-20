import pytest

from scadwright import BBox, Matrix
from scadwright.primitives import circle, cube, cylinder, polyhedron, sphere, square
from scadwright.bbox import _local_bbox


def test_cube_baselined_bbox():
    bb = _local_bbox(cube([10, 20, 30]))
    assert bb.min == (0, 0, 0)
    assert bb.max == (10, 20, 30)
    assert bb.size == (10, 20, 30)


def test_cube_centered_bbox():
    bb = _local_bbox(cube([10, 20, 30], center=True))
    assert bb.min == (-5, -10, -15)
    assert bb.max == (5, 10, 15)


def test_cube_per_axis_centered():
    bb = _local_bbox(cube([10, 20, 30], center="xy"))
    assert bb.min == (-5, -10, 0)
    assert bb.max == (5, 10, 30)


def test_sphere_bbox():
    bb = _local_bbox(sphere(r=7))
    assert bb.min == (-7, -7, -7)
    assert bb.max == (7, 7, 7)


def test_cylinder_bbox_baselined():
    bb = _local_bbox(cylinder(h=10, r=3))
    assert bb.min == (-3, -3, 0)
    assert bb.max == (3, 3, 10)


def test_cylinder_bbox_centered():
    bb = _local_bbox(cylinder(h=10, r=3, center=True))
    assert bb.min == (-3, -3, -5)
    assert bb.max == (3, 3, 5)


def test_cylinder_cone_uses_max_radius():
    bb = _local_bbox(cylinder(h=10, r1=5, r2=2))
    assert bb.min == (-5, -5, 0)
    assert bb.max == (5, 5, 10)


def test_polyhedron_bbox_walks_points():
    bb = _local_bbox(
        polyhedron(
            points=[(0, 0, 0), (10, 5, 2), (-1, 8, 3)],
            faces=[[0, 1, 2]],
        )
    )
    assert bb.min == (-1, 0, 0)
    assert bb.max == (10, 8, 3)


def test_square_bbox_2d_thin():
    bb = _local_bbox(square([10, 20]))
    assert bb.min == (0, 0, 0)
    assert bb.max == (10, 20, 0)


def test_circle_bbox_2d_thin():
    bb = _local_bbox(circle(r=5))
    assert bb.min == (-5, -5, 0)
    assert bb.max == (5, 5, 0)


# --- BBox helpers ---


def test_bbox_size_center():
    bb = BBox(min=(0, 0, 0), max=(10, 20, 30))
    assert bb.size == (10, 20, 30)
    assert bb.center == (5, 10, 15)


def test_bbox_contains():
    outer = BBox(min=(0, 0, 0), max=(10, 10, 10))
    inner = BBox(min=(2, 2, 2), max=(5, 5, 5))
    assert outer.contains(inner)
    assert not inner.contains(outer)


def test_bbox_overlaps():
    a = BBox(min=(0, 0, 0), max=(5, 5, 5))
    b = BBox(min=(3, 3, 3), max=(8, 8, 8))
    c = BBox(min=(10, 10, 10), max=(15, 15, 15))
    assert a.overlaps(b)
    assert not a.overlaps(c)


def test_bbox_union():
    a = BBox(min=(0, 0, 0), max=(5, 5, 5))
    b = BBox(min=(3, 3, 3), max=(8, 8, 8))
    u = a.union(b)
    assert u.min == (0, 0, 0)
    assert u.max == (8, 8, 8)


def test_bbox_intersection_overlap():
    a = BBox(min=(0, 0, 0), max=(5, 5, 5))
    b = BBox(min=(3, 3, 3), max=(8, 8, 8))
    i = a.intersection(b)
    assert i.min == (3, 3, 3)
    assert i.max == (5, 5, 5)


def test_bbox_intersection_disjoint():
    a = BBox(min=(0, 0, 0), max=(5, 5, 5))
    b = BBox(min=(10, 10, 10), max=(15, 15, 15))
    assert a.intersection(b) is None


def test_bbox_transformed_translate():
    bb = BBox(min=(0, 0, 0), max=(10, 10, 10))
    out = bb.transformed(Matrix.translate(1, 2, 3))
    assert out.min == (1, 2, 3)
    assert out.max == (11, 12, 13)


def test_bbox_transformed_rotate_grows_aabb():
    """Rotating a 10x10x10 cube by 45deg around Z gives a sqrt(2)*10 wide AABB."""
    import math as _m

    bb = BBox(min=(-5, -5, -5), max=(5, 5, 5))
    out = bb.transformed(Matrix.rotate_z(45))
    expected_extent = 5 * _m.sqrt(2)
    assert abs(out.max[0] - expected_extent) < 1e-9
    assert abs(out.min[0] + expected_extent) < 1e-9
