"""Tests for Group 4 convention cleanup (4b/4c/4e/4f).

4a (vector normalizer dedup) is a pure refactor — existing tests cover it.
4d (center multi-form) is doc-only.
"""

import pytest

from scadwright import bbox
from scadwright.boolops import union
from scadwright.composition_helpers import mirror_copy
from scadwright.errors import ValidationError
from scadwright.primitives import cube, sphere


# --- 4b: scalar broadcast error messages ---


def test_translate_scalar_error_mentions_axis_and_vector_example():
    with pytest.raises(ValidationError, match="scalar not accepted") as exc:
        cube(1).translate(5)
    msg = str(exc.value)
    assert "3-vector" in msg
    assert "keyword" in msg.lower()


def test_mirror_scalar_error_mentions_axis():
    with pytest.raises(ValidationError, match="scalar not accepted"):
        cube(1).mirror(1)


# --- 4c: rotate angle / axis aliases ---


def test_rotate_axis_angle_short_names_still_work():
    t = cube(1).rotate(a=30, v=[0, 0, 1])
    assert t.a == 30.0 and t.v == (0.0, 0.0, 1.0)


def test_rotate_accepts_angle_and_axis_aliases():
    t = cube(1).rotate(angle=30, axis=[0, 0, 1])
    assert t.a == 30.0 and t.v == (0.0, 0.0, 1.0)


def test_rotate_mixing_a_and_angle_raises():
    with pytest.raises(ValidationError, match="a.*angle"):
        cube(1).rotate(a=30, angle=45, axis=[0, 0, 1])


def test_rotate_mixing_v_and_axis_raises():
    with pytest.raises(ValidationError, match="v.*axis"):
        cube(1).rotate(a=30, v=[0, 0, 1], axis=[1, 0, 0])


def test_rotate_euler_with_positional_still_works():
    t = cube(1).rotate([0, 45, 0])
    assert t.angles == (0.0, 45.0, 0.0)


# --- 4e: CSG flattening is one-level and documented ---


def test_union_flattens_single_level_iterable():
    a, b, c = cube(1), cube(2), cube(3)
    u = union([a, b, c])
    assert len(u.children) == 3


def test_union_rejects_nested_iterables_with_clear_message():
    a, b, c = cube(1), cube(2), cube(3)
    with pytest.raises(ValidationError, match="one level only"):
        union([[a, b], [c]])


def test_union_mixed_variadic_and_iterable():
    a, b, c, d = cube(1), cube(2), cube(3), cube(4)
    u = union(a, [b, c], d)
    assert len(u.children) == 4


# --- 4f: mirror_copy dual signature ---


def test_mirror_copy_positional_form_still_works():
    u = mirror_copy([1, 0, 0], cube(5))
    # 1 original + 1 mirror = 2 children.
    assert len(u.children) == 2


def test_mirror_copy_kwarg_form():
    u = mirror_copy(cube(5), normal=[1, 0, 0])
    assert len(u.children) == 2


def test_mirror_copy_kwarg_form_multiple_shapes():
    u = mirror_copy(cube(5), sphere(r=3, fn=8), normal=[1, 0, 0])
    # 2 originals + 2 mirrored = 4.
    assert len(u.children) == 4


def test_mirror_copy_kwarg_form_no_shapes_raises():
    with pytest.raises(ValidationError, match="at least one shape"):
        mirror_copy(normal=[1, 0, 0])


def test_mirror_copy_positional_form_without_shapes_raises():
    with pytest.raises(ValidationError):
        mirror_copy([1, 0, 0])  # normal only, no shapes


def test_mirror_copy_both_forms_produce_same_bbox():
    a = bbox(mirror_copy([1, 0, 0], cube(5).translate([3, 0, 0])))
    b = bbox(mirror_copy(cube(5).translate([3, 0, 0]), normal=[1, 0, 0]))
    assert a.min == b.min and a.max == b.max
