"""Tests for Anchor surface-kind metadata and decoration-transform anchor preservation."""

import pytest

from scadwright import Component, anchor
from scadwright.anchor import (
    Anchor,
    _normalize_surface_params,
    anchors_from_bbox,
    get_node_anchors,
    transform_anchors,
)
from scadwright.ast.base import Node
from scadwright.bbox import BBox
from scadwright.boolops import union
from scadwright.matrix import Matrix
from scadwright.primitives import cube
from scadwright.transforms import transform


# --- Anchor extension ---


def test_anchor_default_kind_is_planar():
    a = Anchor(position=(0, 0, 0), normal=(0, 0, 1))
    assert a.kind == "planar"
    assert a.surface_params == ()


def test_anchor_with_explicit_kind():
    a = Anchor(
        position=(0, 0, 0),
        normal=(1, 0, 0),
        kind="cylindrical",
        surface_params=(("axis", (0, 0, 1)), ("radius", 5.0)),
    )
    assert a.kind == "cylindrical"
    assert a.surface_param("radius") == 5.0
    assert a.surface_param("axis") == (0, 0, 1)
    assert a.surface_param("missing", default=42) == 42


def test_anchor_surface_param_default_is_none():
    a = Anchor(position=(0, 0, 0), normal=(0, 0, 1))
    assert a.surface_param("anything") is None


def test_normalize_surface_params_dict():
    out = _normalize_surface_params({"radius": 3, "axis": (0, 0, 1)})
    assert out == (("axis", (0, 0, 1)), ("radius", 3))


def test_normalize_surface_params_none_and_empty():
    assert _normalize_surface_params(None) == ()
    assert _normalize_surface_params(()) == ()


def test_anchor_is_hashable_with_surface_params():
    a = Anchor(
        position=(0, 0, 0),
        normal=(1, 0, 0),
        kind="cylindrical",
        surface_params=(("axis", (0, 0, 1)), ("radius", 5.0)),
    )
    # Round-trip through a set requires hashability; the sorted tuple-of-pairs
    # form preserves it.
    assert {a, a} == {a}


# --- anchors_from_bbox tags planar ---


def test_anchors_from_bbox_all_planar():
    bb = BBox(min=(0, 0, 0), max=(10, 10, 10))
    anchors = anchors_from_bbox(bb)
    for name, a in anchors.items():
        assert a.kind == "planar", f"{name} should be planar"
        assert a.surface_params == (), f"{name} surface_params should be empty"


# --- transform_anchors preserves kind / params ---


def test_transform_anchors_preserves_kind_and_params():
    cyl_params = (("axis", (0, 0, 1)), ("radius", 5.0))
    a = Anchor(
        position=(5, 0, 0),
        normal=(1, 0, 0),
        kind="cylindrical",
        surface_params=cyl_params,
    )
    # Pure translate: kind/params survive unchanged. Position/normal transform.
    m = Matrix.translate(10, 0, 0)
    out = transform_anchors({"wall": a}, m)
    assert out["wall"].kind == "cylindrical"
    assert out["wall"].surface_params == cyl_params
    assert out["wall"].position == pytest.approx((15, 0, 0))


# --- anchor() factory accepts kind / surface_params ---


class CylinderShape(Component):
    """Minimal Component with a cylindrical anchor for testing."""

    equations = ["h, r > 0"]

    outer_wall = anchor(
        at="0, 0, h/2",
        normal=(1, 0, 0),
        kind="cylindrical",
        surface_params={"axis": (0, 0, 1), "radius": "r"},
        # Note: surface_params values are stored verbatim (no expression eval
        # for now — that lands when curved kinds are used). For PR 1 we just
        # check the metadata flows through unchanged.
    )

    def build(self):
        from scadwright.primitives import cylinder
        return cylinder(h=self.h, r=self.r)


def test_anchor_factory_propagates_kind():
    c = CylinderShape(h=10, r=5)
    anchors = c.get_anchors()
    assert "outer_wall" in anchors
    assert anchors["outer_wall"].kind == "cylindrical"
    # surface_params is the sorted tuple-of-pairs form.
    sp = dict(anchors["outer_wall"].surface_params)
    assert sp["axis"] == (0, 0, 1)
    # radius was passed as the string "r" — for PR 1 we don't evaluate this.
    # The presence of the key is what we verify.
    assert "radius" in sp


# --- Decoration flag round-trip on @transform ---


@transform("_test_decorate", inline=True, decoration=True)
def _decorate_with_marker(node):
    """Test transform: returns an AST that drops the host's anchors but
    is registered as a decoration so anchor lookup falls back to the host.
    """
    # Wrap in a union with another small cube — would normally drop custom anchors.
    return union(node, cube([1, 1, 1]).translate([100, 0, 0]))


@transform("_test_replace", inline=True)
def _replace_with_other(node):
    """Test transform: same body but NOT marked as a decoration. Used to
    confirm the default behavior drops custom anchors.
    """
    return union(node, cube([1, 1, 1]).translate([100, 0, 0]))


class WithCustomAnchor(Component):
    equations = ["w > 0"]
    mount = anchor(at="0, 0, w", normal=(0, 0, 1))

    def build(self):
        return cube([self.w, self.w, self.w])


def test_decoration_transform_preserves_host_anchors():
    host = WithCustomAnchor(w=10)
    decorated = host._test_decorate()
    anchors = get_node_anchors(decorated)
    assert "mount" in anchors, (
        "decoration=True transform should preserve the host's custom anchors"
    )
    # The mount anchor's position should still reflect the host, not the union bbox.
    assert anchors["mount"].position == pytest.approx((0, 0, 10))


def test_non_decoration_transform_drops_host_anchors():
    host = WithCustomAnchor(w=10)
    replaced = host._test_replace()
    anchors = get_node_anchors(replaced)
    assert "mount" not in anchors, (
        "regular custom transforms drop custom anchors, matching CSG behavior"
    )


def test_decoration_transform_chains():
    """Two decoration transforms on the same host: the second must see the
    first's result as still carrying the host's anchors.
    """
    host = WithCustomAnchor(w=10)
    once = host._test_decorate()
    twice = once._test_decorate()
    anchors = get_node_anchors(twice)
    assert "mount" in anchors
