"""Tests for Node.with_anchor() — adding custom anchors to primitives."""

import pytest

from scadwright.anchor import get_node_anchors
from scadwright.boolops import union
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder


# --- basic ---


def test_with_anchor_publishes_named_anchor():
    c = cube([10, 10, 10]).with_anchor(
        "tip", at=(5, 5, 10), normal=(0, 0, 1)
    )
    anchors = get_node_anchors(c)
    assert "tip" in anchors
    assert anchors["tip"].position == pytest.approx((5.0, 5.0, 10.0))
    assert anchors["tip"].normal == pytest.approx((0.0, 0.0, 1.0))


def test_with_anchor_preserves_bbox_anchors():
    c = cube([10, 10, 10]).with_anchor("tip", at=(5, 5, 10), normal=(0, 0, 1))
    anchors = get_node_anchors(c)
    # All six bbox-derived faces still present alongside the custom anchor.
    for name in ("top", "bottom", "front", "back", "lside", "rside"):
        assert name in anchors


def test_with_anchor_overrides_bbox_default():
    # Custom anchor with the standard name "top" overrides the bbox-derived
    # one — same rule that applies to Component custom anchors.
    c = cube([10, 10, 10]).with_anchor("top", at=(0, 0, 0), normal=(0, 0, 1))
    anchors = get_node_anchors(c)
    assert anchors["top"].position == pytest.approx((0.0, 0.0, 0.0))


# --- propagation through transforms ---


def test_with_anchor_propagates_through_translate():
    c = cube([10, 10, 10]).with_anchor("tip", at=(5, 5, 10), normal=(0, 0, 1))
    moved = c.translate([10, 20, 0])
    anchors = get_node_anchors(moved)
    assert anchors["tip"].position == pytest.approx((15.0, 25.0, 10.0))
    assert anchors["tip"].normal == pytest.approx((0.0, 0.0, 1.0))


def test_with_anchor_propagates_through_rotate():
    c = cube([10, 10, 10]).with_anchor("tip", at=(5, 5, 10), normal=(0, 0, 1))
    rotated = c.rotate([0, 0, 90])
    anchors = get_node_anchors(rotated)
    # 90° around z: (5, 5, 10) -> (-5, 5, 10); normal (0,0,1) unchanged.
    assert anchors["tip"].position == pytest.approx((-5.0, 5.0, 10.0))
    assert anchors["tip"].normal == pytest.approx((0.0, 0.0, 1.0))


def test_with_anchor_chains_with_other_transforms():
    c = (
        cube([10, 10, 10])
        .with_anchor("tip", at=(5, 5, 10), normal=(0, 0, 1))
        .translate([1, 2, 3])
        .rotate([0, 0, 90])
    )
    anchors = get_node_anchors(c)
    # (5+1, 5+2, 10+3) = (6, 7, 13); rotate 90° around z: (-7, 6, 13).
    assert anchors["tip"].position == pytest.approx((-7.0, 6.0, 13.0))


# --- on a non-Component primitive ---


def test_with_anchor_on_cylinder():
    c = cylinder(h=20, r=5).with_anchor(
        "axis_top", at=(0, 0, 20), normal=(0, 0, 1)
    )
    anchors = get_node_anchors(c)
    assert anchors["axis_top"].position == pytest.approx((0.0, 0.0, 20.0))


# --- attach uses the custom anchor ---


def test_attach_uses_with_anchor():
    plate = cube([40, 40, 2])
    peg = cube([5, 5, 10]).with_anchor(
        "base", at=(2.5, 2.5, 0), normal=(0, 0, -1)
    )
    placed = peg.attach(plate, on="top", at="base")
    # The translate puts peg's "base" at plate's "top" (= (20, 20, 2)).
    # Peg's "base" was at (2.5, 2.5, 0); shift = (17.5, 17.5, 2).
    from scadwright.ast.transforms import Translate
    assert isinstance(placed, Translate)
    assert placed.v == pytest.approx((17.5, 17.5, 2.0))


# --- emit transparency ---


def test_with_anchor_emits_no_extra_scad():
    from scadwright.emit.scad import emit_str
    plain = emit_str(cube([10, 10, 10]), pretty=False, banner=False)
    wrapped = emit_str(
        cube([10, 10, 10]).with_anchor("x", at=(0, 0, 0), normal=(0, 0, 1)),
        pretty=False,
        banner=False,
    )
    # The metadata wrapper should not change emitted SCAD.
    assert plain == wrapped


# --- bbox transparency ---


def test_with_anchor_does_not_change_bbox():
    from scadwright.bbox import bbox
    plain_bb = bbox(cube([10, 10, 10]))
    wrapped_bb = bbox(
        cube([10, 10, 10]).with_anchor("x", at=(0, 0, 0), normal=(0, 0, 1))
    )
    assert plain_bb.min == plain_bb.min
    assert plain_bb.max == wrapped_bb.max
    assert plain_bb.min == wrapped_bb.min


# --- booleans drop the anchor (consistent with Component custom anchors) ---


def test_with_anchor_dropped_by_union():
    a = cube([10, 10, 10]).with_anchor("x", at=(0, 0, 0), normal=(0, 0, 1))
    b = cube([5, 5, 5]).translate([20, 0, 0])
    u = union(a, b)
    anchors = get_node_anchors(u)
    assert "x" not in anchors


# --- fuse_extend recurses into the wrapped primitive ---


def test_with_anchor_fuse_extend_reaches_cube():
    # cube().with_anchor(...).attach(plate, fuse=True) should hit the
    # parametric Cube.fuse_extend path, not fall back to cross-section.
    plate = cube([40, 40, 2])
    peg = cube([5, 5, 10]).with_anchor(
        "base", at=(2.5, 2.5, 0), normal=(0, 0, -1)
    )
    placed = peg.attach(plate, on="top", at="base", fuse=True)
    # The result should be a Translate wrapping a WithAnchor wrapping a
    # Translate wrapping the bumped Cube — i.e., the parametric path was
    # taken (no Union with a slab).
    from scadwright.ast.csg import Union
    # Walk down looking for any Union (which would indicate cross-section
    # fallback). For the parametric path there's no Union introduced.
    def has_union(node, depth=10):
        if depth == 0:
            return False
        if isinstance(node, Union):
            return True
        for attr in ("child", "children"):
            v = getattr(node, attr, None)
            if v is None:
                continue
            if isinstance(v, tuple):
                if any(has_union(c, depth - 1) for c in v):
                    return True
            else:
                if has_union(v, depth - 1):
                    return True
        return False

    assert not has_union(placed), (
        "fuse_extend should have taken the parametric path through "
        "WithAnchor; got a Union, suggesting cross-section fallback."
    )


# --- arg validation ---


def test_with_anchor_rejects_bad_at():
    c = cube([10, 10, 10])
    with pytest.raises((TypeError, ValueError, ValidationError)):
        c.with_anchor("x", at="not a tuple", normal=(0, 0, 1))


def test_with_anchor_rejects_bad_normal():
    c = cube([10, 10, 10])
    with pytest.raises((TypeError, ValueError, ValidationError)):
        c.with_anchor("x", at=(0, 0, 0), normal="not a tuple")


# --- surface_params propagate ---


def test_with_anchor_carries_surface_params():
    c = cube([10, 10, 10]).with_anchor(
        "rim",
        at=(0, 0, 10),
        normal=(0, 0, 1),
        kind="planar",
        surface_params={"rim_radius": 5.0},
    )
    anchors = get_node_anchors(c)
    assert anchors["rim"].kind == "planar"
    assert anchors["rim"].surface_param("rim_radius") == 5.0
