import math

import pytest

from scadwright import Component, Param, bbox
from scadwright.boolops import difference, hull, intersection, minkowski, union
from scadwright.primitives import circle, cube, sphere
from scadwright.transforms import transform
def _approx_eq(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


# --- transforms ---


def test_translate_shifts_bbox():
    bb = bbox(cube([10, 10, 10]).translate([5, 0, 0]))
    assert bb.min == (5, 0, 0)
    assert bb.max == (15, 10, 10)


def test_rotate_z_45_grows_aabb():
    bb = bbox(cube([10, 10, 10], center=True).rotate([0, 0, 45]))
    expected_extent = 5 * math.sqrt(2)
    assert abs(bb.max[0] - expected_extent) < 1e-9
    assert abs(bb.min[0] + expected_extent) < 1e-9
    # Z is unchanged by Z-axis rotation.
    assert _approx_eq((bb.min[2], bb.max[2]), (-5, 5))


def test_scale_grows_bbox():
    bb = bbox(cube([1, 1, 1]).scale(5))
    assert bb.min == (0, 0, 0)
    assert bb.max == (5, 5, 5)


def test_mirror_negates():
    bb = bbox(cube([10, 10, 10]).mirror([1, 0, 0]))
    assert bb.min == (-10, 0, 0)
    assert bb.max == (0, 10, 10)


def test_color_passthrough():
    bb_with = bbox(cube([10, 10, 10]).red())
    bb_without = bbox(cube([10, 10, 10]))
    assert bb_with == bb_without


def test_chain_translate_rotate():
    bb = bbox(
        cube([10, 10, 10], center=True).rotate([0, 0, 45]).translate([100, 0, 0])
    )
    expected_extent = 5 * math.sqrt(2)
    assert abs(bb.center[0] - 100) < 1e-9


# --- CSG ---


def test_union_spans_both():
    bb = bbox(union(
        cube([10, 10, 10]),
        cube([10, 10, 10]).translate([20, 0, 0]),
    ))
    assert bb.min == (0, 0, 0)
    assert bb.max == (30, 10, 10)


def test_difference_uses_first_operand():
    bb = bbox(difference(
        cube([10, 10, 10]),
        sphere(r=5).translate([5, 5, 5]),
    ))
    assert bb.min == (0, 0, 0)
    assert bb.max == (10, 10, 10)


def test_intersection_overlap():
    bb = bbox(intersection(
        cube([10, 10, 10]),
        cube([10, 10, 10]).translate([5, 5, 5]),
    ))
    assert bb.min == (5, 5, 5)
    assert bb.max == (10, 10, 10)


def test_hull_aabb():
    bb = bbox(hull(
        cube([1, 1, 1]),
        cube([1, 1, 1]).translate([10, 10, 10]),
    ))
    assert bb.min == (0, 0, 0)
    assert bb.max == (11, 11, 11)


def test_minkowski_extents_add():
    bb = bbox(minkowski(
        cube([10, 10, 10]),
        sphere(r=2),
    ))
    # Cube min=(0,0,0) max=(10,10,10) + sphere min=(-2,-2,-2) max=(2,2,2)
    assert bb.min == (-2, -2, -2)
    assert bb.max == (12, 12, 12)


# --- Component ---


class _Box(Component):
    size = Param(float, default=10)

    def build(self):
        return cube([self.size, self.size, self.size])


def test_component_bbox_from_build():
    bb = bbox(_Box(size=15))
    assert bb.min == (0, 0, 0)
    assert bb.max == (15, 15, 15)


def test_component_translated_bbox():
    bb = bbox(_Box(size=10).translate([100, 0, 0]))
    assert bb.min == (100, 0, 0)
    assert bb.max == (110, 10, 10)


# --- Custom transform ---


def test_custom_transform_bbox_via_expansion():
    from scadwright._custom_transforms.base import unregister

    @transform("_test_bbox_offset")
    def _t(node, *, dx):
        return node.translate([dx, 0, 0])

    try:
        bb = bbox(cube([10, 10, 10])._test_bbox_offset(dx=5))
        assert bb.min == (5, 0, 0)
        assert bb.max == (15, 10, 10)
    finally:
        unregister("_test_bbox_offset")


# --- extrudes ---


def test_linear_extrude_bbox():
    bb = bbox(circle(r=5, fn=24).linear_extrude(height=10))
    assert bb.min == (-5, -5, 0)
    assert bb.max == (5, 5, 10)


def test_linear_extrude_centered():
    bb = bbox(circle(r=3, fn=12).linear_extrude(height=4, center=True))
    assert _approx_eq(bb.min, (-3, -3, -2))
    assert _approx_eq(bb.max, (3, 3, 2))


# --- Resize ---


def test_resize_scales_bbox():
    bb = bbox(cube([1, 2, 3]).resize([10, 20, 30]))
    assert bb.min == (0, 0, 0)
    assert bb.max == (10, 20, 30)
