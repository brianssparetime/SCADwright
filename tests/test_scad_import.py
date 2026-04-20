"""Tests for scad_import (external geometry via SCAD's import())."""

import struct

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import scad_import


# --- Emit ---


def test_minimal_emit():
    out = emit_str(scad_import("part.stl"), banner=False).strip()
    assert out == 'import(file="part.stl");'


def test_emit_with_all_kwargs():
    out = emit_str(scad_import(
        "part.dxf",
        convexity=5,
        layer="top",
        origin=(1.0, 2.0),
        scale=1.5,
        fn=32,
    ))
    assert 'file="part.dxf"' in out
    assert "convexity=5" in out
    assert 'layer="top"' in out
    assert "origin=[1, 2]" in out
    assert "scale=1.5" in out
    # Uniform fn gets hoisted to file-top `$fn = 32;`. Accept either form.
    assert "$fn = 32" in out or "$fn=32" in out


def test_path_escaping():
    out = emit_str(scad_import('with "quotes".stl'))
    assert r'\"quotes\"' in out


def test_bbox_hint_never_emitted():
    out = emit_str(scad_import("part.stl", bbox=((0, 0, 0), (1, 1, 1))))
    assert "bbox" not in out


# --- Validation ---


def test_rejects_non_string_file():
    with pytest.raises(ValidationError, match="non-empty string"):
        scad_import(42)


def test_rejects_empty_filename():
    with pytest.raises(ValidationError, match="non-empty string"):
        scad_import("")


def test_bbox_hint_wrong_shape_raises():
    with pytest.raises(ValidationError, match="bbox"):
        scad_import("x.stl", bbox=(1, 2, 3))


def test_bbox_hint_min_greater_than_max_raises():
    with pytest.raises(ValidationError, match="bbox min"):
        scad_import("x.stl", bbox=((10, 0, 0), (5, 1, 1)))


# --- Bbox resolution ---


def test_bbox_hint_is_returned():
    part = scad_import("profile.svg", bbox=((0, 0, 0), (50, 30, 0)))
    bb = bbox(part)
    assert bb.min == (0.0, 0.0, 0.0)
    assert bb.max == (50.0, 30.0, 0.0)


def test_non_stl_without_hint_is_degenerate():
    bb = bbox(scad_import("profile.svg"))
    assert bb.min == (0.0, 0.0, 0.0)
    assert bb.max == (0.0, 0.0, 0.0)


def test_missing_stl_without_hint_is_degenerate():
    bb = bbox(scad_import("/nonexistent/path.stl"))
    assert bb.min == (0.0, 0.0, 0.0)
    assert bb.max == (0.0, 0.0, 0.0)


def test_stl_auto_parse(tmp_path):
    """A real STL file should have its bbox inferred from triangle vertices."""
    from scadwright._stl import stl_bbox

    stl_bbox.cache_clear()
    path = tmp_path / "tri.stl"
    with open(path, "wb") as f:
        f.write(b"\x00" * 80)
        f.write(struct.pack("<I", 1))
        f.write(struct.pack("<fff", 0, 0, 1))  # normal
        f.write(struct.pack("<fff", 0, 0, 0))
        f.write(struct.pack("<fff", 10, 0, 3))
        f.write(struct.pack("<fff", 5, 8, 6))
        f.write(b"\x00\x00")
    bb = bbox(scad_import(str(path)))
    assert bb.min == (0.0, 0.0, 0.0)
    assert bb.max == (10.0, 8.0, 6.0)


