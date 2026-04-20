import pytest

from scadwright import emit_str
from scadwright.boolops import minkowski, union
from scadwright.errors import EmitError
from scadwright.primitives import circle, cube, sphere
from scadwright.transforms import list_transforms, transform
from scadwright._custom_transforms.base import unregister


@pytest.fixture(autouse=True)
def clean_registry():
    before = set(list_transforms())
    yield
    for name in set(list_transforms()) - before:
        unregister(name)


def test_hoisted_module_emitted_once():
    @transform("_test_chamfer")
    def _t(node, *, r):
        return minkowski(node, sphere(r=r, fn=4))

    tree = union(
        cube(1)._test_chamfer(r=1),
        cube(2)._test_chamfer(r=1),
    )
    out = emit_str(tree)
    # One module def, two calls.
    assert out.count("module _test_chamfer_") == 1
    assert out.count("_test_chamfer_") >= 3  # 1 def + 2 calls


def test_distinct_kwargs_get_distinct_modules():
    @transform("_test_chamfer2")
    def _t(node, *, r):
        return minkowski(node, sphere(r=r, fn=4))

    tree = union(
        cube(1)._test_chamfer2(r=1),
        cube(2)._test_chamfer2(r=2),
    )
    out = emit_str(tree)
    assert out.count("module _test_chamfer2_") == 2


def test_inline_transform_no_module():
    @transform("_test_inline", inline=True)
    def _t(node, *, h):
        return node.linear_extrude(height=h)

    tree = circle(r=1, fn=8)._test_inline(h=2)
    out = emit_str(tree)
    assert "module" not in out
    assert "linear_extrude" in out


def test_module_uses_children_placeholder():
    @transform("_test_pass")
    def _t(node, *, dx):
        return node.translate([dx, 0, 0])

    tree = cube(1)._test_pass(dx=5)
    out = emit_str(tree)
    assert "children();" in out


def test_unregistered_transform_raises_emit_error():
    """If a Custom node references an unregistered name, emit raises EmitError."""
    from scadwright.ast.custom import Custom

    n = Custom(name="never_registered", kwargs=(), child=cube(1))
    with pytest.raises(EmitError, match="unregistered"):
        emit_str(n)
