"""Tests for the surface primitive (heightmap import)."""

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import surface


def test_surface_minimal_emit():
    out = emit_str(surface("h.png"), banner=False).strip()
    assert out == 'surface(file="h.png");'


def test_surface_center_and_invert_and_convexity():
    out = emit_str(surface("h.png", center=True, invert=True, convexity=5))
    assert "center=true" in out
    assert "invert=true" in out
    assert "convexity=5" in out


def test_surface_path_escaping():
    out = emit_str(surface('with "quotes"/path.png'))
    assert r'\"quotes\"' in out


def test_surface_rejects_empty_filename():
    with pytest.raises(ValidationError, match="non-empty string"):
        surface("")


def test_surface_rejects_non_string():
    with pytest.raises(ValidationError, match="non-empty string"):
        surface(42)


def test_surface_bbox_is_degenerate():
    # Surface extent isn't inspectable without reading the file; bbox is zero.
    bb = bbox(surface("anything.png"))
    assert bb.min == (0.0, 0.0, 0.0)
    assert bb.max == (0.0, 0.0, 0.0)


def test_surface_chained_through_transform():
    # Transforms should compose even with a degenerate surface bbox.
    out = emit_str(surface("h.png").translate([5, 0, 0]))
    assert "translate([5, 0, 0])" in out
    assert "surface(" in out
