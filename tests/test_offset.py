"""Tests for the 2D offset operation."""

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import circle, square
from scadwright.transforms import offset as offset_fn


def test_offset_r_emits_rounded_form():
    out = emit_str(circle(r=5, fn=16).offset(r=2))
    assert "offset(r=2)" in out


def test_offset_delta_emits_sharp_form():
    out = emit_str(square([4, 4]).offset(delta=1))
    assert "offset(delta=1)" in out


def test_offset_delta_chamfer():
    out = emit_str(square([4, 4]).offset(delta=1, chamfer=True))
    assert "delta=1" in out and "chamfer=true" in out


def test_offset_negative_r_contracts():
    out = emit_str(square([10, 10]).offset(r=-1))
    assert "offset(r=-1)" in out


def test_offset_requires_r_or_delta():
    with pytest.raises(ValidationError, match="exactly one"):
        circle(r=5).offset()


def test_offset_rejects_both_r_and_delta():
    with pytest.raises(ValidationError, match="exactly one"):
        circle(r=5).offset(r=1, delta=2)


def test_offset_chamfer_with_r_raises():
    with pytest.raises(ValidationError, match="chamfer"):
        circle(r=5).offset(r=1, chamfer=True)


def test_offset_bbox_expands_xy():
    bb = bbox(square([10, 10]).offset(r=2))
    assert bb.min == (-2.0, -2.0, 0.0)
    assert bb.max == (12.0, 12.0, 0.0)


def test_offset_bbox_contracts_on_negative():
    bb = bbox(square([10, 10]).offset(r=-2))
    assert bb.min == (2.0, 2.0, 0.0)
    assert bb.max == (8.0, 8.0, 0.0)


def test_offset_bbox_collapses_when_overcontracted():
    # -r larger than half the child extent -> would flip; degenerate bbox.
    bb = bbox(square([4, 4]).offset(r=-10))
    assert bb.min == bb.max  # degenerate


def test_offset_forwards_resolution():
    # Uniform fn gets hoisted to file-top `$fn = 32;`. Accept either form.
    out = emit_str(circle(r=5).offset(r=2, fn=32))
    assert "$fn = 32" in out or "$fn=32" in out


def test_standalone_offset_matches_chained():
    a = offset_fn(circle(r=5), r=2)
    b = circle(r=5).offset(r=2)
    assert type(a) is type(b)
    assert a.r == b.r


def test_offset_preserves_z_zero():
    bb = bbox(circle(r=5, fn=16).offset(r=2))
    assert bb.min[2] == 0.0 and bb.max[2] == 0.0
