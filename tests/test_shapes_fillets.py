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
    b = ChamferedBox(size=(20, 15, 10), chamfer=2)
    scad = emit_str(b)
    assert "intersection" in scad


def test_chamfered_box_both_raises():
    with pytest.raises(ValidationError, match="fillet or chamfer, not both"):
        ChamferedBox(size=(20, 15, 10), fillet=2, chamfer=2)


def test_chamfered_box_neither_raises():
    with pytest.raises(ValidationError, match="specify either fillet or chamfer"):
        ChamferedBox(size=(20, 15, 10))


def test_chamfered_box_too_small_raises():
    with pytest.raises(ValidationError, match="must be >"):
        ChamferedBox(size=(4, 4, 4), fillet=3)


# --- Countersink ---


def test_countersink_builds():
    c = Countersink(shaft_d=3, head_d=6, head_depth=2, shaft_depth=10)
    scad = emit_str(c)
    assert "cylinder" in scad


def test_countersink_bbox():
    c = Countersink(shaft_d=3, head_d=6, head_depth=2, shaft_depth=10)
    bb = bbox(c)
    assert bb.size[2] == pytest.approx(12.0, abs=0.1)
    assert bb.max[0] == pytest.approx(3.0, abs=0.1)  # head_d/2


# --- Counterbore ---


def test_counterbore_builds():
    c = Counterbore(shaft_d=3, head_d=6, head_depth=3, shaft_depth=10)
    scad = emit_str(c)
    assert "cylinder" in scad


def test_counterbore_bbox():
    c = Counterbore(shaft_d=3, head_d=6, head_depth=3, shaft_depth=10)
    bb = bbox(c)
    assert bb.size[2] == pytest.approx(13.0, abs=0.1)
    assert bb.max[0] == pytest.approx(3.0, abs=0.1)  # head_d/2
