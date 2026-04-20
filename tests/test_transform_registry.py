import pytest

from scadwright.errors import SCADwrightError
from scadwright.primitives import cube
from scadwright.transforms import Transform, get_transform, list_transforms, transform
from scadwright.ast.custom import Custom
from scadwright._custom_transforms.base import unregister


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure tests don't pollute the global registry."""
    before = set(list_transforms())
    yield
    after = set(list_transforms())
    for name in after - before:
        unregister(name)


def test_decorator_registers():
    @transform("_test_passthrough")
    def _t(node):
        return node

    assert "_test_passthrough" in list_transforms()
    assert get_transform("_test_passthrough") is not None


def test_dispatch_via_node_attribute():
    @transform("_test_offset")
    def _offset(node, *, dx):
        return node.translate([dx, 0, 0])

    c = cube(1)
    result = c._test_offset(dx=5)
    assert isinstance(result, Custom)
    assert result.name == "_test_offset"
    assert dict(result.kwargs) == {"dx": 5}
    assert result.child is c


def test_kwargs_sorted_for_stable_identity():
    @transform("_test_two_kwargs")
    def _t(node, *, a, b):
        return node

    n1 = cube(1)._test_two_kwargs(a=1, b=2)
    n2 = cube(1)._test_two_kwargs(b=2, a=1)
    # kwargs should be tuple-of-pairs in sorted order, identical for both.
    assert n1.kwargs == n2.kwargs == (("a", 1), ("b", 2))


def test_duplicate_registration_raises():
    @transform("_test_dup")
    def _a(node):
        return node

    with pytest.raises(SCADwrightError, match="already registered"):
        @transform("_test_dup")
        def _b(node):
            return node


def test_bad_signature_no_positional():
    with pytest.raises(SCADwrightError, match="positional"):
        @transform("_test_bad_no_pos")
        def _t():
            return None


def test_bad_signature_varargs():
    with pytest.raises(SCADwrightError, match=r"\*args"):
        @transform("_test_bad_varargs")
        def _t(node, *args):
            return node


def test_subclass_form_works():
    class _PassThru(Transform):
        name = "_test_passthru_class"

        def expand(self, child, **kwargs):
            return child

    from scadwright._custom_transforms.base import register
    register("_test_passthru_class", _PassThru())
    assert get_transform("_test_passthru_class") is not None


def test_unknown_attribute_still_raises_attribute_error():
    """__getattr__ must not swallow lookups that aren't transforms."""
    c = cube(1)
    with pytest.raises(AttributeError):
        c._not_a_real_attr


def test_dispatch_captures_source_location():
    @transform("_test_loc")
    def _t(node, *, x):
        return node

    import inspect
    line = inspect.currentframe().f_lineno
    n = cube(1)._test_loc(x=1)  # line + 1
    assert n.source_location is not None
    assert n.source_location.line == line + 1
