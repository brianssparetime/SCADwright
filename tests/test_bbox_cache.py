from scadwright import Component, Param, bbox
from scadwright.primitives import cube
class _Counter(Component):
    """Component that counts how many times build() was called."""

    _calls = 0

    def __init__(self):
        super().__init__()
        type(self)._calls = 0

    def build(self):
        type(self)._calls += 1
        return cube([10, 10, 10])


def test_bbox_caches_per_component_instance():
    c = _Counter()
    assert _Counter._calls == 0
    bbox(c)
    assert _Counter._calls == 1
    bbox(c)
    # Second call hits the cache, no rebuild.
    assert _Counter._calls == 1


def test_invalidate_clears_bbox_cache():
    c = _Counter()
    bbox(c)
    n1 = _Counter._calls
    c._invalidate()
    bbox(c)
    assert _Counter._calls == n1 + 1


def test_param_component_has_bbox_cache():
    """Auto-generated __init__ should set _bbox_cache via super().__init__."""

    class _P(Component):
        size = Param(float, default=10)

        def build(self):
            return cube(self.size)

    p = _P()
    assert p._bbox_cache is None
    bbox(p)
    assert p._bbox_cache is not None


# --- node.bbox property (matches free function) ---


def test_bbox_property_on_primitive_matches_free_function():
    c = cube([10, 20, 30])
    assert c.bbox == bbox(c)
    assert c.bbox.size == (10.0, 20.0, 30.0)


def test_bbox_property_on_transformed_node_matches_free_function():
    c = cube([10, 10, 10]).up(5).right(2)
    assert c.bbox == bbox(c)


def test_bbox_property_on_component_uses_cache():
    c = _Counter()
    _ = c.bbox
    assert _Counter._calls == 1
    _ = c.bbox
    assert _Counter._calls == 1   # second access hits the cache


def test_bbox_property_on_component_matches_free_function():
    class _P(Component):
        size = Param(float, default=10)

        def build(self):
            return cube(self.size)

    p = _P(size=7)
    assert p.bbox == bbox(p)
    assert p.bbox.size == (7.0, 7.0, 7.0)


def test_bbox_property_invalidates_with_param_change():
    """Setting a Param invalidates the cache; .bbox reflects the new value."""
    class _P(Component):
        size = Param(float, default=10)

        def build(self):
            return cube(self.size)

    p = _P(size=5)
    assert p.bbox.size == (5.0, 5.0, 5.0)
    # Pre-freeze direct __set__ via the descriptor invalidates the cache.
    type(p).size.__set__(p, 8)
    assert p.bbox.size == (8.0, 8.0, 8.0)
