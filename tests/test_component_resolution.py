from scadwright import Component, materialize, resolution
from scadwright.primitives import sphere
class _HighRes(Component):
    fn = 128

    def __init__(self):
        super().__init__()

    def build(self):
        return sphere(r=5)


class _NoFn(Component):
    def __init__(self):
        super().__init__()

    def build(self):
        return sphere(r=5)


def test_class_fn_flows_into_build():
    c = _HighRes()
    tree = materialize(c)
    assert tree.fn == 128


def test_instance_fn_overrides_class():
    c = _HighRes()
    c.fn = 16  # instance override
    # Must invalidate to force rebuild under new attr.
    c._invalidate()
    tree = materialize(c)
    assert tree.fn == 16


def test_explicit_kwarg_inside_build_wins():
    class _Explicit(Component):
        fn = 128

        def __init__(self):
            super().__init__()

        def build(self):
            return sphere(r=5, fn=8)

    tree = materialize(_Explicit())
    assert tree.fn == 8


def test_outer_context_inherits_when_component_has_no_fn():
    c = _NoFn()
    with resolution(fn=32):
        tree = materialize(c)
    assert tree.fn == 32


def test_component_fn_shadows_outer_context():
    with resolution(fn=32):
        tree = materialize(_HighRes())
    # Component fn=128 wins over outer 32.
    assert tree.fn == 128


def test_fa_fs_independent_from_fn():
    class _FaOnly(Component):
        fa = 5

        def __init__(self):
            super().__init__()

        def build(self):
            return sphere(r=5)

    tree = materialize(_FaOnly())
    assert tree.fa == 5
    assert tree.fn is None
    assert tree.fs is None


def test_component_with_no_resolution_attrs_builds_without_wrap():
    """If all of fn/fa/fs are None, no resolution context is entered."""
    c = _NoFn()
    tree = materialize(c)
    assert tree.fn is None
