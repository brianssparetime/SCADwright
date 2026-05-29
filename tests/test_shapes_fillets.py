"""Tests for fillets subpackage."""

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import (
    ChamferMask,
    ChamferedBox,
    Counterbore,
    Countersink,
    FilletMask,
    counterbore_for_screw,
    countersink_for_screw,
)


# --- FilletMask ---


def test_fillet_mask_z():
    m = FilletMask(r=3, length=10, axis="z")
    bb = bbox(m)
    assert bb.size[2] == pytest.approx(10.0, abs=0.1)


def test_fillet_mask_x():
    m = FilletMask(r=3, length=10, axis="x")
    bb = bbox(m)
    assert bb.size[0] == pytest.approx(10.0, abs=0.1)


def test_fillet_mask_emits_difference():
    assert "difference" in emit_str(FilletMask(r=2, length=5))


# --- ChamferMask ---


def test_chamfer_mask_z():
    m = ChamferMask(size=3, length=10, axis="z")
    bb = bbox(m)
    assert bb.size[2] == pytest.approx(10.0, abs=0.1)


def test_chamfer_mask_emits():
    scad = emit_str(ChamferMask(size=2, length=5))
    assert "difference" in scad


# --- ChamferedBox ---


def test_chamfered_box_fillet():
    b = ChamferedBox(size=(20, 15, 10), fillet=2)
    bb = bbox(b)
    assert bb.size[0] == pytest.approx(20.0, abs=0.5)
    assert bb.size[2] == pytest.approx(10.0, abs=0.5)


def test_chamfered_box_chamfer():
    """Chamfer via minkowski with an octahedron — produces 45° bevels.

    Outer dimensions are preserved (inner cube + octahedron radius
    sums back to size). The previous cylinder-intersection formula
    was broken (cylinders too large to clip the box at all).
    """
    b = ChamferedBox(size=(20, 15, 10), chamfer=2)
    scad = emit_str(b)
    assert "minkowski" in scad
    assert "polyhedron" in scad
    bb = bbox(b)
    assert bb.size[0] == pytest.approx(20.0, abs=0.01)
    assert bb.size[1] == pytest.approx(15.0, abs=0.01)
    assert bb.size[2] == pytest.approx(10.0, abs=0.01)


def test_chamfered_box_both_raises():
    with pytest.raises(ValidationError, match=r"exactly_one\(fillet, chamfer\)"):
        ChamferedBox(size=(20, 15, 10), fillet=2, chamfer=2)


def test_chamfered_box_neither_raises():
    with pytest.raises(ValidationError, match=r"exactly_one\(fillet, chamfer\)"):
        ChamferedBox(size=(20, 15, 10))


def test_chamfered_box_too_small_raises():
    with pytest.raises(ValidationError, match=r"all\(s > 2 \*"):
        ChamferedBox(size=(4, 4, 4), fillet=3)


# --- Countersink ---


def test_countersink_builds():
    c = Countersink(shaft_d=3, head_d=6, head_depth=2, shaft_depth=10)
    scad = emit_str(c)
    assert "rotate_extrude" in scad
    assert "polygon" in scad


def test_countersink_bbox():
    c = Countersink(shaft_d=3, head_d=6, head_depth=2, shaft_depth=10)
    bb = bbox(c)
    assert bb.size[2] == pytest.approx(12.0, abs=0.1)
    assert bb.max[0] == pytest.approx(3.0, abs=0.1)  # head_d/2


def test_countersink_is_single_solid_no_internal_union():
    """Regression: built as a single rotate_extrude, not a union of
    cylinders. The cylinder-stack form had a coincident annular face
    at z=shaft_depth that produced visible CSG artifacts when the
    Component was used as a difference cutter."""
    c = Countersink(shaft_d=3, head_d=6, head_depth=2, shaft_depth=10)
    scad = emit_str(c)
    assert "union" not in scad
    assert "cylinder" not in scad


# --- Counterbore ---


def test_counterbore_builds():
    c = Counterbore(shaft_d=3, head_d=6, head_depth=3, shaft_depth=10)
    scad = emit_str(c)
    assert "rotate_extrude" in scad
    assert "polygon" in scad


def test_counterbore_bbox():
    c = Counterbore(shaft_d=3, head_d=6, head_depth=3, shaft_depth=10)
    bb = bbox(c)
    assert bb.size[2] == pytest.approx(13.0, abs=0.1)
    assert bb.max[0] == pytest.approx(3.0, abs=0.1)  # head_d/2


