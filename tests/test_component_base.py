import pytest

from scadwright import Component, materialize
from scadwright.errors import BuildError
from scadwright.primitives import cube
from scadwright.ast.primitives import Cube


class _Box(Component):
    def __init__(self, width):
        super().__init__()
        self.width = width

    def build(self):
        return cube([self.width, self.width, self.width])


def test_component_is_node():
    """Component must be a Node for emitter dispatch / CSG composition."""
    from scadwright.ast.base import Node

    assert isinstance(_Box(width=1), Node)


def test_materialize_caches_and_invalidate_rebuilds():
    b = _Box(width=5)
    first = materialize(b)
    assert materialize(b) is first                         # cached
    b._invalidate()
    second = materialize(b)
    assert second is not first                             # rebuilt
    assert second.size == first.size                       # same value


def test_missing_build_raises_with_classname():
    class _NoBuild(Component):
        def __init__(self):
            super().__init__()

    # Phase 3: NotImplementedError from build() is now wrapped in BuildError.
    with pytest.raises(BuildError) as exc_info:
        materialize(_NoBuild())
    assert "_NoBuild" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, NotImplementedError)


def test_component_source_location_points_at_instantiation():
    """The Component must capture the caller's file:line, not scadwright
    internals."""
    import inspect

    this_line = inspect.currentframe().f_lineno
    b = _Box(width=1)  # on line this_line + 1
    assert b.source_location.file.endswith("test_component_base.py")
    assert b.source_location.line == this_line + 1


def test_concrete_nodes_still_frozen():
    """Unfreezing Component must NOT cascade to concrete AST nodes."""
    import dataclasses

    c = cube(5)
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        c.size = (1, 1, 1)


def test_build_not_called_before_materialize():
    """Phase 0 Q10 / Phase 2 Q3: build is lazy."""
    counter = {"n": 0}

    class _Counter(Component):
        def __init__(self):
            super().__init__()

        def build(self):
            counter["n"] += 1
            return cube(1)

    c = _Counter()
    assert counter["n"] == 0
    materialize(c)
    assert counter["n"] == 1
    materialize(c)
    assert counter["n"] == 1  # cached, no rebuild
