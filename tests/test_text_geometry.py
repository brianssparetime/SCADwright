"""Tests for the text_geometry transform — placed glyph geometry without
combining with the host. Shares all kwargs and validation with add_text;
the test set below exercises the geometry-only path's distinct surface."""

from __future__ import annotations

import pytest

from scadwright.anchor import get_node_anchors
from scadwright.ast.csg import Difference, Union
from scadwright.ast.custom import Custom
from scadwright.boolops import difference, union
from scadwright.emit import emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder
from scadwright.shapes import Tube


def _expand(custom: Custom):
    """Helper: expand an inline Custom to its body for structural inspection."""
    from scadwright._custom_transforms.base import get_transform
    t = get_transform(custom.name)
    return t.expand(custom.child, **custom.kwargs_dict())


# --- Smoke ---


def test_smoke_emits():
    plate = cube([40, 40, 2])
    glyphs = plate.text_geometry(
        label="HELLO", on="top", relief=-0.3, font_size=6,
    )
    scad = emit_str(glyphs)
    assert "text" in scad
    assert '"HELLO"' in scad


def test_returns_custom_node():
    plate = cube([40, 40, 2])
    glyphs = plate.text_geometry(
        label="HI", on="top", relief=-0.3, font_size=4,
    )
    assert isinstance(glyphs, Custom)
    assert glyphs.name == "text_geometry"


# --- Equivalence with add_text composition ---
#
# Planar single-line produces ONE glyph subtree, so text_geometry returns
# it directly and `difference(host, text_geometry(...))` is byte-identical
# to `host.add_text(...)`. Multi-line on planar collapses to a single
# 2D union → still one extruded subtree → byte-identical. Curved surfaces
# (cylindrical / rim arc) emit ONE node per glyph, so text_geometry wraps
# them in a union: the composed result is geometrically equivalent but
# wraps an inner union, not byte-equal. We test structurally instead.


def test_planar_inset_byte_matches_add_text_difference():
    plate = cube([40, 40, 2])
    via_add = plate.add_text(
        label="HI", on="top", relief=-0.3, font_size=4,
    )
    via_geom = difference(
        plate,
        plate.text_geometry(
            label="HI", on="top", relief=-0.3, font_size=4,
        ),
    )
    assert emit_str(via_add) == emit_str(via_geom)


def test_planar_raised_byte_matches_add_text_union():
    plate = cube([40, 40, 2])
    via_add = plate.add_text(
        label="HI", on="top", relief=0.5, font_size=4,
    )
    via_geom = union(
        plate,
        plate.text_geometry(
            label="HI", on="top", relief=0.5, font_size=4,
        ),
    )
    assert emit_str(via_add) == emit_str(via_geom)


def test_planar_multiline_byte_matches_add_text():
    plate = cube([40, 40, 2])
    via_add = plate.add_text(
        label="LINE 1\nLINE 2", on="top", relief=-0.3, font_size=4,
    )
    via_geom = difference(
        plate,
        plate.text_geometry(
            label="LINE 1\nLINE 2", on="top", relief=-0.3, font_size=4,
        ),
    )
    assert emit_str(via_add) == emit_str(via_geom)


def test_cylindrical_geometry_round_trips():
    """Curved surfaces emit one node per glyph; text_geometry unions them.
    Verify the composed result emits valid SCAD that mentions the label
    and uses an outer difference."""
    cyl = cylinder(h=20, r=10)
    result = difference(
        cyl,
        cyl.text_geometry(
            label="ABC", on="outer_wall", relief=-0.4, font_size=3,
        ),
    )
    scad = emit_str(result)
    assert "difference()" in scad
    assert '"A"' in scad and '"B"' in scad and '"C"' in scad


def test_rim_arc_geometry_round_trips():
    tube = Tube(h=10, od=30, id=20)
    result = difference(
        tube,
        tube.text_geometry(
            label="RIM", on="top", relief=-0.3, font_size=3,
        ),
    )
    scad = emit_str(result)
    assert "difference()" in scad
    assert '"R"' in scad and '"I"' in scad and '"M"' in scad


