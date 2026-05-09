"""Tests for custom-anchor propagation through Difference.

The first child's custom anchors survive a Difference unless a cutter's
bbox covers the anchor's position (in which case the cutter may have
removed material at it). Bbox-derived faces always propagate (the
difference's bbox is conservative).

Union and Intersection still drop all custom anchors — that behavior
is unchanged.
"""

import pytest

from scadwright import Component, Param, anchor
from scadwright.anchor import get_node_anchors
from scadwright.boolops import difference, intersection, union
from scadwright.primitives import cube, cylinder


# Test Component with a custom anchor on the +Z face.

class Bracket(Component):
    w = Param(float, default=20)
    thk = Param(float, default=3)
    depth = Param(float, default=15)

    mount_face = anchor(at="w/2, w/2, thk", normal=(0, 0, 1))
    side_anchor = anchor(at="w, w/2, thk/2", normal=(1, 0, 0))

    def build(self):
        return cube([self.w, self.w, self.depth])


# --- baseline: with no boolean, custom anchors are present ---


def test_baseline_bracket_has_mount_face():
    b = Bracket()
    anchors = get_node_anchors(b)
    assert "mount_face" in anchors
    assert "side_anchor" in anchors


# --- difference: first-child custom anchors survive when cutters miss them ---


def test_difference_with_interior_cutter_keeps_mount_face():
    """A small cutter that doesn't reach mount_face → mount_face survives."""
    b = Bracket()
    # Tiny cutter near the origin, far from mount_face at (10, 10, 3).
    drill = cylinder(h=2, r=0.5).translate([2, 2, 0])
    result = difference(b, drill)
    anchors = get_node_anchors(result)
    assert "mount_face" in anchors
    # Anchor's position is unchanged (Difference doesn't move geometry).
    assert anchors["mount_face"].position == pytest.approx((10.0, 10.0, 3.0))


def test_difference_with_cutter_at_mount_face_drops_it():
    """A cutter whose bbox covers mount_face → drop the anchor."""
    b = Bracket()
    # Cutter at mount_face's position; bbox covers (10, 10, 3).
    drill = cylinder(h=10, r=2).translate([10, 10, 0])
    result = difference(b, drill)
    anchors = get_node_anchors(result)
    assert "mount_face" not in anchors


def test_difference_with_cutter_at_one_anchor_keeps_others():
    """A cutter affects mount_face but not side_anchor → only mount_face dropped."""
    b = Bracket()
    drill = cylinder(h=10, r=2).translate([10, 10, 0])
    result = difference(b, drill)
    anchors = get_node_anchors(result)
    assert "mount_face" not in anchors
    assert "side_anchor" in anchors


# --- bbox-derived faces always propagate through Difference ---


def test_difference_preserves_bbox_faces():
    b = Bracket()
    drill = cylinder(h=2, r=0.5).translate([2, 2, 0])
    result = difference(b, drill)
    anchors = get_node_anchors(result)
    for name in ("top", "bottom", "front", "back", "lside", "rside"):
        assert name in anchors


def test_difference_bbox_faces_survive_even_with_overlapping_cutter():
    """A cutter that drills through the top face — the bbox-derived 'top'
    anchor still propagates (the bbox is preserved by the conservative
    difference bbox; whether the user gets the geometry they want at
    that point is up to them)."""
    b = Bracket()
    drill = cylinder(h=20, r=2).translate([10, 10, 0])
    result = difference(b, drill)
    anchors = get_node_anchors(result)
    assert "top" in anchors


# --- attach can use the propagated anchor ---


def test_attach_uses_propagated_mount_face():
    b = Bracket()
    drill = cylinder(h=2, r=0.5).translate([2, 2, 0])
    drilled_bracket = difference(b, drill)
    sensor = cube([4, 4, 1]).attach(drilled_bracket, on="mount_face")
    # sensor's bottom (at (2, 2, 0)) goes to mount_face (at (10, 10, 3)).
    from scadwright.ast.transforms import Translate
    assert isinstance(sensor, Translate)
    assert sensor.v == pytest.approx((8.0, 8.0, 3.0))


def test_attach_to_dropped_anchor_raises():
    b = Bracket()
    drill = cylinder(h=10, r=2).translate([10, 10, 0])
    drilled_bracket = difference(b, drill)
    with pytest.raises(Exception, match="mount_face"):
        cube([4, 4, 1]).attach(drilled_bracket, on="mount_face")


# --- WithAnchor through difference behaves the same way ---


def test_with_anchor_propagates_through_difference():
    base = (
        cube([20, 20, 5])
        .with_anchor("nub", at=(10, 10, 5), normal=(0, 0, 1))
    )
    # Cutter on the opposite side — anchor should survive.
    drill = cylinder(h=5, r=1).translate([2, 2, 0])
    result = difference(base, drill)
    anchors = get_node_anchors(result)
    assert "nub" in anchors


def test_with_anchor_dropped_when_cutter_covers_it():
    base = (
        cube([20, 20, 5])
        .with_anchor("nub", at=(10, 10, 5), normal=(0, 0, 1))
    )
    # Cutter directly under the anchor — drops it.
    drill = cylinder(h=5, r=1).translate([10, 10, 0])
    result = difference(base, drill)
    anchors = get_node_anchors(result)
    assert "nub" not in anchors


# --- Union and Intersection still drop all custom anchors ---


def test_union_still_drops_custom_anchors():
    b = Bracket()
    other = cube([10, 10, 10]).translate([30, 0, 0])
    u = union(b, other)
    anchors = get_node_anchors(u)
    assert "mount_face" not in anchors
    assert "side_anchor" not in anchors


def test_intersection_still_drops_custom_anchors():
    b = Bracket()
    other = cube([30, 30, 30])
    i = intersection(b, other)
    anchors = get_node_anchors(i)
    assert "mount_face" not in anchors


# --- propagation composes through transforms ---


def test_difference_then_translate_propagates_anchor():
    b = Bracket()
    drill = cylinder(h=2, r=0.5).translate([2, 2, 0])
    moved = difference(b, drill).translate([100, 0, 0])
    anchors = get_node_anchors(moved)
    assert "mount_face" in anchors
    # mount_face (10, 10, 3) shifted by (100, 0, 0) → (110, 10, 3).
    assert anchors["mount_face"].position == pytest.approx((110.0, 10.0, 3.0))


# --- multiple cutters, one affects, others don't ---


def test_multiple_cutters_only_one_drops_anchor():
    b = Bracket()
    drill_at_mount = cylinder(h=10, r=2).translate([10, 10, 0])
    drill_elsewhere = cylinder(h=10, r=1).translate([2, 2, 0])
    result = difference(b, drill_at_mount, drill_elsewhere)
    anchors = get_node_anchors(result)
    assert "mount_face" not in anchors
    assert "side_anchor" in anchors  # neither cutter is near side_anchor


def test_multiple_cutters_none_affect_anchors():
    b = Bracket()
    drill1 = cylinder(h=2, r=0.5).translate([2, 2, 0])
    drill2 = cylinder(h=2, r=0.5).translate([18, 2, 0])
    result = difference(b, drill1, drill2)
    anchors = get_node_anchors(result)
    assert "mount_face" in anchors
    assert "side_anchor" in anchors
