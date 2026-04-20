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
