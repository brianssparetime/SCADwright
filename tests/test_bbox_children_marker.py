"""``bbox()`` of the ``@transform`` CHILDREN placeholder must raise.

Returning a degenerate bbox here was a silent footgun: any framework
method called inside a non-inline transform's ``expand()`` body that
introspects bbox would receive a fictional value and emit broken
SCAD without warning. The canonical example is ``halve()`` sizing
its cutter from ``bbox(self)`` — with the placeholder yielding
zero-volume, halve's floor produced a 1mm cutter and silently sliced
99% of the actual geometry.

These tests pin the new behavior: any code path that reaches the
placeholder via bbox surfaces a clear ``ValidationError`` naming the
remedy (``inline=True`` or restructure).
"""

from __future__ import annotations

import pytest

from scadwright import bbox, emit_str
from scadwright._custom_transforms.base import unregister
from scadwright.ast.custom import CHILDREN
from scadwright.errors import ValidationError
from scadwright.primitives import cube
from scadwright.transforms import transform


def test_direct_bbox_on_children_raises():
    with pytest.raises(ValidationError, match="CHILDREN placeholder"):
        bbox(CHILDREN)


def test_bbox_error_names_workarounds():
    """The error message points at both available remedies — ``inline=True``
    and restructuring — so the user can act without grepping docs."""
    with pytest.raises(ValidationError) as exc:
        bbox(CHILDREN)
    msg = str(exc.value)
    assert "inline=True" in msg
    assert "restructure" in msg


def test_halve_in_non_inline_transform_raises_via_bbox():
    """The canonical bug: ``node.halve(...)`` inside a non-inline
    transform's ``expand()`` calls ``bbox(node)`` to size its cutter,
    where ``node`` is the CHILDREN placeholder. The bbox raise
    propagates so the user sees the breakage immediately rather than
    receiving a silent 1mm cutter in the emitted SCAD."""
    try:
        @transform("_test_split_x_non_inline")
        def split_x(node):
            return node.halve([-1, 0, 0])

        part = cube(50).translate([0, 0, 0])._test_split_x_non_inline()
        with pytest.raises(ValidationError, match="CHILDREN placeholder"):
            emit_str(part)
    finally:
        unregister("_test_split_x_non_inline")


def test_halve_in_inline_transform_works():
    """``inline=True`` exposes the real child to ``expand()``, so
    ``halve()``'s bbox introspection sees the actual geometry. Same
    user code, different decorator: works."""
    try:
        @transform("_test_split_x_inline", inline=True)
        def split_x(node):
            return node.halve([-1, 0, 0])

        part = cube(50)._test_split_x_inline()
        out = emit_str(part)
        # halve emits intersection(part, kept_box); with the real
        # 50-unit cube visible, the cutter sizes correctly.
        assert "intersection" in out
        # The cutter cube is sized from the actual bbox, not 1mm.
        # cube(50) has bbox extending to 50, so size = 2 * 50 * 1.02 = 102.
        assert "cube([102" in out or "cube([1," not in out
    finally:
        unregister("_test_split_x_inline")
