"""Generator-style build(): Components may yield Nodes instead of returning
a single Node; the framework auto-unions the yielded parts."""

import pytest

from scadwright import Component, materialize
from scadwright.ast.csg import Union
from scadwright.ast.primitives import Cube
from scadwright.errors import BuildError
from scadwright.primitives import cube


class _Multi(Component):
    def build(self):
        yield cube(1)
        yield cube(2).translate([5, 0, 0])
        yield cube(3).translate([10, 0, 0])


def test_generator_build_auto_unions():
    tree = materialize(_Multi())
    assert isinstance(tree, Union)
    assert len(tree.children) == 3


class _Single(Component):
    def build(self):
        yield cube(7)


def test_generator_build_single_item_unwraps():
    """A generator that yields exactly one Node should unwrap to that Node,
    not produce a redundant union(x) wrapper."""
    tree = materialize(_Single())
    assert isinstance(tree, Cube)
    assert tree.size == (7.0, 7.0, 7.0)


class _Empty(Component):
    def build(self):
        if False:
            yield cube(1)


def test_generator_build_empty_raises():
    with pytest.raises(BuildError, match="yielded no parts"):
        materialize(_Empty())


class _BadYield(Component):
    def build(self):
        yield cube(1)
        yield "not a node"


def test_generator_build_non_node_yield_raises():
    with pytest.raises(BuildError, match="yielded non-Node at index 1"):
        materialize(_BadYield())


class _BadReturn(Component):
    def build(self):
        return [cube(1), cube(2)]


def test_non_generator_non_node_return_raises():
    """Returning a plain list isn't the generator form — should fail clearly."""
    with pytest.raises(BuildError, match="must return a Node or yield Nodes"):
        materialize(_BadReturn())


class _NodeReturn(Component):
    """Traditional Node-returning build() must still work."""

    def build(self):
        return cube(4)


def test_node_return_still_works():
    tree = materialize(_NodeReturn())
    assert isinstance(tree, Cube)
    assert tree.size == (4.0, 4.0, 4.0)


class _Inner(Component):
    def build(self):
        yield cube(1)
        yield cube(2)


class _Outer(Component):
    def build(self):
        yield _Inner()
        yield cube(99)


def test_nested_generator_components_compose():
    tree = materialize(_Outer())
    assert isinstance(tree, Union)
    # Outer yields 2 children; inner's build is independent.
    assert len(tree.children) == 2
