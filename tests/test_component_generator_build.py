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


# --- Specific hints for common new-author mistakes ---


class _MissingReturn(Component):
    def build(self):
        cube([1, 1, 1])  # no `return` statement; Python returns None


def test_build_returns_none_hints_return_or_yield():
    with pytest.raises(BuildError) as exc_info:
        materialize(_MissingReturn())
    msg = str(exc_info.value)
    assert "got None" in msg
    assert "did you forget a `return`" in msg
    assert "yield" in msg


def test_build_returns_list_of_nodes_hints_yield_or_union():
    """The classic new-author mistake — returning a list of parts gets a
    pinpoint hint at both `yield` (preferred) and `union(...)` (alternative)."""
    with pytest.raises(BuildError) as exc_info:
        materialize(_BadReturn())
    msg = str(exc_info.value)
    assert "got list of 2 Nodes" in msg
    assert "yield" in msg
    assert "union" in msg


class _TupleReturn(Component):
    def build(self):
        return (cube(1), cube(2))


def test_build_returns_tuple_of_nodes_hints_yield_or_union():
    with pytest.raises(BuildError) as exc_info:
        materialize(_TupleReturn())
    msg = str(exc_info.value)
    assert "got tuple of 2 Nodes" in msg
    assert "yield" in msg


class _EmptyList(Component):
    def build(self):
        return []


def test_build_returns_empty_list_specific_message():
    with pytest.raises(BuildError) as exc_info:
        materialize(_EmptyList())
    msg = str(exc_info.value)
    assert "got empty list" in msg
    assert "at least one" in msg


class _MixedList(Component):
    def build(self):
        return [cube(1), 5, "x"]


def test_build_returns_list_with_non_node_items():
    with pytest.raises(BuildError) as exc_info:
        materialize(_MixedList())
    msg = str(exc_info.value)
    assert "non-Node items" in msg
    # Both bad types should be named.
    assert "int" in msg
    assert "str" in msg
    # No yield/union hint for mixed lists — the description already names
    # the problem; an unfocused hint adds noise.
    assert "Hint:" not in msg


class _UnknownReturnType(Component):
    def build(self):
        return 42


def test_build_returns_unknown_type_keeps_generic_message():
    """Niche return shapes (int, str, dict, function, ...) get the
    generic `got <type>` message without a focused hint — the type name
    is signal enough."""
    with pytest.raises(BuildError) as exc_info:
        materialize(_UnknownReturnType())
    msg = str(exc_info.value)
    assert "got int" in msg
    assert "Hint:" not in msg


class _SingletonList(Component):
    def build(self):
        return [cube(1)]


def test_build_returns_singleton_list_still_hints():
    """A 1-element list isn't auto-unwrapped (lists aren't a build()
    return form). The hint applies the same as for multi-element lists."""
    with pytest.raises(BuildError) as exc_info:
        materialize(_SingletonList())
    msg = str(exc_info.value)
    assert "got list of 1 Nodes" in msg
    assert "yield" in msg


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
