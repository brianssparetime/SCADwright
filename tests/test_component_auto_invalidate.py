"""Tests for auto-invalidation on Param reassignment (MajorReview Group 3f)."""

from scadwright import Component, bbox, tree_hash
from scadwright.primitives import cube
from scadwright.component.params import Param


class _Box(Component):
    size = Param(float, default=10.0)

    def build(self):
        return cube(self.size)


def test_reassign_param_rebuilds_tree():
    c = _Box(size=5)
    tree1 = c._get_built_tree()
    c.size = 20
    tree2 = c._get_built_tree()
    assert tree1 is not tree2
    # And the new tree reflects the new size.
    bb = bbox(c)
    assert bb.max == (20.0, 20.0, 20.0)


def test_reassign_param_invalidates_bbox_cache():
    c = _Box(size=5)
    bbox(c)  # populates cache
    assert c._bbox_cache is not None
    c.size = 20
    assert c._bbox_cache is None


def test_reassign_param_invalidates_tree_hash_cache():
    c = _Box(size=5)
    tree_hash(c)
    assert c._tree_hash_cache is not None
    c.size = 20
    assert c._tree_hash_cache is None


def test_tree_hash_reflects_new_param_value():
    c = _Box(size=5)
    h1 = tree_hash(c)
    c.size = 20
    h2 = tree_hash(c)
    assert h1 != h2
