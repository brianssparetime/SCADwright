"""Geometry assertion helpers built on sc.bbox().

All raise stdlib AssertionError with informative messages. Pytest's
introspection picks them up cleanly.
"""

from __future__ import annotations

import math

from scadwright.bbox import BBox, bbox as _bbox


def _coerce_envelope(envelope) -> BBox:
    """Accept a 3-element size (centered envelope) or a BBox."""
    if isinstance(envelope, BBox):
        return envelope
    try:
        items = list(envelope)
    except TypeError:
        raise TypeError(f"envelope must be a BBox or 3-element size, got {type(envelope).__name__}")
    if len(items) != 3:
        raise ValueError(f"envelope size must have 3 elements, got {len(items)}")
    x, y, z = (float(v) for v in items)
    return BBox(min=(-x / 2.0, -y / 2.0, -z / 2.0), max=(x / 2.0, y / 2.0, z / 2.0))


def assert_fits_in(node, envelope) -> None:
    """Assert that node's bbox fits within `envelope` (a size-3 vector or BBox)."""
    env = _coerce_envelope(envelope)
    nb = _bbox(node)
    if not env.contains(nb):
        raise AssertionError(
            f"node bbox does not fit in envelope:\n"
            f"  node:     {nb}\n"
            f"  envelope: {env}"
        )


def assert_no_collision(a, b) -> None:
    """Assert that the bboxes of `a` and `b` do not overlap."""
    ba = _bbox(a)
    bb = _bbox(b)
    if ba.overlaps(bb):
        raise AssertionError(
            f"bboxes overlap:\n"
            f"  a: {ba}\n"
            f"  b: {bb}"
        )


def assert_contains(outer, inner) -> None:
    """Assert that outer's bbox fully contains inner's bbox."""
    bo = _bbox(outer)
    bi = _bbox(inner)
    if not bo.contains(bi):
        raise AssertionError(
            f"outer does not contain inner:\n"
            f"  outer: {bo}\n"
            f"  inner: {bi}"
        )


def assert_bbox_equal(node, expected: BBox, tol: float = 1e-9) -> None:
    """Assert that node's bbox matches `expected` element-wise within tolerance."""
    actual = _bbox(node)
    diffs = []
    for axis, label in enumerate("xyz"):
        if abs(actual.min[axis] - expected.min[axis]) > tol:
            diffs.append(f"min.{label}: actual={actual.min[axis]}, expected={expected.min[axis]}")
        if abs(actual.max[axis] - expected.max[axis]) > tol:
            diffs.append(f"max.{label}: actual={actual.max[axis]}, expected={expected.max[axis]}")
    if diffs:
        raise AssertionError(
            f"bbox mismatch (tol={tol}):\n"
            f"  actual:   {actual}\n"
            f"  expected: {expected}\n"
            "  " + "\n  ".join(diffs)
        )
