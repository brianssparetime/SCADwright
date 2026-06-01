"""Design + @variant: multi-variant scripts via the Design base class."""

import tempfile
from pathlib import Path

import pytest

from scadwright import Component
from scadwright.boolops import difference
from scadwright.design import (
    Design, variant, resolve_variants, registered_designs, _reset_for_testing,
    _render_one,
)
from scadwright.errors import SCADwrightError, ValidationError
from scadwright.primitives import cube, cylinder


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


def test_design_name_attribute_overrides_class_name_in_output():
    from scadwright.design import _render_one

    class LensHousingDesign(Design):
        name = "v13f"

        @variant()
        def print(self):
            return cube(1)

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        from pathlib import Path
        out = _render_one(
            LensHousingDesign, "print",
            LensHousingDesign.__variants__["print"],
            base_dir=Path(td),
        )
        assert out.name == "v13f-print.scad"


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


# --- Variant ambient-context capture (regression for the resolution leak) ---


class _CtxLeakHousing(Component):
    """A Component whose build() uses a difference, so its tight_bbox
    is overridden (preventing accidental eager build via .bbox traversal).
    Used to test that the variant's resolution context reaches build()."""

    equations = "r, h > 0"

    def build(self):
        return difference(
            cylinder(h=self.h, r=self.r),
            cylinder(h=self.h + 2, r=self.r - 2).down(1),
        )

    def tight_bbox(self):
        from scadwright.bbox import BBox
        return BBox(min=(-self.r, -self.r, 0), max=(self.r, self.r, self.h))


def _scad_for_variant(design_cls, vname) -> str:
    """Render a variant to a temp file and return the SCAD as a string."""
    meta = design_cls.__variants__[vname]
    with tempfile.TemporaryDirectory() as td:
        out = _render_one(design_cls, vname, meta, base_dir=Path(td))
        return out.read_text()


def test_variant_fn_reaches_lazily_built_components():
    """@variant(fn=N) must apply to Components built lazily during emit.

    Without the fix, Housing.build() runs after the variant's resolution
    context has exited; primitives capture None and the file ships with
    no $fn directive. Reading .bbox inside the variant body works around
    the bug — this test deliberately avoids any such workaround.
    """

    class D(Design):
        h = _CtxLeakHousing(r=10, h=20)

        @variant(fn=48)
        def lazy(self):
            return self.h.translate([0, 0, 0])

    scad = _scad_for_variant(D, "lazy")
    assert "$fn = 48" in scad or "$fn=48" in scad, (
        f"variant fn=48 was lost — output had no $fn directive.\n"
        f"first 500 chars:\n{scad[:500]}"
    )


def test_variant_fn_does_not_leak_across_variants():
    """Two variants with different fn values, sharing a class-attribute
    Component. Each variant's output must reflect its own declared fn,
    independent of variant execution order."""

    class D(Design):
        h = _CtxLeakHousing(r=10, h=20)

        @variant(fn=48)
        def big(self):
            return self.h.translate([0, 0, 0])

        @variant(fn=24)
        def small(self):
            return self.h.translate([0, 0, 0])

    # Render in this order; the cache from `big` must not leak into `small`.
    big_scad = _scad_for_variant(D, "big")
    small_scad = _scad_for_variant(D, "small")

    assert "$fn = 48" in big_scad or "$fn=48" in big_scad
    assert "$fn = 24" in small_scad or "$fn=24" in small_scad
    assert "$fn = 48" not in small_scad and "$fn=48" not in small_scad, (
        "fn=48 leaked from `big` variant into `small` variant via the "
        "Component cache."
    )


def test_variant_viewpoint_reaches_emit():
    """@variant(rotation=...) is read by the emitter at emit time. The
    emit must happen inside the variant's viewpoint context."""

    class D(Design):
        @variant(rotation=(60, 0, 30), distance=200)
        def view(self):
            return cube(10)

    scad = _scad_for_variant(D, "view")
    assert "$vpr" in scad, (
        f"variant rotation was lost — output had no $vpr directive.\n"
        f"first 300 chars:\n{scad[:300]}"
    )


