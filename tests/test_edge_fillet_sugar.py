"""Tests for the .fillet() / .chamfer() methods on Cube and Cylinder.

These are sugar over FilletMask / ChamferMask / a custom rotate_extrude
profile. See src/scadwright/ast/_edge_fillets.py.
"""

import math

import pytest

from scadwright import bbox, emit_str, tree_hash
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder


# --- Cube: all 12 edges resolve, preserve bbox, emit a difference ---


@pytest.mark.parametrize("edge", [
    "top_front", "top_back", "top_lside", "top_rside",
    "bottom_front", "bottom_back", "bottom_lside", "bottom_rside",
    "front_lside", "front_rside", "back_lside", "back_rside",
])
def test_cube_fillet_each_edge_preserves_bbox(edge):
    """A fillet only carves inward, so the bbox stays the same."""
    c = cube([10, 20, 30]).fillet(edge, r=2)
    bb = bbox(c)
    assert bb.size == pytest.approx((10.0, 20.0, 30.0))
    scad = emit_str(c)
    assert "difference" in scad


@pytest.mark.parametrize("edge", [
    "top_front", "top_back", "top_lside", "top_rside",
    "bottom_front", "bottom_back", "bottom_lside", "bottom_rside",
    "front_lside", "front_rside", "back_lside", "back_rside",
])
def test_cube_chamfer_each_edge_preserves_bbox(edge):
    c = cube([10, 20, 30]).chamfer(edge, size=2)
    bb = bbox(c)
    assert bb.size == pytest.approx((10.0, 20.0, 30.0))
    scad = emit_str(c)
    assert "difference" in scad


# --- Group selectors ---


def test_cube_fillet_group_top_expands_to_4_edges():
    """`fillet("top", r=...)` rounds all 4 top edges. Visually this means
    the bbox stays the same but the geometry has been carved 4× from
    the FilletMask references."""
    c = cube([10, 20, 30]).fillet("top", r=2)
    scad = emit_str(c)
    # FilletMask occurrences: 4 (one per top edge).
    assert scad.count("// FilletMask") == 4 or scad.count("FilletMask") == 4


def test_cube_fillet_group_bottom_expands_to_4_edges():
    c = cube([10, 20, 30]).fillet("bottom", r=2)
    scad = emit_str(c)
    assert scad.count("// FilletMask") == 4 or scad.count("FilletMask") == 4


def test_cube_fillet_group_vertical_expands_to_4_edges():
    c = cube([10, 20, 30]).fillet("vertical", r=2)
    scad = emit_str(c)
    assert scad.count("// FilletMask") == 4 or scad.count("FilletMask") == 4


def test_cube_fillet_list_of_groups_no_duplicates():
    """`["top", "bottom"]` should expand to 8 edges (top 4 + bottom 4) with
    no duplicates from the vertical group."""
    c = cube([10, 20, 30]).fillet(["top", "bottom"], r=2)
    scad = emit_str(c)
    assert scad.count("// FilletMask") == 8 or scad.count("FilletMask") == 8


def test_cube_fillet_list_of_individual_edges():
    """List form accepts individual edge names."""
    c = cube([10, 20, 30]).fillet(["top_front", "top_back"], r=2)
    scad = emit_str(c)
    assert scad.count("// FilletMask") == 2 or scad.count("FilletMask") == 2


def test_cube_fillet_mixed_group_and_individual():
    """Mixing a group with individual edges works (and dedupes)."""
    c1 = cube([10, 20, 30]).fillet(["top", "top_front"], r=2)
    c2 = cube([10, 20, 30]).fillet("top", r=2)
    # `["top", "top_front"]` should be the same as `"top"` (dedup).
    assert tree_hash(c1) == tree_hash(c2)


# --- Centered cubes ---


def test_cube_fillet_fully_centered_cube():
    c = cube([10, 10, 10], center=True).fillet("vertical", r=1)
    bb = bbox(c)
    assert bb.center == pytest.approx((0.0, 0.0, 0.0))
    assert bb.size == pytest.approx((10.0, 10.0, 10.0))


def test_cube_fillet_partially_centered_cube_xy():
    c = cube([10, 10, 10], center="xy").fillet("top", r=1)
    bb = bbox(c)
    # Centered in x, y; not in z.
    assert bb.center[0] == pytest.approx(0.0)
    assert bb.center[1] == pytest.approx(0.0)
    assert bb.min[2] == pytest.approx(0.0)
    assert bb.max[2] == pytest.approx(10.0)


# --- Empty / error cases ---


def test_cube_fillet_unknown_edge_name_raises():
    with pytest.raises(ValidationError, match="unknown edge name"):
        cube([10, 10, 10]).fillet("middle_left", r=2)


def test_cube_fillet_radius_too_big_raises():
    with pytest.raises(ValidationError, match="exceeds half"):
        cube([4, 4, 10]).fillet("top_front", r=3)


def test_cube_fillet_radius_zero_raises():
    with pytest.raises(ValidationError, match="must be positive"):
        cube([10, 10, 10]).fillet("top_front", r=0)


