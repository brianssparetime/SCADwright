"""Tests for tree_hash caching on Components (MajorReview Group 6c)."""

from unittest.mock import patch

from scadwright import Component, tree_hash
from scadwright.primitives import cube
class _Box(Component):
    def __init__(self, size):
        super().__init__()
        self.size = size

    def build(self):
        return cube(self.size)


def test_component_tree_hash_is_stable():
    c = _Box(10)
    h1 = tree_hash(c)
    h2 = tree_hash(c)
    assert h1 == h2


def test_component_caches_after_first_call():
    c = _Box(10)
    assert c._tree_hash_cache is None
    h = tree_hash(c)
    assert c._tree_hash_cache == h


def test_component_second_call_uses_cache():
    # The cache short-circuits _canonicalize, which is the slow part.
    c = _Box(10)
    tree_hash(c)  # populates cache

    # Patch _canonicalize to fail if called again.
    with patch("scadwright.hashing._canonicalize", side_effect=AssertionError("cache missed")):
        h = tree_hash(c)
    assert h == c._tree_hash_cache


def test_invalidate_clears_tree_hash_cache():
    c = _Box(10)
    tree_hash(c)
    assert c._tree_hash_cache is not None
    c._invalidate()
    assert c._tree_hash_cache is None


def test_structurally_equal_components_hash_equal():
    # Cache is per-instance, but two instances with the same structure
    # must still produce the same hash (no accidental short-circuit).
    a = _Box(10)
    b = _Box(10)
    assert tree_hash(a) == tree_hash(b)


def test_different_params_hash_different():
    a = _Box(10)
    b = _Box(20)
    assert tree_hash(a) != tree_hash(b)


def test_bare_node_hash_uncached_but_correct():
    n = cube(10)
    h1 = tree_hash(n)
    h2 = tree_hash(n)
    assert h1 == h2
    # Bare nodes don't grow a cache attribute.
    assert not hasattr(n, "_tree_hash_cache")
