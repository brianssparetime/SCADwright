"""``@transform(tight_bbox=...)`` hook for declaring the tight AABB of a
custom transform's result.

The framework can't tighten the bbox of a Difference by AST analysis,
so transforms that use ``difference()`` internally need this hook for
``tight_bbox()`` to succeed. The hook receives the real child node
plus the transform's kwargs and returns a ``BBox``.

``bbox()`` (loose) does NOT consult the hook — only ``tight_bbox()``
does. The two APIs deliberately diverge here.
"""

from __future__ import annotations

import pytest

from scadwright import BBox, bbox, tight_bbox
from scadwright._custom_transforms.base import Transform, register, unregister
from scadwright.boolops import difference, intersection
from scadwright.primitives import cube, cylinder, sphere
from scadwright.transforms import transform


# =============================================================================
# Hook returns BBox — visitor uses it
# =============================================================================


def test_hook_returns_bbox_used_directly():
    try:
        @transform(
            "_test_chop_decl",
            tight_bbox=lambda child, *, keep_x, **_: BBox(
                min=(0, 0, 0), max=(keep_x, 20, 20),
            ),
        )
        def _test_chop_decl(node, *, keep_x):
            # Body uses difference; the hook is what makes tight_bbox work.
            return difference(node, cube(50).translate([keep_x, -1, -1]))

        bb = tight_bbox(cube(20)._test_chop_decl(keep_x=10))
        assert bb.min == (0, 0, 0)
        assert bb.max == (10, 20, 20)
    finally:
        unregister("_test_chop_decl")


def test_hook_kwargs_match_transform_kwargs():
    """The hook receives exactly the kwargs the transform was called with."""
    captured = {}

    def _capture_hook(child, **kwargs):
        captured.update(kwargs)
        return BBox(min=(0, 0, 0), max=(1, 1, 1))

    try:
        @transform("_test_capture", tight_bbox=_capture_hook)
        def _test_capture(node, *, foo, bar=2):
            return node

        tight_bbox(cube(10)._test_capture(foo=42, bar=99))
        assert captured == {"foo": 42, "bar": 99}
    finally:
        unregister("_test_capture")


def test_hook_receives_real_child_not_placeholder():
    """The framework calls the hook with the actual wrapped Node — never
    the ChildrenMarker placeholder. Same contract as the bbox visitor's
    visit_Custom path: the placeholder is emit-only."""
    captured_child = []

    def _capture_child(child, **_):
        captured_child.append(child)
        return BBox(min=(0, 0, 0), max=(1, 1, 1))

    try:
        @transform("_test_child", tight_bbox=_capture_child)
        def _test_child(node):
            return node

        actual = cube(10)
        tight_bbox(actual._test_child())
        assert captured_child[0] is actual
    finally:
        unregister("_test_child")


# =============================================================================
# Hook returns None — falls through to walking
# =============================================================================


def test_hook_returns_none_falls_through_to_walk():
    """A hook returning None is the same as no hook — the framework
    walks the expanded body. Useful for transforms whose hook can
    handle some kwargs combinations and not others."""
    try:
        @transform(
            "_test_optional_hook",
            tight_bbox=lambda child, **_: None,
        )
        def _test_optional_hook(node):
            # Body uses Intersection (via halve internals), which the
            # walk handles natively — hook isn't needed for tightness.
            return intersection(node, cube(8))

        bb = tight_bbox(cube(20)._test_optional_hook())
        # Intersection clips: 20³ ∩ 8³ = 8³.
        assert bb.min == (0, 0, 0)
        assert bb.max == (8, 8, 8)
    finally:
        unregister("_test_optional_hook")


# =============================================================================
# Hook raises — wrapped error names the transform
# =============================================================================


def test_hook_raising_notimplemented_wrapped():
    def _refusing_hook(child, **_):
        raise NotImplementedError("can't compute for this kwargs combo")

    try:
        @transform("_test_refuse", tight_bbox=_refusing_hook)
        def _test_refuse(node):
            return node

        with pytest.raises(
            NotImplementedError,
            match=r"@transform\('_test_refuse'\)\.tight_bbox",
        ):
            tight_bbox(cube(10)._test_refuse())
    finally:
        unregister("_test_refuse")


# =============================================================================
# Hook returns non-BBox — TypeError
# =============================================================================


def test_hook_must_return_bbox():
    try:
        @transform("_test_bad_return", tight_bbox=lambda c, **_: "not a bbox")
        def _test_bad_return(node):
            return node

        with pytest.raises(TypeError, match="must return a BBox"):
            tight_bbox(cube(10)._test_bad_return())
    finally:
        unregister("_test_bad_return")


