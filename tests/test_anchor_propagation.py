"""Tests for anchor propagation through transforms and CSG."""

import pytest

from scadwright import Component, Param, anchor, bbox
from scadwright.anchor import get_node_anchors
from scadwright.boolops import union
from scadwright.primitives import cube


class Post(Component):
    h = Param(float, default=10)
    w = Param(float, default=5)

    tip = anchor(at="w/2, w/2, h", normal=(0, 0, 1))

    def build(self):
        return cube([self.w, self.w, self.h])


# --- propagation through translate ---


def test_anchors_propagate_through_translate():
    post = Post()
    moved = post.translate([20, 0, 0])
    anchors = get_node_anchors(moved)
    assert "tip" in anchors
    # Original tip at (2.5, 2.5, 10), shifted +20 in x.
    assert anchors["tip"].position == pytest.approx((22.5, 2.5, 10.0))
    assert anchors["tip"].normal == pytest.approx((0.0, 0.0, 1.0))


def test_standard_anchors_propagate_through_translate():
    post = Post()
    moved = post.translate([10, 10, 10])
    anchors = get_node_anchors(moved)
    # "top" from bbox: original top at (2.5, 2.5, 10), shifted by (10,10,10).
    assert anchors["top"].position == pytest.approx((12.5, 12.5, 20.0))


# --- propagation through rotate ---


def test_anchors_propagate_through_rotate():
    post = Post()
    rotated = post.rotate([0, 0, 90])
    anchors = get_node_anchors(rotated)
    assert "tip" in anchors
    # After 90-degree rotation around z: (2.5, 2.5, 10) -> (-2.5, 2.5, 10).
    assert anchors["tip"].position[2] == pytest.approx(10.0)
    # Normal (0,0,1) should be unchanged by z-rotation.
    assert anchors["tip"].normal == pytest.approx((0.0, 0.0, 1.0))


# --- propagation through scale ---


def test_anchors_propagate_through_scale():
    post = Post()
    scaled = post.scale([2, 1, 1])
    anchors = get_node_anchors(scaled)
    assert "tip" in anchors
    # Original tip at (2.5, 2.5, 10), scale x by 2 -> (5.0, 2.5, 10).
    assert anchors["tip"].position == pytest.approx((5.0, 2.5, 10.0))


# --- propagation through mirror ---


def test_anchors_propagate_through_mirror():
    post = Post()
    mirrored = post.mirror([1, 0, 0])
    anchors = get_node_anchors(mirrored)
    assert "tip" in anchors
    # Mirror across x=0: (2.5, 2.5, 10) -> (-2.5, 2.5, 10).
    assert anchors["tip"].position == pytest.approx((-2.5, 2.5, 10.0))


def test_mirror_inverts_normal():
    post = Post()
    # Anchor "rside" has normal (1,0,0). Mirror across x should invert it.
    mirrored = post.mirror([1, 0, 0])
    anchors = get_node_anchors(mirrored)
    assert anchors["rside"].normal[0] == pytest.approx(-1.0)


# --- chained transforms ---


def test_anchors_propagate_through_chained_transforms():
    post = Post()
    moved = post.translate([10, 0, 0]).rotate([0, 0, 90])
    anchors = get_node_anchors(moved)
    assert "tip" in anchors


# --- CSG drops custom anchors ---


def test_csg_drops_custom_anchors():
    post = Post()
    combined = union(post, cube(1))
    anchors = get_node_anchors(combined)
    # Custom anchor "tip" should be dropped by union.
    assert "tip" not in anchors
    # Standard bbox-derived anchors still present.
    assert "top" in anchors


# --- attach uses propagated anchors ---


def test_attach_uses_propagated_custom_anchor():
    post = Post()
    moved_post = post.translate([20, 0, 0])
    peg = cube([3, 3, 4]).attach(moved_post, face="tip")
    bb = bbox(peg)
    # tip of moved post is at (22.5, 2.5, 10). Peg's bottom should be there.
    assert bb.min[2] == pytest.approx(10.0)
    assert bb.center[0] == pytest.approx(22.5)
    assert bb.center[1] == pytest.approx(2.5)


# --- non-spatial wrappers pass through ---


def test_color_passes_through_anchors():
    post = Post()
    colored = post.red()
    anchors = get_node_anchors(colored)
    assert "tip" in anchors