def test_cube_fillet_negative_radius_raises():
    with pytest.raises(ValidationError, match="must be positive"):
        cube([10, 10, 10]).fillet("top_front", r=-1)


def test_cube_fillet_non_string_edges_raises():
    with pytest.raises(ValidationError, match="must be a string"):
        cube([10, 10, 10]).fillet(42, r=2)


# --- Rotated primitives don't have .fillet (by design) ---


def test_rotated_cube_has_no_fillet_method():
    """`cube(...).rotate(...)` returns a Rotate node, not a Cube. Calling
    .fillet on the result is an AttributeError from Python — the user's
    traceback points at their call line. This is the type-system way to
    keep the scope honest."""
    rotated = cube([10, 10, 10]).rotate([0, 0, 30])
    with pytest.raises(AttributeError, match="fillet"):
        rotated.fillet("top_front", r=2)


# --- Chains naturally ---


def test_cube_fillet_chains_with_other_transforms():
    """The result of .fillet is a normal Node — translate, rotate, color
    all chain off it."""
    c = cube([10, 10, 10]).fillet("top", r=2).up(5).red()
    bb = bbox(c)
    assert bb.min[2] == pytest.approx(5.0)
    assert bb.max[2] == pytest.approx(15.0)


# --- tight_bbox honors the design-doc contract ---


def test_cube_fillet_tight_bbox_matches_cube_bbox():
    """A fillet only carves inward, so tight_bbox of the result equals
    the cube's bbox. Without the _carved transform's tight_bbox hook,
    the inner Difference would raise."""
    from scadwright import tight_bbox
    c = cube([10, 20, 30]).fillet("top", r=2)
    tb = tight_bbox(c)
    assert tb.size == pytest.approx((10.0, 20.0, 30.0))


def test_cube_chamfer_tight_bbox_matches_cube_bbox():
    from scadwright import tight_bbox
    c = cube([10, 20, 30]).chamfer("vertical", size=2)
    tb = tight_bbox(c)
    assert tb.size == pytest.approx((10.0, 20.0, 30.0))


def test_cylinder_fillet_tight_bbox_matches_cylinder_bbox():
    from scadwright import tight_bbox
    cy = cylinder(h=10, r=5).fillet("top_rim", r=1)
    tb = tight_bbox(cy)
    assert tb.size == pytest.approx((10.0, 10.0, 10.0))


def test_filleted_shapes_compose_with_pack_on_bed():
    """pack_on_bed uses tight_bbox; filleted shapes must support it."""
    from scadwright.composition_helpers import pack_on_bed
    packed = pack_on_bed(
        cube([10, 20, 5]).fillet("top", r=1),
        cube([15, 10, 5]).chamfer("vertical", size=1),
        cylinder(h=5, r=4).fillet("top_rim", r=1),
        plate=(200, 200),
    )
    bb = bbox(packed)
    # Smoke check: pack_on_bed produced a reasonable composite without raising.
    assert bb.size[2] == pytest.approx(5.0)


# --- Cylinder rim ---


def test_cylinder_fillet_top_rim():
    cy = cylinder(h=10, r=5).fillet("top_rim", r=1)
    bb = bbox(cy)
    # Bbox preserved (fillet only carves inward at the rim).
    assert bb.size[2] == pytest.approx(10.0)
    scad = emit_str(cy)
    assert "rotate_extrude" in scad


def test_cylinder_fillet_bottom_rim():
    cy = cylinder(h=10, r=5).fillet("bottom_rim", r=1)
    bb = bbox(cy)
    assert bb.size[2] == pytest.approx(10.0)


def test_cylinder_chamfer_top_rim():
    cy = cylinder(h=10, r=5).chamfer("top_rim", size=1)
    bb = bbox(cy)
    assert bb.size[2] == pytest.approx(10.0)
    scad = emit_str(cy)
    assert "rotate_extrude" in scad


def test_cylinder_fillet_invalid_rim_name_raises():
    with pytest.raises(ValidationError, match="rim must be"):
        cylinder(h=10, r=5).fillet("middle_rim", r=1)


def test_cylinder_fillet_cone_raises():
    with pytest.raises(ValidationError, match="cone cylinders"):
        cylinder(h=10, r1=5, r2=2).fillet("top_rim", r=1)


def test_cylinder_chamfer_cone_raises():
    with pytest.raises(ValidationError, match="cone cylinders"):
        cylinder(h=10, r1=5, r2=2).chamfer("top_rim", size=1)


def test_cylinder_fillet_radius_exceeds_dimensions_raises():
    # r exceeds cylinder radius
    with pytest.raises(ValidationError, match="exceeds the cylinder"):
        cylinder(h=10, r=2).fillet("top_rim", r=3)
    # r exceeds half the height
    with pytest.raises(ValidationError, match="exceeds the cylinder"):
        cylinder(h=2, r=10).fillet("top_rim", r=5)


def test_cylinder_fillet_centered_cylinder():
    """Centered cylinder rim fillet: preserves bbox center on z."""
    cy = cylinder(h=10, r=5, center=True).fillet("top_rim", r=1)
    bb = bbox(cy)
    assert bb.center[2] == pytest.approx(0.0)
    assert bb.size[2] == pytest.approx(10.0)
