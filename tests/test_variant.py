from scadwright import Component, current_variant, emit_str, variant
from scadwright.primitives import cube, sphere


def test_default_variant_is_none():
    assert not current_variant()
    assert current_variant().name is None


def test_variant_context_sets_and_restores():
    with variant("print"):
        assert current_variant() == "print"
    assert not current_variant()


def test_nested_variants():
    with variant("display"):
        assert current_variant() == "display"
        with variant("print"):
            assert current_variant() == "print"
        assert current_variant() == "display"
    assert not current_variant()


def test_component_can_branch_on_variant():
    class _Swap(Component):
        def __init__(self):
            super().__init__()

        def build(self):
            if current_variant() == "print":
                return cube(1)
            return sphere(r=1)

    c = _Swap()
    tree_display = emit_str(c)
    assert "sphere" in tree_display

    c2 = _Swap()  # fresh instance to avoid cache
    with variant("print"):
        tree_print = emit_str(c2)
    assert "cube" in tree_print
