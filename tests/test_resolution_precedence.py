"""Pin the resolution precedence rules documented in resolution.md.

For primitives:
  1. per-call `fn=` kwarg beats everything.
  2. else, the resolution() context active at construction fills in.

For Components (layering on top of the primitive rule):
  - Each Component captures the ambient `(fn, fa, fs)` context at
    construction and at every direct-parent wrap. The captured snapshot
    is replayed inside `build()` so primitives see the right values
    regardless of when build runs (eager or lazy).
  - Component's instance attr > class attr > snapshot establishes the
    inner-overrides-outer precedence around build(). Primitives inside
    see it unless they specify their own fn=.
"""

import tempfile
from pathlib import Path

import pytest

from scadwright import Component, Param, bbox, emit_str, resolution, render
from scadwright.primitives import cube, cylinder, sphere


def _fn_of(node):
    """Small helper: extract the fn attribute of a primitive."""
    return node.fn


# --- Primitive-level precedence ---


def test_per_call_wins_over_outer_context():
    with resolution(fn=32):
        c = cylinder(h=1, r=1, fn=64)
    assert _fn_of(c) == 64


def test_outer_context_fills_in():
    with resolution(fn=32):
        c = cylinder(h=1, r=1)
    assert _fn_of(c) == 32


def test_no_context_no_kwarg_is_unset():
    c = cylinder(h=1, r=1)
    assert _fn_of(c) is None


def test_nested_context_inner_wins():
    with resolution(fn=32):
        with resolution(fn=128):
            c = cylinder(h=1, r=1)
    assert _fn_of(c) == 128


def test_nested_context_inherits_unspecified():
    with resolution(fn=32, fa=5):
        with resolution(fn=128):
            c = cylinder(h=1, r=1)
    assert c.fn == 128
    assert c.fa == 5


# --- Component-level precedence ---


class _ClassDefault(Component):
    fn = 64

    def build(self):
        return sphere(r=1)


def test_component_class_attr_becomes_context_inside_build():
    w = _ClassDefault()
    built = w._get_built_tree()
    assert built.fn == 64


def test_component_instance_attr_overrides_class_attr():
    w = _ClassDefault()
    w.fn = 128
    built = w._get_built_tree()
    assert built.fn == 128


def test_component_class_attr_overrides_outer_context_at_build_time():
    w = _ClassDefault()
    with resolution(fn=8):
        built = w._get_built_tree()
    assert built.fn == 64


def test_per_call_kwarg_inside_build_overrides_component_attr():
    class _ExplicitInside(Component):
        fn = 64

        def build(self):
            # explicit fn on the call wins over our class attr
            return sphere(r=1, fn=200)

    w = _ExplicitInside()
    assert w._get_built_tree().fn == 200


def test_component_without_attrs_picks_up_build_time_context():
    class _NoAttrs(Component):
        def build(self):
            return sphere(r=1)

    w = _NoAttrs()
    with resolution(fn=32):
        built = w._get_built_tree()
    assert built.fn == 32


def test_component_without_attrs_no_context_is_unset():
    class _NoAttrs(Component):
        def build(self):
            return sphere(r=1)

    # Force rebuild to ensure no stale cache from other tests.
    w = _NoAttrs()
    built = w._get_built_tree()
    assert built.fn is None


# --- Construction-time context is captured and replayed at build ---


def test_component_construction_time_context_carries_to_lazy_build():
    """A Component captures the ambient `(fn, fa, fs)` context at
    construction. When `build()` runs lazily — even after the with-block
    has exited — `_get_built_tree()` opens a `resolution()` scope using
    the captured snapshot, so primitives inside `build()` see the
    construction-time values.

    This is Position Y: lazy build is invisible to the user. The
    context active when the Component entered the AST is what its
    geometry uses, regardless of when the build actually runs.
    """
    class _NoAttrs(Component):
        def build(self):
            return sphere(r=1)

    with resolution(fn=32):
        w = _NoAttrs()
    # Context exited here. Build happens now, but the snapshot from
    # construction-time replays inside `_get_built_tree()`.
    built = w._get_built_tree()
    assert built.fn == 32


