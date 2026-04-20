"""Tests for force_render (SCAD's render(convexity=...))."""

from scadwright import bbox, emit_str
from scadwright.ast.transforms import ForceRender
from scadwright.debug import force_render
from scadwright.primitives import cube


def test_force_render_emit_no_convexity():
    out = emit_str(cube(10).force_render())
    assert "render()" in out
    assert "cube" in out


def test_force_render_emit_with_convexity():
    out = emit_str(cube(10).force_render(convexity=5))
    assert "render(convexity=5)" in out


def test_force_render_bbox_passes_through():
    bb = bbox(cube(10).force_render())
    assert bb.min == (0.0, 0.0, 0.0)
    assert bb.max == (10.0, 10.0, 10.0)


def test_standalone_matches_chained():
    a = force_render(cube(5), convexity=2)
    b = cube(5).force_render(convexity=2)
    assert isinstance(a, ForceRender) and isinstance(b, ForceRender)
    assert a.convexity == b.convexity


def test_force_render_composes_with_other_transforms():
    out = emit_str(cube(10).force_render().translate([5, 0, 0]))
    assert "translate" in out and "render()" in out