def test_hook_returning_tuple_rejected():
    """Tuples look bbox-shaped but aren't — explicit TypeError."""
    try:
        @transform(
            "_test_tuple",
            tight_bbox=lambda c, **_: ((0, 0, 0), (1, 1, 1)),
        )
        def _test_tuple(node):
            return node

        with pytest.raises(TypeError, match="must return a BBox"):
            tight_bbox(cube(10)._test_tuple())
    finally:
        unregister("_test_tuple")


# =============================================================================
# No hook — walk fails for Difference, useful named error
# =============================================================================


def test_no_hook_with_difference_body_useful_error():
    try:
        @transform("_test_chop_no_hook")
        def _test_chop_no_hook(node):
            return difference(node, cube(50).translate([10, -1, -1]))

        with pytest.raises(NotImplementedError) as exc:
            tight_bbox(cube(20)._test_chop_no_hook())
        msg = str(exc.value)
        assert "_test_chop_no_hook" in msg
        assert "tight_bbox=" in msg
        assert "halve" in msg
    finally:
        unregister("_test_chop_no_hook")


def test_no_hook_with_intersection_body_walks_fine():
    """Transforms whose body uses only operators that AST analysis can
    tighten (Intersection via halve, Union, transforms) work without
    a hook. Pin the no-hook-needed case."""
    try:
        @transform("_test_intersect")
        def _test_intersect(node):
            return node.halve([1, 0, 0])

        bb = tight_bbox(cube(20, center=True)._test_intersect())
        # Halve keeps +x: x ∈ [0, 10], y/z ∈ [-10, 10].
        assert bb.min[0] == 0
        assert bb.max[0] == 10
    finally:
        unregister("_test_intersect")


# =============================================================================
# Transform-subclass form (not via decorator) — hook works the same way
# =============================================================================


def test_subclass_form_overriding_tight_bbox():
    """The class-based escape hatch also gets the hook by overriding
    ``Transform.tight_bbox``. Same behavior as the decorator path."""

    class _SubclassChop(Transform):
        name = "_test_subclass_chop"

        def expand(self, child, *, keep_x):
            return difference(child, cube(50).translate([keep_x, -1, -1]))

        def tight_bbox(self, child, *, keep_x):
            cb = tight_bbox(child)
            return BBox(
                min=(cb.min[0], cb.min[1], cb.min[2]),
                max=(keep_x, cb.max[1], cb.max[2]),
            )

    try:
        register("_test_subclass_chop", _SubclassChop())
        bb = tight_bbox(cube(20)._test_subclass_chop(keep_x=12))
        assert bb.max[0] == 12
        assert bb.max[1] == 20
    finally:
        unregister("_test_subclass_chop")


# =============================================================================
# bbox() (loose) does NOT consult the hook
# =============================================================================


def test_bbox_loose_ignores_hook():
    """The hook is for tight_bbox() only. bbox() walks the expansion
    and uses first-child's-bbox for any Difference inside — same
    behavior with or without a hook. Ensures the two APIs stay
    distinct in semantics."""
    try:
        # Hook would lie if consumed by bbox() — make it return a tiny
        # bbox so we can distinguish.
        @transform(
            "_test_bbox_loose",
            tight_bbox=lambda c, **_: BBox(min=(0, 0, 0), max=(1, 1, 1)),
        )
        def _test_bbox_loose(node):
            return difference(node, cube(50).translate([10, -1, -1]))

        loose = bbox(cube(20)._test_bbox_loose())
        # bbox() walks the expansion; first child of Difference is the
        # 20-cube → bbox is 0..20.
        assert loose.min == (0, 0, 0)
        assert loose.max == (20, 20, 20)
    finally:
        unregister("_test_bbox_loose")


# =============================================================================
# Composition through outer transforms
# =============================================================================


def test_hook_composes_with_outer_transform():
    """The visitor applies its self._ctx to the hook's returned BBox,
    so wrapping the Custom node in a Translate composes correctly."""
    try:
        @transform(
            "_test_composes",
            tight_bbox=lambda c, **_: BBox(min=(0, 0, 0), max=(10, 10, 10)),
        )
        def _test_composes(node):
            return node

        bb = tight_bbox(cube(20)._test_composes().translate([100, 0, 0]))
        assert bb.min == (100, 0, 0)
        assert bb.max == (110, 10, 10)
    finally:
        unregister("_test_composes")
