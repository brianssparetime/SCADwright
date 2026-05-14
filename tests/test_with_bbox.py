"""Tests for ``with_bbox_from`` — user-assertion bbox override.

The wrapper is transparent to emit and anchors, and intercepts the two
bbox visitors to report ``source``'s extents instead of the child's.
Motivating case: late-applied differences against a cached host where
the user knows the diff doesn't move the bbox."""

from __future__ import annotations

import pytest

from scadwright import BBox, Node, bbox, tight_bbox, with_bbox_from
from scadwright.anchor import Anchor, get_node_anchors
from scadwright.ast.transforms import WithBBox
from scadwright.boolops import difference
from scadwright.composition_helpers import pack_on_bed
from scadwright.emit import emit_str
from scadwright.primitives import cube


# --- Core override semantics ---


def test_overrides_bbox_to_source_node():
    """Bbox of `difference(big, small).with_bbox_from(big)` is big's bbox,
    not the (smaller-or-equal) default first-child result. The default
    happens to coincide here because difference's conservative bbox IS
    first-child, but the assertion is the load-bearing piece for
    tight_bbox below — keep both tests symmetric."""
    big = cube([40, 40, 10])
    small = cube([2, 2, 1])
    asserted = difference(big, small).with_bbox_from(big)
    assert bbox(asserted) == bbox(big)


def test_overrides_tight_bbox_where_difference_would_raise():
    """Without the assertion, tight_bbox on a Difference raises. With it,
    the result equals tight_bbox(source). This is the load-bearing case."""
    big = cube([40, 40, 10])
    small = cube([2, 2, 1])
    plain = difference(big, small)
    with pytest.raises(NotImplementedError):
        tight_bbox(plain)
    asserted = plain.with_bbox_from(big)
    assert tight_bbox(asserted) == tight_bbox(big)


def test_accepts_bbox_literal():
    """`source` can be a BBox value, used directly."""
    big = cube([10, 10, 10])
    declared = BBox(min=(0.0, 0.0, 0.0), max=(10.0, 10.0, 10.0))
    result = difference(big, cube([1, 1, 1])).with_bbox_from(declared)
    assert tight_bbox(result) == declared
    assert bbox(result) == declared


# --- Spatial composition ---


def test_spatial_transform_composes_node_source():
    """A transform above the wrapper moves both the child and the asserted
    bbox the same way; the source bbox is queried within the visitor's
    accumulated ctx."""
    big = cube([10, 10, 10])
    wrapped = difference(big, cube([1, 1, 1])).with_bbox_from(big)
    moved = wrapped.translate([5, 0, 0])
    expected = bbox(big.translate([5, 0, 0]))
    assert bbox(moved) == expected


def test_spatial_transform_composes_bbox_literal():
    """A BBox-literal source also transforms by ctx, mirroring how
    primitive bboxes compose with enclosing transforms."""
    declared = BBox(min=(0.0, 0.0, 0.0), max=(10.0, 10.0, 10.0))
    wrapped = cube([10, 10, 10]).with_bbox_from(declared)
    moved = wrapped.translate([3, 0, 0])
    expected = BBox(min=(3.0, 0.0, 0.0), max=(13.0, 10.0, 10.0))
    assert bbox(moved) == expected


# --- Transparency: emit + anchors ---


def test_emit_is_transparent():
    """Wrapping in `with_bbox_from` adds no SCAD output."""
    big = cube([10, 10, 10])
    inner = difference(big, cube([1, 1, 1]))
    plain = emit_str(inner)
    wrapped = emit_str(inner.with_bbox_from(big))
    assert plain == wrapped


def test_anchors_pass_through():
    """The wrapper is transparent for anchor lookup — wrapping doesn't
    add or hide anchors."""
    plate = cube([40, 40, 2])
    inner_anchors = get_node_anchors(plate)
    wrapped_anchors = get_node_anchors(plate.with_bbox_from(plate))
    # Comparing Anchor objects directly: they're frozen dataclasses with
    # value semantics, so two anchors at the same place compare equal.
    assert set(inner_anchors.keys()) == set(wrapped_anchors.keys())
    for name in inner_anchors:
        assert inner_anchors[name] == wrapped_anchors[name]


# --- fuse_extend re-wrap ---


def test_fuse_extend_rewraps():
    """fuse_extend on a wrapped supportable primitive recurses into the
    child and re-wraps the result, preserving the bbox assertion."""
    source = cube([10, 10, 10])
    wrapped = cube([10, 10, 10]).with_bbox_from(source)
    # Anchor on the top face, outward +Z.
    a = Anchor(position=(5.0, 5.0, 10.0), normal=(0.0, 0.0, 1.0), kind="planar")
    extended = wrapped.fuse_extend(a, eps=0.01)
    assert extended is not None
    assert isinstance(extended, WithBBox)
    assert extended.source is source


# --- Standalone form ---


def test_standalone_form_matches_method():
    big = cube([10, 10, 10])
    via_method = big.with_bbox_from(big)
    via_function = with_bbox_from(big, big)
    assert bbox(via_method) == bbox(via_function)


# --- Motivating pattern: force_render + late-diff + pack_on_bed ---


def test_force_render_late_diff_emits_correctly():
    body = cube([40, 40, 10])
    cutter = cube([2, 2, 1])
    cached = body.force_render()
    result = difference(cached, cutter).with_bbox_from(body)
    scad = emit_str(result)
    assert "render()" in scad
    assert "difference()" in scad


def test_pack_on_bed_with_engraved_body():
    """End-to-end: a body whose tight_bbox would otherwise be unknowable
    (difference + force_render) lays out via pack_on_bed once we declare
    its bbox via with_bbox_from."""
    body_a = cube([20, 20, 5])
    body_b = cube([15, 15, 5])
    cutter = cube([1, 1, 1])
    engraved_a = difference(body_a.force_render(), cutter).with_bbox_from(body_a)
    engraved_b = difference(body_b.force_render(), cutter).with_bbox_from(body_b)
    layout = pack_on_bed(engraved_a, engraved_b, gap=5.0, assert_fit=False)
    scad = emit_str(layout)
    # Both engraved bodies present in the layout; no exception during pack.
    assert "render()" in scad
    assert "difference()" in scad


# --- Top-level public API ---


def test_node_publicly_importable():
    """Regression guard for the public `Node` export (Change 3)."""
    from scadwright import Node as PubNode
    from scadwright.ast.base import Node as InternalNode
    assert PubNode is InternalNode