def test_counterbore_is_single_solid_no_internal_union():
    """Regression: built as a single rotate_extrude, not a union of
    cylinders. The cylinder-stack form had a coincident annular face
    at z=shaft_depth that produced visible CSG artifacts when the
    Component was used as a difference cutter."""
    c = Counterbore(shaft_d=3, head_d=6, head_depth=3, shaft_depth=10)
    scad = emit_str(c)
    assert "union" not in scad
    assert "cylinder" not in scad


# --- Screw-spec factories ---


def test_counterbore_for_screw_pulls_dims_from_spec():
    # M3 socket: clearance_d=3.4, head_d=5.5, head_h=3.0
    c = counterbore_for_screw("M3", shaft_depth=10)
    assert c.shaft_d == pytest.approx(3.4)
    assert c.head_d == pytest.approx(5.5)
    assert c.head_depth == pytest.approx(3.0)
    assert c.shaft_depth == 10


def test_counterbore_for_screw_button_head_differs():
    # M3 button: head_d=5.7, head_h=1.5 (vs socket 5.5/3.0)
    c = counterbore_for_screw("M3", shaft_depth=10, head="button")
    assert c.head_d == pytest.approx(5.7)
    assert c.head_depth == pytest.approx(1.5)


def test_countersink_for_screw_pulls_dims_from_spec():
    c = countersink_for_screw("M5", shaft_depth=20)
    # M5 socket: clearance_d=5.5, head_d=8.5, head_h=5.0
    assert c.shaft_d == pytest.approx(5.5)
    assert c.head_d == pytest.approx(8.5)
    assert c.head_depth == pytest.approx(5.0)


def test_factory_returns_correct_type():
    assert isinstance(counterbore_for_screw("M3", shaft_depth=10), Counterbore)
    assert isinstance(countersink_for_screw("M3", shaft_depth=10), Countersink)


# --- through= kwarg: ergonomic depth-from-host-thickness ---


def test_counterbore_for_screw_through_subtracts_head_h():
    """through=plate_thk computes shaft_depth = plate_thk - head_h so
    the head bore sits inside the parent. M3 socket head_h=3.0; passing
    through=10 should yield shaft_depth=7."""
    c = counterbore_for_screw("M3", through=10)
    assert c.shaft_depth == pytest.approx(10 - 3.0)
    # Full cutter length still equals plate_thk; head sits above shaft.
    assert c.shaft_depth + c.head_depth == pytest.approx(10)


def test_counterbore_for_screw_requires_exactly_one_depth_kwarg():
    """Both kwargs together → ambiguous; neither → no information."""
    from scadwright.errors import ValidationError
    with pytest.raises(ValidationError, match="exactly one of through"):
        counterbore_for_screw("M3", shaft_depth=10, through=10)
    with pytest.raises(ValidationError, match="exactly one of through"):
        counterbore_for_screw("M3")


def test_counterbore_for_screw_through_too_small_raises():
    """through < head_h means the head bore alone doesn't fit; the
    factory raises rather than producing a degenerate negative-shaft
    geometry."""
    from scadwright.errors import ValidationError
    # M3 head_h = 3.0; through=2 is shorter than head_h.
    with pytest.raises(ValidationError, match="less than the head height"):
        counterbore_for_screw("M3", through=2)


def test_countersink_for_screw_through_subtracts_head_h():
    """Same through= semantics on countersink_for_screw."""
    c = countersink_for_screw("M5", through=12)
    # M5 socket: head_h=5.0
    assert c.shaft_depth == pytest.approx(12 - 5.0)


def test_countersink_for_screw_requires_exactly_one_depth_kwarg():
    from scadwright.errors import ValidationError
    with pytest.raises(ValidationError, match="exactly one of through"):
        countersink_for_screw("M3", shaft_depth=10, through=10)
    with pytest.raises(ValidationError, match="exactly one of through"):
        countersink_for_screw("M3")


# --- tip anchor (consistency with Bolt.tip) ---


def test_counterbore_publishes_tip_anchor():
    c = Counterbore(shaft_d=3, head_d=6, head_depth=3, shaft_depth=10)
    anchors = c.get_anchors()
    assert "tip" in anchors
    assert anchors["tip"].position == (0, 0, 0)
    assert anchors["tip"].normal == (0, 0, -1)


def test_countersink_publishes_tip_anchor():
    c = Countersink(shaft_d=3, head_d=6, head_depth=2, shaft_depth=10)
    anchors = c.get_anchors()
    assert "tip" in anchors
    assert anchors["tip"].position == (0, 0, 0)
    assert anchors["tip"].normal == (0, 0, -1)