def test_variant_eager_build_runs_inside_context():
    """After method() returns, every Component in the tree should already
    be built (`_built_tree` populated). Confirms eager-build ran inside
    the variant's contexts."""

    class TrackedHousing(Component):
        equations = "r, h > 0"
        def build(self):
            return difference(
                cylinder(h=self.h, r=self.r),
                cylinder(h=self.h + 2, r=self.r - 2).down(1),
            )
        def tight_bbox(self):
            from scadwright.bbox import BBox
            return BBox(min=(-self.r, -self.r, 0), max=(self.r, self.r, self.h))

    captured = {}

    class D(Design):
        h = TrackedHousing(r=10, h=20)

        @variant(fn=48)
        def go(self):
            # Capture the Component's cache state when method() returns.
            captured["pre"] = self.h._built_tree
            return self.h.translate([0, 0, 0])

    _scad_for_variant(D, "go")
    # After eager-build runs (before render), the cache should be filled.
    # We can only sample via a reference outside the variant body — the
    # post-render state of the class-attribute Component.
    assert D.h._built_tree is not None, (
        "after render, Component should have been eagerly built and cached"
    )


def test_design_clearances_class_attr_does_not_reach_class_attr_components():
    """KNOWN GAP: ``Design.clearances = Clearances(...)`` doesn't reach
    Components instantiated as class-level attributes on the same Design.

    Clearances resolve at ``Component.__init__`` (in
    ``_init_factory._resolve_clearance_kwarg``), not lazily at build.
    Class-attribute Components are constructed at class-def time —
    before the variant's clearance context is active and before the
    framework can read ``Design.clearances`` — so they freeze with
    ``DEFAULT_CLEARANCES``.

    This is the same family of silent-drift bug Position Y addressed
    for resolution. The fix would require making clearance resolution
    lazy (deferring ``_resolve_clearance_kwarg`` until build time).
    That's a bigger change than the resolution fix because clearance
    feeds the equation solver — so it's tracked as a separate concern.

    This test is marked ``xfail(strict=True)``: if the fix lands and
    Components correctly inherit ``Design.clearances``, this test will
    pass and pytest will fail the run (signalling that the gap closed
    and this test should be flipped from xfail to a regular assertion).
    """
    from scadwright import Clearances
    from scadwright.shapes import AlignmentPin

    class D(Design):
        clearances = Clearances(sliding=0.05)
        pin = AlignmentPin(d=4, h=8, lead_in=1)  # constructed at class-def time

    # The pin's resolved clearance should match Design.clearances.sliding (0.05).
    # Today it's DEFAULT_CLEARANCES.sliding (0.1) because the pin was
    # constructed before any context was active.
    assert D.pin.clearance == pytest.approx(0.05), (
        f"expected pin to inherit Design.clearances.sliding=0.05, got "
        f"{D.pin.clearance}; class-attribute Components freeze their "
        f"clearance at class-def time"
    )

# Mark the above test as a known gap. When the lazy-clearance fix lands
# and the assertion holds, pytest with strict xfail will fail this test
# — flipping it from xfail to a regular passing test should be part of
# the fix commit.
test_design_clearances_class_attr_does_not_reach_class_attr_components = pytest.mark.xfail(
    strict=True,
    reason="known gap: clearances resolve at __init__, not build; "
           "class-attr Components miss Design.clearances",
)(test_design_clearances_class_attr_does_not_reach_class_attr_components)


def test_variant_build_errors_fail_fast_no_output_file():
    """A Component that raises during build() should fail fast — no
    output file written, error surfaces from _render_one with the
    Component named in the chain."""

    class Broken(Component):
        equations = "x > 0"
        def build(self):
            raise RuntimeError("intentional failure for test")

    class D(Design):
        b = Broken(x=1)

        @variant()
        def go(self):
            return self.b.translate([0, 0, 0])

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "D-go.scad"
        meta = D.__variants__["go"]
        # Without eager build, render() partially writes the file before
        # the build error surfaces. With eager build, the error surfaces
        # before render() runs and no file is created.
        with pytest.raises(SCADwrightError):
            _render_one(D, "go", meta, base_dir=Path(td))
        assert not out.exists(), (
            "eager build should fail before any output file is written; "
            f"found leftover file at {out}"
        )


