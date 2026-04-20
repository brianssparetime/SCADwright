"""Pin the resolution precedence rules documented in resolution.md.

For primitives:
  1. per-call `fn=` kwarg beats everything.
  2. else, the resolution() context active at construction fills in.

For Components (layering on top of the primitive rule):
  - Component's instance attr > class attr establishes an implicit
    resolution() scope around build(). Primitives inside see it unless
    they specify their own fn=.
  - Component builds are lazy: the context that matters is the one active
    at build time, modified by the Component's own wrap.
"""

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


# --- Lazy-build timing caveat documented as a test ---


def test_component_construction_time_context_does_not_carry_to_build():
    """Construction happens inside `with resolution(...)`, but build is lazy.
    If the with-block exits before build, the context is gone."""
    class _NoAttrs(Component):
        def build(self):
            return sphere(r=1)

    with resolution(fn=32):
        w = _NoAttrs()
    # Context exited here. Build happens now:
    built = w._get_built_tree()
    assert built.fn is None
