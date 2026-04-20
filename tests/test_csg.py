from scadwright.boolops import difference, intersection, union
from scadwright.primitives import cube, cylinder, sphere
from scadwright.ast.csg import Difference, Intersection, Union


def test_union_variadic():
    u = union(cube(1), sphere(r=1), cylinder(h=1, r=1))
    assert isinstance(u, Union)
    assert len(u.children) == 3


def test_union_flattens_iterable():
    parts = [cube(1), sphere(r=1)]
    u = union(parts)
    assert len(u.children) == 2


def test_union_mixed_nodes_and_iterables():
    u = union(cube(1), [sphere(r=1), cylinder(h=1, r=1)])
    assert len(u.children) == 3


def test_difference_preserves_order():
    a, b, c = cube(1), sphere(r=1), cylinder(h=1, r=1)
    d = difference(a, b, c)
    assert isinstance(d, Difference)
    assert d.children == (a, b, c)


def test_intersection_returns_intersection():
    i = intersection(cube(1), sphere(r=1))
    assert isinstance(i, Intersection)
