from scadwright import Component, Param, tree_hash
from scadwright.boolops import difference
from scadwright.primitives import cube, sphere
from scadwright.transforms import transform
def test_same_tree_same_hash():
    h1 = tree_hash(cube([10, 20, 30]))
    h2 = tree_hash(cube([10, 20, 30]))
    assert h1 == h2


def test_different_geometry_different_hash():
    h1 = tree_hash(cube([10, 20, 30]))
    h2 = tree_hash(cube([10, 20, 31]))
    assert h1 != h2


def test_source_location_excluded():
    """Same tree built on different lines must hash equal."""
    a = cube(10)  # line A
    b = cube(10)  # line B
    assert tree_hash(a) == tree_hash(b)


def test_chained_transform_hashes_stable():
    h1 = tree_hash(cube(1).translate([5, 0, 0]).red())
    h2 = tree_hash(cube(1).translate([5, 0, 0]).red())
    assert h1 == h2


def test_hash_is_16_chars_hex():
    h = tree_hash(cube(1))
    assert len(h) == 16
    int(h, 16)  # parses as hex


def test_component_hash_includes_params():
    class _Box(Component):
        size = Param(float, default=10)
        def build(self):
            return cube(self.size)

    h1 = tree_hash(_Box(size=10))
    h2 = tree_hash(_Box(size=20))
    assert h1 != h2


def test_component_same_params_same_hash():
    class _Box(Component):
        size = Param(float, default=10)
        def build(self):
            return cube(self.size)

    h1 = tree_hash(_Box(size=10))
    h2 = tree_hash(_Box(size=10))
    assert h1 == h2


def test_csg_order_matters():
    """Difference is order-sensitive; hash should reflect that."""
    a = difference(cube(10), sphere(r=3))
    b = difference(sphere(r=3), cube(10))
    assert tree_hash(a) != tree_hash(b)


def test_custom_transform_kwargs_in_hash():
    from scadwright._custom_transforms.base import unregister

    @transform("_test_th_offset")
    def _t(node, *, dx):
        return node.translate([dx, 0, 0])

    try:
        h1 = tree_hash(cube(1)._test_th_offset(dx=1))
        h2 = tree_hash(cube(1)._test_th_offset(dx=2))
        assert h1 != h2
    finally:
        unregister("_test_th_offset")