# Primary-script-module scoping: when the user runs `python foo.py`,
# Designs defined in foo.py take precedence over Designs in
# transitively-imported modules. Without this, a helper Component class
# imported from a sibling Design module would drag that sibling's
# `default=True` variant into selection.


def test_resolve_variants_scopes_to_primary_module(monkeypatch):
    """Two Designs with default=True in different modules: the one in
    the primary script module wins, the imported one is excluded."""
    import sys
    import types

    class Primary(Design):
        @variant(default=True)
        def cap(self):
            return cube(1)

    class Imported(Design):
        @variant(default=True)
        def other(self):
            return cube(2)

    # Pretend Primary was defined in the user's script (__main__) and
    # Imported was pulled in from a sibling module.
    Primary.__module__ = "__main__"
    Imported.__module__ = "somelib"

    fake_main = types.ModuleType("__main__")
    fake_main.Primary = Primary
    monkeypatch.setitem(sys.modules, "__main__", fake_main)

    selected = resolve_variants(None, kind="build")
    assert len(selected) == 1
    assert selected[0][0] is Primary
    assert selected[0][1] == "cap"


def test_resolve_variants_falls_back_to_global_when_no_primary_module(monkeypatch):
    """If neither __main__ nor __scadwright_script__ contains Designs
    (e.g., REPL, pytest), selection falls back to the global registry."""
    import sys
    import types

    class A(Design):
        @variant(default=True)
        def go(self):
            return cube(1)

    # __main__ has no Design subclasses; primary detection returns None.
    fake_main = types.ModuleType("__main__")
    monkeypatch.setitem(sys.modules, "__main__", fake_main)
    monkeypatch.delitem(sys.modules, "__scadwright_script__", raising=False)

    selected = resolve_variants(None, kind="build")
    assert len(selected) == 1
    assert selected[0][0] is A


def test_resolve_variants_scopes_via_scadwright_script_module(monkeypatch):
    """The CLI loads scripts as `__scadwright_script__`. Scoping works
    on that name too — not just `__main__`."""
    import sys
    import types

    class Primary(Design):
        @variant(default=True)
        def cap(self):
            return cube(1)

    class Imported(Design):
        @variant(default=True)
        def other(self):
            return cube(2)

    Primary.__module__ = "__scadwright_script__"
    Imported.__module__ = "somelib"

    fake_script = types.ModuleType("__scadwright_script__")
    fake_script.Primary = Primary
    monkeypatch.setitem(sys.modules, "__scadwright_script__", fake_script)

    selected = resolve_variants(None, kind="build")
    assert len(selected) == 1
    assert selected[0][0] is Primary


def test_resolve_variants_explicit_variant_still_searches_primary_only(monkeypatch):
    """An explicit variant name finds it within the primary module's
    scope. A variant that exists only in a transitively-imported
    module is not reachable by name."""
    import sys
    import types

    class Primary(Design):
        @variant()
        def cap(self):
            return cube(1)

    class Imported(Design):
        @variant()
        def secret(self):
            return cube(2)

    Primary.__module__ = "__main__"
    Imported.__module__ = "somelib"

    fake_main = types.ModuleType("__main__")
    fake_main.Primary = Primary
    monkeypatch.setitem(sys.modules, "__main__", fake_main)

    # The Imported.secret variant is not reachable by name.
    with pytest.raises(SCADwrightError, match="no variant named 'secret'"):
        resolve_variants("secret", kind="build")

    # Primary.cap is reachable.
    selected = resolve_variants("cap", kind="build")
    assert len(selected) == 1
    assert selected[0][0] is Primary
