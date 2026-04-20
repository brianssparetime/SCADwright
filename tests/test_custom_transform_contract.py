"""Tests for the custom-transform CHILDREN placeholder contract (Group 8a/8b)."""

import pytest

from scadwright import emit_str
from scadwright.ast.custom import CHILDREN, Custom
from scadwright.ast.transforms import Translate
from scadwright.primitives import cube, sphere
from scadwright.transforms import transform
from scadwright._custom_transforms.base import unregister


# --- 8a: CHILDREN attribute-access guard ---


def test_missing_attribute_raises_clear_message():
    # Directly exercise the placeholder — same result the emitter sees when
    # a non-inline transform's expand() tries to read a child attribute.
    with pytest.raises(AttributeError, match="inline=True"):
        CHILDREN.size


def test_error_names_the_attribute_that_was_accessed():
    with pytest.raises(AttributeError, match=r"\.r\b"):
        CHILDREN.r


def test_dunder_access_raises_plain_attribute_error():
    # Dunders should NOT carry our special message — Python/tools rely on
    # the default behavior (reprs, isinstance checks, pickling, etc.).
    with pytest.raises(AttributeError) as exc:
        CHILDREN.__some_dunder_that_doesnt_exist__
    assert "inline=True" not in str(exc.value)


def test_hasattr_returns_false_cleanly():
    # hasattr swallows AttributeError; our override must raise it (not some
    # other exception) so this works.
    assert hasattr(CHILDREN, "size") is False
    assert hasattr(CHILDREN, "nonexistent") is False


def test_transform_dispatch_still_works_on_placeholder():
    try:
        @transform("_probe_for_children")
        def _probe(node, *, x):
            return node

        # Calling a registered transform on CHILDREN should succeed and
        # produce a Custom node.
        result = CHILDREN._probe_for_children(x=42)
        assert isinstance(result, Custom)
        assert result.name == "_probe_for_children"
        assert result.child is CHILDREN
    finally:
        unregister("_probe_for_children")


def test_builtin_methods_still_work_on_placeholder():
    # translate is a method defined directly on Node (resolves via MRO, not
    # __getattr__), so CHILDREN.translate(...) must still work — a non-inline
    # expand() often composes built-in transforms around the placeholder.
    result = CHILDREN.translate([0, 0, 1])
    assert isinstance(result, Translate)
    assert result.child is CHILDREN


def test_inline_transform_can_read_child_attributes():
    try:
        @transform("_inline_reads", inline=True)
        def _inline_reads(node, *, scale_by):
            # Works because inline=True: `node` is the real child, not CHILDREN.
            new_size = node.size[0] * scale_by
            return cube(new_size)

        result = cube(10)._inline_reads(scale_by=2)
        out = emit_str(result)
        assert "cube([20" in out
    finally:
        unregister("_inline_reads")


def test_non_inline_transform_reading_child_crashes_at_emit_with_clear_message():
    try:
        @transform("_bad_inspector")
        def _bad_inspector(node, *, depth):
            # This will be called with CHILDREN during emit; reading .size
            # is the mistake we're catching.
            _ = node.size
            return node

        part = cube(10)._bad_inspector(depth=1)
        with pytest.raises(AttributeError, match="inline=True"):
            emit_str(part)
    finally:
        unregister("_bad_inspector")


# --- 8b: doc-example parity ---
# Re-run the example from docs/custom_transforms.md to catch prose drift.


def test_docs_first_example_runs():
    from scadwright.boolops import minkowski

    try:
        @transform("chamfer_top_docs_example")
        def chamfer_top_docs_example(node, *, depth):
            return minkowski(node, sphere(r=depth, fn=8))

        part = cube([10, 10, 5]).chamfer_top_docs_example(depth=1)
        out = emit_str(part)
        assert "minkowski" in out
    finally:
        unregister("chamfer_top_docs_example")
