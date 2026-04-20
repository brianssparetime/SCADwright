"""Components must work with the same chained methods that regular Nodes
have. Individual attribute-roundtrip tests for each transform are
covered by test_transforms.py; this file only tests what's Component-
specific: source-location capture on chained calls and 2D→3D extrude
promotion."""

from scadwright import Component, emit_str
from scadwright.ast.transforms import Translate
from scadwright.primitives import circle, cube


class _Unit(Component):
    def __init__(self):
        super().__init__()

    def build(self):
        return cube(1)


def test_chained_transform_on_component_wraps_it_as_child():
    c = _Unit()
    t = c.translate([1, 2, 3])
    assert isinstance(t, Translate)
    assert t.child is c


def test_chain_source_location_points_at_chain_site():
    """A chained call on a Component must capture the user's call-site,
    not scadwright internals."""
    import inspect

    this_line = inspect.currentframe().f_lineno
    t = _Unit().translate([0, 0, 1])  # line this_line + 1
    assert t.source_location.file.endswith("test_component_chaining.py")
    assert t.source_location.line == this_line + 1


def test_linear_extrude_on_2d_component():
    """A Component whose build() returns a 2D shape must accept
    linear_extrude."""
    class _Disc(Component):
        def __init__(self):
            super().__init__()

        def build(self):
            return circle(r=5, fn=32)

    ex = _Disc().linear_extrude(height=10)
    out = emit_str(ex)
    assert "linear_extrude(height=10" in out
    assert "circle(r=5" in out
