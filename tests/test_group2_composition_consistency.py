"""MajorReview2 Group 2 — composition helper signature consistency.

- `node.mirror_copy(normal=...)` alias matches the standalone form.
- Standalone `rotate_copy` defaults `n=4`; `n` is keyword-only to avoid
  ambiguity with the variadic `*children`.
"""

import pytest

from scadwright import bbox, emit_str
from scadwright.ast.csg import Union
from scadwright.ast.transforms import Mirror, Rotate
from scadwright.composition_helpers import mirror_copy, rotate_copy
from scadwright.errors import ValidationError
from scadwright.primitives import cube, sphere


# --- 2a: mirror_copy chained gains normal= kwarg ---


def test_chained_mirror_copy_normal_kwarg_works():
    result = cube(1).mirror_copy(normal=[1, 0, 0])
    assert isinstance(result, Union)
    assert len(result.children) == 2
    assert isinstance(result.children[1], Mirror)
    assert result.children[1].normal == (1.0, 0.0, 0.0)


def test_chained_mirror_copy_normal_matches_positional_vector():
    a = cube(1).mirror_copy([1, 0, 0])
    b = cube(1).mirror_copy(normal=[1, 0, 0])
    assert a.children[1].normal == b.children[1].normal


def test_chained_mirror_copy_xyz_kwargs_still_work():
    result = cube(1).mirror_copy(x=1)
    assert result.children[1].normal == (1.0, 0.0, 0.0)


def test_chained_mirror_copy_both_v_and_normal_raises():
    with pytest.raises(ValidationError, match="not both"):
        cube(1).mirror_copy(v=[1, 0, 0], normal=[0, 1, 0])


def test_chained_and_standalone_mirror_copy_produce_same_normal():
    chained = cube(1).mirror_copy(normal=[1, 0, 0])
    standalone = mirror_copy(cube(1), normal=[1, 0, 0])
    assert chained.children[1].normal == standalone.children[1].normal


# --- 2b: rotate_copy standalone defaults n=4, n is keyword-only ---


def test_standalone_rotate_copy_default_n():
    result = rotate_copy(60, cube(5).translate([10, 0, 0]))
    # 4 copies (default n).
    assert isinstance(result, Union)
    assert len(result.children) == 4


def test_standalone_rotate_copy_explicit_n_kwarg():
    result = rotate_copy(60, cube(5).translate([10, 0, 0]), n=6)
    assert len(result.children) == 6


def test_standalone_rotate_copy_variadic_children_with_default_n():
    result = rotate_copy(
        60,
        cube(3).translate([10, 0, 0]),
        sphere(r=1, fn=8).translate([10, 0, 5]),
    )
    # 2 originals + 2 originals × 3 extra rotations = 2 + 6 = 8.
    assert len(result.children) == 8


def test_standalone_rotate_copy_axis_kwarg():
    result = rotate_copy(90, cube(3).translate([10, 0, 0]), n=2, axis=[1, 0, 0])
    rotated = result.children[1]
    assert isinstance(rotated, Rotate)
    assert rotated.v == (1.0, 0.0, 0.0)


def test_standalone_rotate_copy_positional_n_no_longer_accepted():
    """n moved to keyword-only; calling with n as second positional
    now interprets it as a child, which isn't a Node → TypeError."""
    with pytest.raises((TypeError, ValidationError)):
        rotate_copy(60, 6, cube(3))


def test_chained_rotate_copy_default_n_unchanged():
    """The chained method already had n=4 default; verify unchanged."""
    result = cube(3).translate([10, 0, 0]).rotate_copy(60)
    assert len(result.children) == 4


def test_chained_rotate_copy_matches_standalone_with_same_args():
    shape = cube(3).translate([10, 0, 0])
    chained = shape.rotate_copy(60, n=6, axis=[0, 0, 1])
    standalone = rotate_copy(60, shape, n=6, axis=[0, 0, 1])
    # Both produce Union with 6 children; shape-level contents match.
    assert len(chained.children) == len(standalone.children) == 6
    # Compare the rotate step at index 1.
    c_rot = chained.children[1]
    s_rot = standalone.children[1]
    assert c_rot.a == s_rot.a
    assert c_rot.v == s_rot.v
