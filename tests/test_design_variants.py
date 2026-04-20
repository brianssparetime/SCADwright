"""Design + @variant: multi-variant scripts via the Design base class."""

import pytest

from scadwright import Component
from scadwright.design import (
    Design, variant, resolve_variants, registered_designs, _reset_for_testing,
)
from scadwright.errors import SCADwrightError, ValidationError
from scadwright.primitives import cube


@pytest.fixture(autouse=True)
def reset_registry():
    _reset_for_testing()
    yield
    _reset_for_testing()


def test_single_variant_registers():
    class D(Design):
        @variant()
        def only(self):
            return cube(1)

    assert registered_designs() == [D]
    assert list(D.__variants__) == ["only"]


def test_single_variant_runs_without_name():
    class D(Design):
        @variant()
        def only(self):
            return cube(1)

    selected = resolve_variants(None, kind="build")
    assert len(selected) == 1
    assert selected[0][1] == "only"


def test_cli_nonexistent_variant_errors_even_with_one_variant():
    class D(Design):
        @variant()
        def only(self):
            return cube(1)

    with pytest.raises(SCADwrightError, match="no variant named 'bogus'"):
        resolve_variants("bogus", kind="build")


def test_multiple_variants_no_default_build_runs_all():
    class D(Design):
        @variant()
        def a(self):
            return cube(1)

        @variant()
        def b(self):
            return cube(2)

    selected = resolve_variants(None, kind="build")
    assert sorted(v[1] for v in selected) == ["a", "b"]


def test_multiple_variants_no_default_preview_errors():
    class D(Design):
        @variant()
        def a(self):
            return cube(1)

        @variant()
        def b(self):
            return cube(2)

    with pytest.raises(SCADwrightError, match="pass --variant"):
        resolve_variants(None, kind="preview")


def test_multiple_variants_one_default_runs_default():
    class D(Design):
        @variant()
        def a(self):
            return cube(1)

        @variant(default=True)
        def b(self):
            return cube(2)

    for kind in ("build", "preview", "render"):
        selected = resolve_variants(None, kind=kind)
        assert len(selected) == 1
        assert selected[0][1] == "b"


def test_multiple_defaults_in_one_design_errors_at_class_creation():
    with pytest.raises(ValidationError, match="multiple variants marked"):
        class D(Design):
            @variant(default=True)
            def a(self):
                return cube(1)

            @variant(default=True)
            def b(self):
                return cube(2)


def test_cli_variant_name_picks_correctly():
    class D(Design):
        @variant()
        def a(self):
            return cube(1)

        @variant()
        def b(self):
            return cube(2)

    selected = resolve_variants("b", kind="preview")
    assert selected[0][1] == "b"


def test_variant_metadata_roundtrips():
    class D(Design):
        @variant(fn=48, out="custom.scad", default=True)
        def v(self):
            return cube(1)

    meta = D.__variants__["v"]
    assert meta.fn == 48
    assert meta.out == "custom.scad"
    assert meta.default is True


def test_default_output_path_uses_design_and_variant_names():
    from scadwright.design import _render_one

    class D(Design):
        @variant()
        def scene(self):
            return cube(1)

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        from pathlib import Path
        out = _render_one(D, "scene", D.__variants__["scene"], base_dir=Path(td))
        assert out.name == "D-scene.scad"


def test_variant_out_override_respected():
    from scadwright.design import _render_one

    class D(Design):
        @variant(out="sub/custom.scad")
        def scene(self):
            return cube(1)

    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        # Need to create the subdir first
        (Path(td) / "sub").mkdir()
        out = _render_one(D, "scene", D.__variants__["scene"], base_dir=Path(td))
        assert out.name == "custom.scad"
        assert out.parent.name == "sub"


def test_two_designs_both_visible_in_registry():
    class D1(Design):
        @variant()
        def a(self):
            return cube(1)

    class D2(Design):
        @variant()
        def a(self):
            return cube(2)

    assert len(registered_designs()) == 2


def test_ambiguous_variant_name_across_designs_errors_on_lookup():
    class D1(Design):
        @variant()
        def same(self):
            return cube(1)

    class D2(Design):
        @variant()
        def same(self):
            return cube(2)

    with pytest.raises(SCADwrightError, match="ambiguous"):
        resolve_variants("same", kind="build")


def test_shared_parts_are_single_instance_across_variants():
    calls = {"n": 0}

    class Tracked(Component):
        def build(self):
            calls["n"] += 1
            return cube(1)

    class D(Design):
        part = Tracked()

        @variant()
        def a(self):
            return self.part

        @variant()
        def b(self):
            return self.part.translate([5, 0, 0])

    # Class-body instantiation runs once. Methods reference self.part, which
    # points back to the same class-level instance.
    d = D()
    assert d.part is D.part
