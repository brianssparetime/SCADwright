"""Tests for Group 11 convenience methods on Node.

center_bbox, attach, array (linear_copy alias), and CSG operator overloads.
"""

import pytest

from scadwright import bbox, emit_str
from scadwright.ast.csg import Difference, Intersection, Union
from scadwright.errors import ValidationError
from scadwright.primitives import cube, sphere


# --- center_bbox ---


@pytest.mark.parametrize(
    "shape, expected_size",
    [
        (cube([10, 20, 30]),                    (10.0, 20.0, 30.0)),
        (cube([10, 10, 10], center=True),       (10.0, 10.0, 10.0)),
        (cube(10).translate([100, 200, 300]),   (10.0, 10.0, 10.0)),
    ],
    ids=["asymmetric", "already-centered", "pre-translated"],
)
def test_center_bbox_moves_to_origin_and_preserves_extent(shape, expected_size):
    c = shape.center_bbox()
    bb = bbox(c)
    assert bb.center == pytest.approx((0.0, 0.0, 0.0))
    assert bb.size == pytest.approx(expected_size)


# --- attach ---


@pytest.mark.parametrize(
    "on, at, peg_size, seat_axis, peg_extent",
    [
        ("top", "bottom", [10, 10, 5], 2, (2.0, 7.0)),       # default: on top
        ("bottom", "top", [10, 10, 5], 2, (-5.0, 0.0)),      # underneath
        ("rside", "lside", [5, 5, 5], 0, (40.0, 45.0)),      # right side
    ],
    ids=["default-top", "underneath", "rside"],
)
def test_attach_sits_peg_against_plate_face(on, at, peg_size, seat_axis, peg_extent):
    plate = cube([40, 40, 2])
    peg = cube(peg_size).attach(plate, on=on, at=at)
    bb = bbox(peg)
    assert bb.min[seat_axis] == pytest.approx(peg_extent[0])
    assert bb.max[seat_axis] == pytest.approx(peg_extent[1])


def test_attach_default_args_place_on_top():
    """Default on='top', at='bottom' puts peg on top of plate."""
    plate = cube([40, 40, 2])
    peg = cube([10, 10, 5]).attach(plate)
    bb = bbox(peg)
    assert bb.min[2] == pytest.approx(2.0)
    assert bb.max[2] == pytest.approx(7.0)


def test_attach_axis_sign_names_work():
    """Axis-sign names (+z, -x, etc.) work the same as friendly names."""
    plate = cube([40, 40, 2])
    peg_friendly = cube([10, 10, 5]).attach(plate, on="top", at="bottom")
    peg_axis = cube([10, 10, 5]).attach(plate, on="+z", at="-z")
    bb_f = bbox(peg_friendly)
    bb_a = bbox(peg_axis)
    assert bb_f.min == pytest.approx(bb_a.min)
    assert bb_f.max == pytest.approx(bb_a.max)


def test_attach_invalid_face_raises():
    with pytest.raises(ValidationError, match="custom anchor.*only available on Components"):
        cube(5).attach(cube(5), on="diagonal")


def test_attach_invalid_at_raises():
    with pytest.raises(ValidationError, match="custom anchor.*only available on Components"):
        cube(5).attach(cube(5), at="oops")


def test_attach_chain_with_translate_offsets_from_center():
    plate = cube([40, 40, 2])
    peg = cube([5, 5, 5]).attach(plate).translate([10, 0, 0])
    bb = bbox(peg)
    # Center was at X=20, offset 10 -> X center = 30.
    assert bb.center[0] == pytest.approx(30.0)


def test_attach_same_face_aligns_faces():
    """Attaching top-to-top aligns the top faces (peg sits below plate)."""
    plate = cube([40, 40, 2])
    peg = cube([10, 10, 5]).attach(plate, on="top", at="top")
    bb = bbox(peg)
    # Peg's top face should be at plate's top (z=2), peg extends down to z=-3.
    assert bb.max[2] == pytest.approx(2.0)
    assert bb.min[2] == pytest.approx(-3.0)