# --- User-managed context patterns: the cases the original @variant
#     patch couldn't fix without snapshot-at-AST-insertion. ---


class _Plain(Component):
    """Component with no class-level fn; relies entirely on context."""

    def build(self):
        return sphere(r=1)


def _render_to_string(node) -> str:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "test.scad"
        render(node, out)
        return out.read_text()


def test_with_resolution_around_construction_then_render_outside():
    """Construct inside `with resolution()`, render outside. Snapshot
    captured at construction makes the file emit the right $fn."""
    with resolution(fn=64):
        c = _Plain()
    scad = _render_to_string(c)
    assert "$fn = 64" in scad or "$fn=64" in scad


def test_construct_outside_then_wrap_inside_then_render_outside():
    """Construct outside any context. Wrap (e.g. translate) inside a
    `with resolution()` block. The wrap's __post_init__ recaptures
    snapshot. Render outside the block: file still emits the right $fn."""
    c = _Plain()
    with resolution(fn=48):
        n = c.translate([0, 0, 0])
    scad = _render_to_string(n)
    assert "$fn = 48" in scad or "$fn=48" in scad


def test_with_resolution_around_render_only_uses_render_time_fallback():
    """Construct outside, never wrap, render inside `with resolution()`.
    The render-time fallback captures context onto the unsnapshotted
    Component; file emits the right $fn."""
    c = _Plain()  # snapshot=(None, None, None)
    with resolution(fn=24):
        scad = _render_to_string(c)
    assert "$fn = 24" in scad or "$fn=24" in scad


def test_class_attr_fn_overrides_snapshot():
    """A Component with `fn = 96` as a class attribute uses 96 even when
    the snapshot has a different value. Inner (class attr) overrides
    outer (snapshot) — same precedence as today's nested resolution()."""

    class _ClassFn(Component):
        fn = 96

        def build(self):
            return sphere(r=1)

    with resolution(fn=64):
        c = _ClassFn()
    built = c._get_built_tree()
    assert built.fn == 96


def test_instance_attr_fn_overrides_class_attr_and_snapshot():
    """Per-instance `fn=` kwarg wins over class attr and snapshot."""

    class _CustomFn(Component):
        fn = 96
        equations = "r > 0"

        def build(self):
            return sphere(r=self.r)

    with resolution(fn=64):
        c = _CustomFn(r=1, fn=200)
    built = c._get_built_tree()
    assert built.fn == 200


def test_nested_component_inherits_outer_components_snapshot():
    """An inner Component constructed inside an outer Component's build()
    sees the outer's snapshot context as the ambient `current_resolution()`,
    so the inner's snapshot is the outer's snapshot."""

    class Inner(Component):
        def build(self):
            return sphere(r=1)

    class Outer(Component):
        def build(self):
            return Inner().translate([0, 0, 0])

    with resolution(fn=72):
        o = Outer()
    # Outer.build() runs lazily here. Inside Outer.build(), the snapshot
    # context (fn=72) is active, so Inner() captures it. When Inner
    # builds (also lazily), its own snapshot fires fn=72.
    scad = emit_str(o)
    assert "$fn = 72" in scad or "$fn=72" in scad


def test_component_reuse_across_contexts_uses_latest_wrap():
    """A Component wrapped in two different contexts: the most recent
    wrap's context wins. Each wrap's __post_init__ overwrites the
    snapshot."""
    c = _Plain()
    with resolution(fn=32):
        first_wrap = c.translate([1, 0, 0])
    with resolution(fn=128):
        second_wrap = c.translate([2, 0, 0])
    # second_wrap was created last; c's snapshot now reflects fn=128.
    # both wraps share the same Component instance c, so both render fn=128.
    assert "$fn = 128" in _render_to_string(second_wrap) or "$fn=128" in _render_to_string(second_wrap)