def test_bbox_hint_wins_over_stl_auto_parse(tmp_path):
    """If the user provides a hint, it takes priority even for an STL."""
    from scadwright._stl import stl_bbox

    stl_bbox.cache_clear()
    path = tmp_path / "auto.stl"
    with open(path, "wb") as f:
        f.write(b"\x00" * 80)
        f.write(struct.pack("<I", 1))
        f.write(struct.pack("<fff", 0, 0, 1))
        f.write(struct.pack("<fff", 0, 0, 0))
        f.write(struct.pack("<fff", 10, 0, 0))
        f.write(struct.pack("<fff", 0, 10, 0))
        f.write(b"\x00\x00")
    part = scad_import(str(path), bbox=((0, 0, 0), (100, 100, 100)))
    bb = bbox(part)
    assert bb.max == (100.0, 100.0, 100.0)


# --- Composition ---


def test_imported_shape_composes_with_transforms():
    part = scad_import("fastener.stl").translate([5, 0, 0]).rotate([0, 0, 90])
    out = emit_str(part)
    assert "rotate" in out
    assert "translate" in out
    assert "import" in out


def test_imported_shape_in_difference():
    from scadwright.boolops import difference
    from scadwright.primitives import cube

    part = difference(cube(20), scad_import("hole.stl", bbox=((0, 0, 0), (5, 5, 5))))
    out = emit_str(part)
    assert "difference()" in out
    assert "import" in out


# --- Bbox hint sanity-check against STL auto-parse ---


def _make_stl(path, bbox):
    """Write a minimal binary STL spanning `bbox`."""
    mn, mx = bbox
    with open(path, "wb") as f:
        f.write(b"\x00" * 80)
        f.write(struct.pack("<I", 1))
        f.write(struct.pack("<fff", 0, 0, 1))  # normal
        f.write(struct.pack("<fff", mn[0], mn[1], mn[2]))
        f.write(struct.pack("<fff", mx[0], mn[1], mn[2]))
        f.write(struct.pack("<fff", mx[0], mx[1], mx[2]))
        f.write(b"\x00\x00")


def test_stl_hint_smaller_than_actual_warns(tmp_path):
    import warnings
    from scadwright._stl import stl_bbox
    from scadwright.api.factories import _scad_import_hint_warned

    stl_bbox.cache_clear()
    _scad_import_hint_warned.clear()
    path = tmp_path / "big.stl"
    _make_stl(path, ((0, 0, 0), (100, 100, 100)))

    with warnings.catch_warnings(record=True) as recs:
        warnings.simplefilter("always")
        scad_import(str(path), bbox=((0, 0, 0), (10, 10, 10)))

    relevant = [w for w in recs if issubclass(w.category, UserWarning)]
    assert len(relevant) >= 1
    assert "smaller than" in str(relevant[0].message)


def test_stl_hint_matching_or_larger_does_not_warn(tmp_path):
    import warnings
    from scadwright._stl import stl_bbox
    from scadwright.api.factories import _scad_import_hint_warned

    stl_bbox.cache_clear()
    _scad_import_hint_warned.clear()
    path = tmp_path / "small.stl"
    _make_stl(path, ((0, 0, 0), (5, 5, 5)))

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        # Hint exactly matches: no warning.
        scad_import(str(path), bbox=((0, 0, 0), (5, 5, 5)))
        # Hint larger on every axis: no warning.
        scad_import(str(path), bbox=((-1, -1, -1), (10, 10, 10)))


def test_stl_hint_check_skipped_for_missing_file(tmp_path):
    import warnings
    from scadwright._stl import stl_bbox
    from scadwright.api.factories import _scad_import_hint_warned

    stl_bbox.cache_clear()
    _scad_import_hint_warned.clear()
    # File doesn't exist → no auto-parse → no warning.
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        scad_import(str(tmp_path / "nope.stl"), bbox=((0, 0, 0), (1, 1, 1)))


def test_stl_hint_check_skipped_for_non_stl_extension(tmp_path):
    import warnings
    from scadwright.api.factories import _scad_import_hint_warned

    _scad_import_hint_warned.clear()
    # Non-STL extension: even an absurd hint doesn't trigger the STL check.
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        scad_import("p.svg", bbox=((0, 0, 0), (1, 1, 1)))
