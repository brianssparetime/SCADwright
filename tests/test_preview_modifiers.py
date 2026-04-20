"""Tests for preview modifiers (#, %, *, !)."""

import pytest

from scadwright import bbox, emit_str
from scadwright.primitives import cube, cylinder
from scadwright.transforms import background, disable, highlight, only


def test_highlight_emits_hash_sigil():
    out = emit_str(cube(10).highlight())
    assert "#cube" in out


def test_background_emits_percent_sigil():
    out = emit_str(cube(10).background())
    assert "%cube" in out


def test_disable_emits_star_sigil():
    out = emit_str(cube(10).disable())
    assert "*cube" in out


def test_only_emits_bang_sigil():
    out = emit_str(cube(10).only())
    assert "!cube" in out


def test_sigil_on_nested_transform():
    out = emit_str(cube(10).translate([5, 0, 0]).highlight())
    # Sigil attaches to the outermost statement.
    assert "#translate" in out
    assert "cube" in out


def test_standalone_and_chained_same_ast():
    a = highlight(cube(10))
    b = cube(10).highlight()
    assert type(a) is type(b) and a.mode == b.mode


def test_highlight_passes_bbox_through():
    bb = bbox(cube(10).highlight())
    assert bb.max == (10.0, 10.0, 10.0)


def test_background_passes_bbox_through():
    bb = bbox(cylinder(h=5, r=3, fn=16).background())
    assert bb.max[2] == 5.0


def test_only_passes_bbox_through():
    bb = bbox(cube(10).only())
    assert bb.max == (10.0, 10.0, 10.0)


def test_disable_collapses_bbox_to_zero():
    bb = bbox(cube(10).disable())
    assert bb.min == (0.0, 0.0, 0.0)
    assert bb.max == (0.0, 0.0, 0.0)


def test_modifier_composition():
    # Stack multiple modifiers (legal in SCAD; innermost is applied first).
    out = emit_str(cube(10).highlight().translate([1, 0, 0]))
    # Outer translate wraps the highlighted cube.
    assert "translate" in out
    assert "#cube" in out
