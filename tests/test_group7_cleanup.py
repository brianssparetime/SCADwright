"""Tests for MajorReview2 Group 7.

7a: Custom.kwargs sorted invariant enforcement.
7b: Text bbox hint (mirrors scad_import's pattern).
"""

import pytest

from scadwright import Component, Param, bbox
from scadwright.ast.custom import Custom
from scadwright.errors import ValidationError
from scadwright.primitives import cube, text
from scadwright.transforms import transform
from scadwright._custom_transforms.base import unregister


# --- 7a: Custom invariant ---


def test_custom_rejects_unsorted_kwargs():
    with pytest.raises(ValidationError, match="sorted by name"):
        Custom(name="x", kwargs=(("z", 1), ("a", 2)), child=cube(1))


def test_custom_accepts_sorted_kwargs():
    n = Custom(name="x", kwargs=(("a", 1), ("z", 2)), child=cube(1))
    assert n.kwargs == (("a", 1), ("z", 2))


def test_custom_accepts_empty_kwargs():
    Custom(name="x", kwargs=(), child=cube(1))


def test_custom_accepts_single_kwarg():
    Custom(name="x", kwargs=(("only", 1),), child=cube(1))


def test_factory_dispatch_still_produces_sorted_kwargs():
    try:
        @transform("_group7_probe")
        def _p(node, *, b, a):
            return node

        # Keyword order at call site doesn't matter — factory must sort.
        result = cube(1)._group7_probe(b=2, a=1)
        names = [k for k, _ in result.kwargs]
        assert names == sorted(names)
    finally:
        unregister("_group7_probe")


# --- 7b: Text bbox hint ---


def test_text_bbox_hint_returned_verbatim():
    t = text("Hi", bbox=((0, 0, 0), (100, 20, 0)))
    bb = bbox(t)
    assert bb.min == (0.0, 0.0, 0.0)
    assert bb.max == (100.0, 20.0, 0.0)


def test_text_without_hint_falls_through_to_estimate():
    t = text("Hi", size=10)
    bb = bbox(t)
    # Heuristic: 0.6 * size * spacing * n_chars = 0.6 * 10 * 1 * 2 = 12 wide.
    assert bb.max[0] == pytest.approx(12.0)


def test_text_bbox_hint_rejects_wrong_shape():
    with pytest.raises(ValidationError, match="text bbox"):
        text("Hi", bbox=(1, 2, 3))


def test_text_bbox_hint_rejects_inverted_corners():
    with pytest.raises(ValidationError, match="text bbox"):
        text("Hi", bbox=((10, 0, 0), (5, 1, 0)))


def test_text_bbox_hint_never_emitted():
    from scadwright import emit_str

    out = emit_str(text("Hi", bbox=((0, 0, 0), (1, 1, 0))))
    assert "bbox" not in out
    assert "text(" in out


def test_text_bbox_hint_wins_over_estimate_with_different_dimensions():
    # Estimate for "Label" size 5 would be ~15 wide. Hint overrides.
    t = text("Label", size=5, bbox=((0, 0, 0), (500, 500, 0)))
    assert bbox(t).max == (500.0, 500.0, 0.0)


