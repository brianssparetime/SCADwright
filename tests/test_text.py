"""Tests for the 2D text primitive."""

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import text


# --- Emit ---


def test_text_minimal_emit():
    out = emit_str(text("Hello"), banner=False).strip()
    assert out == 'text("Hello");'


def test_text_non_default_size():
    out = emit_str(text("Hi", size=20))
    assert 'size=20' in out


def test_text_halign_valign():
    out = emit_str(text("X", halign="center", valign="center"))
    assert 'halign="center"' in out
    assert 'valign="center"' in out


def test_text_font_emitted_when_set():
    out = emit_str(text("A", font="Liberation Sans"))
    assert 'font="Liberation Sans"' in out


def test_text_escapes_quotes():
    out = emit_str(text('a "b" c'))
    assert r'\"b\"' in out


def test_text_escapes_backslash_and_newline():
    out = emit_str(text("line1\nline2"))
    assert r"\n" in out


def test_text_emits_fn():
    # Uniform fn gets hoisted to file-top `$fn = 24;`. Accept either form.
    out = emit_str(text("X", fn=24))
    assert "$fn = 24" in out or "$fn=24" in out


# --- Validation ---


def test_text_rejects_non_string():
    with pytest.raises(ValidationError, match="must be a string"):
        text(42)


def test_text_rejects_invalid_halign():
    with pytest.raises(ValidationError, match="halign"):
        text("X", halign="middle")


def test_text_rejects_invalid_valign():
    with pytest.raises(ValidationError, match="valign"):
        text("X", valign="above")


def test_text_rejects_invalid_direction():
    with pytest.raises(ValidationError, match="direction"):
        text("X", direction="diagonal")


def test_text_rejects_non_positive_size():
    with pytest.raises(ValidationError, match="positive"):
        text("X", size=0)


# --- Bbox (estimated) ---


def test_text_bbox_left_baseline():
    bb = bbox(text("ABCDE", size=10, halign="left", valign="baseline"))
    # Width ≈ 0.6 * 10 * 1 * 5 = 30; baseline y ∈ [-2, 8]
    assert bb.min == pytest.approx((0.0, -2.0, 0.0))
    assert bb.max == pytest.approx((30.0, 8.0, 0.0))


def test_text_bbox_center_halign():
    bb = bbox(text("ABCDE", size=10, halign="center", valign="baseline"))
    assert bb.min[0] == pytest.approx(-15.0)
    assert bb.max[0] == pytest.approx(15.0)


def test_text_bbox_right_halign():
    bb = bbox(text("ABCDE", size=10, halign="right", valign="baseline"))
    assert bb.min[0] == pytest.approx(-30.0)
    assert bb.max[0] == pytest.approx(0.0)


def test_text_bbox_top_valign():
    bb = bbox(text("X", size=10, valign="top"))
    assert bb.min[1] == pytest.approx(-10.0)
    assert bb.max[1] == pytest.approx(0.0)


def test_text_bbox_bottom_valign():
    bb = bbox(text("X", size=10, valign="bottom"))
    assert bb.min[1] == pytest.approx(0.0)
    assert bb.max[1] == pytest.approx(10.0)


def test_text_bbox_center_valign():
    bb = bbox(text("X", size=10, valign="center"))
    assert bb.min[1] == pytest.approx(-5.0)
    assert bb.max[1] == pytest.approx(5.0)


def test_text_bbox_honors_spacing():
    bb_default = bbox(text("AB", size=10, spacing=1.0))
    bb_wide = bbox(text("AB", size=10, spacing=2.0))
    assert bb_wide.max[0] == pytest.approx(bb_default.max[0] * 2)


def test_text_extruded_bbox_has_z():
    bb = bbox(text("Label", size=5).linear_extrude(height=2))
    assert bb.min[2] == 0.0
    assert bb.max[2] == 2.0
