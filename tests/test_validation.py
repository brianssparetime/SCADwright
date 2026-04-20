import pytest

from scadwright.boolops import union
from scadwright.errors import ValidationError
from scadwright.extrusions import linear_extrude
from scadwright.primitives import circle, cube, cylinder, polyhedron, sphere
# --- cube ---


def test_cube_negative_size_rejected():
    with pytest.raises(ValidationError, match="non-negative"):
        cube([-1, 2, 3])


def test_cube_string_rejected():
    with pytest.raises(ValidationError):
        cube("ten")


def test_cube_short_vector_rejected():
    with pytest.raises(ValidationError, match="exactly 3"):
        cube([1, 2])


def test_cube_long_vector_rejected():
    with pytest.raises(ValidationError, match="exactly 3"):
        cube([1, 2, 3, 4])


def test_cube_nan_rejected():
    import math

    with pytest.raises(ValidationError, match="finite"):
        cube(math.nan)


# --- sphere / circle / cylinder ---


def test_sphere_negative_radius_rejected():
    with pytest.raises(ValidationError, match="positive"):
        sphere(r=-1)


def test_sphere_zero_radius_rejected():
    with pytest.raises(ValidationError, match="positive"):
        sphere(r=0)


def test_circle_negative_radius_rejected():
    with pytest.raises(ValidationError):
        circle(r=-1)


def test_cylinder_negative_height_rejected():
    with pytest.raises(ValidationError, match="non-negative"):
        cylinder(h=-1, r=1)


# --- transforms ---


def test_translate_scalar_rejected_as_ambiguous():
    """Phase 1 quietly accepted translate(5). Phase 3 rejects."""
    with pytest.raises(ValidationError, match="scalar not accepted"):
        cube(1).translate(5)


def test_translate_string_rejected():
    with pytest.raises(ValidationError):
        cube(1).translate("x")


def test_translate_short_vec_rejected():
    with pytest.raises(ValidationError, match="exactly 3"):
        cube(1).translate([1, 2])


def test_translate_non_numeric_kwarg_rejected():
    with pytest.raises(ValidationError):
        cube(1).translate(x="five")


# --- polyhedron ---


def test_polyhedron_empty_points_rejected():
    with pytest.raises(ValidationError, match="non-empty"):
        polyhedron(points=[], faces=[[0, 1, 2]])


def test_polyhedron_face_index_out_of_range():
    with pytest.raises(ValidationError, match="out of range"):
        polyhedron(
            points=[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            faces=[[0, 1, 99]],
        )


def test_polyhedron_face_too_few_indices():
    with pytest.raises(ValidationError, match="at least 3"):
        polyhedron(
            points=[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            faces=[[0, 1]],
        )


# --- csg ---


def test_empty_union_rejected():
    with pytest.raises(ValidationError, match="at least one"):
        union()


def test_union_non_node_rejected():
    with pytest.raises(ValidationError):
        union(cube(1), "hello")


# --- source location in error ---


def test_validation_error_carries_source_location():
    import inspect

    line = inspect.currentframe().f_lineno
    try:
        cube([-1, 2, 3])  # line line+2
    except ValidationError as e:
        assert e.source_location is not None
        assert e.source_location.file.endswith("test_validation.py")
        assert e.source_location.line == line + 2
    else:
        raise AssertionError("expected ValidationError")


# --- extrudes ---


def test_linear_extrude_non_node_child_rejected():
    with pytest.raises(ValidationError, match="Node"):
        linear_extrude("not a node", height=5)


def test_linear_extrude_non_positive_height_rejected():
    with pytest.raises(ValidationError, match="positive"):
        linear_extrude(circle(r=1), height=0)