# --- array ---


def test_array_default_axis_x():
    arr = cube(5).array(count=3, spacing=10)
    bb = bbox(arr)
    # count=3, spacing=10 → copies at x=0, 10, 20; each 5 wide → max x = 25.
    assert bb.min == pytest.approx((0.0, 0.0, 0.0))
    assert bb.max == pytest.approx((25.0, 5.0, 5.0))


def test_array_axis_y():
    arr = cube(5).array(count=4, spacing=6, axis="y")
    bb = bbox(arr)
    # copies at y=0, 6, 12, 18; each 5 tall → max y = 23.
    assert bb.max[1] == pytest.approx(23.0)


def test_array_axis_z_case_insensitive():
    arr = cube(5).array(count=2, spacing=10, axis="Z")
    bb = bbox(arr)
    assert bb.max[2] == pytest.approx(15.0)


def test_array_negative_spacing_goes_backwards():
    arr = cube(5).array(count=3, spacing=-10)
    bb = bbox(arr)
    assert bb.min[0] == pytest.approx(-20.0)
    assert bb.max[0] == pytest.approx(5.0)


def test_array_explicit_vector_axis():
    arr = cube(2).array(count=2, spacing=5, axis=[1, 1, 0])
    bb = bbox(arr)
    # Second copy at (5, 5, 0); self at (0,0,0) of extent 2.
    assert bb.max[0] == pytest.approx(7.0)
    assert bb.max[1] == pytest.approx(7.0)


def test_array_invalid_axis_string_raises():
    with pytest.raises(ValidationError, match="axis must"):
        cube(1).array(count=2, spacing=5, axis="diagonal")


def test_array_non_positive_count_raises():
    with pytest.raises(ValidationError, match="positive integer"):
        cube(1).array(count=0, spacing=5)


def test_array_bool_count_rejected():
    with pytest.raises(ValidationError, match="positive integer"):
        cube(1).array(count=True, spacing=5)


# --- operator overloads ---


def test_sub_produces_difference():
    d = cube(10) - cube(5)
    assert isinstance(d, Difference)
    assert len(d.children) == 2


def test_or_produces_union():
    u = cube(5) | cube(5).translate([5, 0, 0])
    assert isinstance(u, Union)
    assert len(u.children) == 2


def test_and_produces_intersection():
    i = cube(5) & cube(5).translate([2, 0, 0])
    assert isinstance(i, Intersection)
    assert len(i.children) == 2


def test_or_chains_flatten():
    a, b, c = cube(1), cube(2), cube(3)
    u = a | b | c
    assert isinstance(u, Union)
    assert len(u.children) == 3
    # Not nested.
    for child in u.children:
        assert not isinstance(child, Union)


def test_and_chains_flatten():
    a, b, c = cube(1), cube(2), cube(3)
    i = a & b & c
    assert isinstance(i, Intersection)
    assert len(i.children) == 3


def test_sub_chains_flatten():
    a, b, c = cube(10), cube(3), cube(2)
    d = a - b - c
    assert isinstance(d, Difference)
    assert len(d.children) == 3


def test_mixed_ops_do_not_flatten_across_types():
    a, b, c = cube(1), cube(2), cube(3)
    expr = (a | b) & c
    assert isinstance(expr, Intersection)
    # Intersection has two children: the union and c.
    assert len(expr.children) == 2
    assert isinstance(expr.children[0], Union)


def test_non_node_rhs_raises_type_error():
    with pytest.raises(TypeError):
        _ = cube(10) | 5
    with pytest.raises(TypeError):
        _ = cube(10) - "oops"


def test_operator_emit_is_flat():
    a, b, c = cube(1), cube(2), cube(3)
    out = emit_str(a | b | c)
    # A single union() wrapping three cubes — not nested.
    assert out.count("union()") == 1


def test_parenthesized_intersection_preserved():
    a, b, c = cube(1), cube(2), cube(3)
    expr = a | (b & c)
    assert isinstance(expr, Union)
    assert isinstance(expr.children[1], Intersection)