# --- Anchor semantics (decoration=False on text_geometry) ---


def test_result_bbox_is_glyph_mesh_not_host():
    """text_geometry is decoration=False, so the result's bbox is the
    glyph mesh's bbox (small) — NOT the host's bbox. Contrast with
    add_text, which is decoration=True and reports the host's bbox
    through its decoration wrapper."""
    from scadwright.bbox import bbox as _bbox
    plate = cube([40, 40, 2])
    glyphs = plate.text_geometry(
        label="X", on="top", relief=-0.3, font_size=4,
    )
    plate_bb = _bbox(plate)
    glyphs_bb = _bbox(glyphs)
    # The glyph mesh extends roughly font_size in x/y; the plate is 40x40.
    # A direct size comparison is enough to prove the glyph bbox is not
    # the host bbox.
    plate_xy = max(plate_bb.size[0], plate_bb.size[1])
    glyphs_xy = max(glyphs_bb.size[0], glyphs_bb.size[1])
    assert glyphs_xy < plate_xy


def test_add_text_still_preserves_host_anchors():
    """Regression guard: the refactor must not have stripped decoration=True
    from add_text. The decorated result must expose the host's bbox-derived
    face anchors so further `.attach()` calls keep working."""
    plate = cube([40, 40, 2])
    decorated = plate.add_text(
        label="X", on="top", relief=-0.3, font_size=4,
    )
    names = set(get_node_anchors(decorated).keys())
    assert "top" in names
    assert "bottom" in names


# --- Validation parity with add_text ---
#
# Validation runs at expand time (the transform's body is called when the
# Custom is expanded for emit), so each negative test triggers via emit_str.


def test_relief_zero_rejected():
    with pytest.raises(ValidationError, match="relief=0"):
        emit_str(cube([10, 10, 10]).text_geometry(
            label="X", on="top", relief=0, font_size=4,
        ))


def test_invalid_label_type_rejected():
    with pytest.raises(ValidationError, match="must be a string"):
        emit_str(cube([10, 10, 10]).text_geometry(
            label=42, on="top", relief=-0.3, font_size=4,
        ))


def test_invalid_font_size_rejected():
    with pytest.raises(ValidationError, match="positive number"):
        emit_str(cube([10, 10, 10]).text_geometry(
            label="X", on="top", relief=-0.3, font_size=-1,
        ))


# --- Motivating use: late-diff outside force_render ---


def test_late_diff_pattern_emits_force_render():
    """The motivating pattern: cache the smooth body, apply text as an
    outside difference. Verifies emit works end-to-end; the perf payoff
    is in OpenSCAD's preview, not in SCAD source."""
    body = cube([40, 40, 10])
    cached = body.force_render()
    cutter = body.text_geometry(
        label="VERSION 1", on="top", relief=-0.4, font_size=5,
    )
    result = difference(cached, cutter)
    scad = emit_str(result)
    assert "render()" in scad
    assert '"VERSION 1"' in scad
    assert "difference()" in scad


# --- Structural expansion ---


def test_planar_single_glyph_expands_to_translate():
    """Planar with one extruded subtree: text_geometry returns it directly,
    no union wrapper."""
    plate = cube([40, 40, 2])
    glyphs = plate.text_geometry(
        label="X", on="top", relief=-0.3, font_size=4,
    )
    expanded = _expand(glyphs)
    # _place_planar returns a Translate around the rotated, extruded text.
    assert not isinstance(expanded, Union)
    assert not isinstance(expanded, Difference)


def test_curved_multi_glyph_expands_to_union():
    """Curved walls emit one node per glyph; text_geometry wraps the list
    in a union so a single Node can be returned."""
    cyl = cylinder(h=20, r=10)
    glyphs = cyl.text_geometry(
        label="ABC", on="outer_wall", relief=-0.4, font_size=3,
    )
    expanded = _expand(glyphs)
    assert isinstance(expanded, Union)
    # Three glyphs → at least three Union children (more if per-glyph
    # decomposition produces extras).
    assert len(expanded.children) >= 3
