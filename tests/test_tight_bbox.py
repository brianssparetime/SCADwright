import pytest

from scadwright import Component, tight_bbox
from scadwright.boolops import union
from scadwright.primitives import cube, sphere
def test_tight_bbox_cube():
    bb = tight_bbox(cube([10, 20, 30]))
    assert bb.min == (0, 0, 0)
    assert bb.max == (10, 20, 30)


def test_tight_bbox_sphere():
    bb = tight_bbox(sphere(r=5))
    assert bb.min == (-5, -5, -5)
    assert bb.max == (5, 5, 5)


def test_tight_bbox_rejects_translate():
    with pytest.raises(NotImplementedError, match="primitives"):
        tight_bbox(cube(1).translate([5, 0, 0]))


def test_tight_bbox_rejects_csg():
    with pytest.raises(NotImplementedError):
        tight_bbox(union(cube(1), sphere(r=1)))


def test_tight_bbox_rejects_component():
    class _W(Component):
        def __init__(self):
            super().__init__()
        def build(self):
            return cube(1)

    with pytest.raises(NotImplementedError):
        tight_bbox(_W())
