from scadwright import Component, emit_str
from scadwright.boolops import union
from scadwright.primitives import cube, sphere
class _Box(Component):
    def __init__(self, size):
        super().__init__()
        self.size = size

    def build(self):
        return cube([self.size, self.size, self.size])


def test_emit_str_component_equals_emit_str_build():
    """With section labels off, a Component's emit should be identical to
    emitting its build() result directly."""
    b = _Box(size=4)
    assert emit_str(b, section_labels=False) == emit_str(b.build(), section_labels=False)


def test_debug_comment_points_at_instantiation_line():
    import inspect

    this_line = inspect.currentframe().f_lineno
    b = _Box(size=1)  # line this_line + 1
    out = emit_str(b, debug=True)
    assert f"test_component_emit.py:{this_line + 1}" in out


def test_chained_transform_on_component():
    b = _Box(size=2).translate([1, 2, 3])
    out = emit_str(b)
    assert "translate([1, 2, 3])" in out
    assert "cube([2, 2, 2]" in out


def test_component_in_union():
    out = emit_str(union(_Box(size=1), sphere(r=1)))
    assert "union()" in out
    assert "cube([1, 1, 1]" in out
    assert "sphere(r=1)" in out


def test_component_emits_same_output_each_time():
    """Caching must not corrupt output across multiple emits."""
    b = _Box(size=3)
    first = emit_str(b)
    second = emit_str(b)
    assert first == second
