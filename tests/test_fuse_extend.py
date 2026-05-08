"""Unit tests for Node.fuse_extend implementations.

These exercise the per-shape local-extension methods directly, without
going through attach() or fuse(). The behavior tests at the API level
live in test_fuse_phase1.py.
"""

import pytest

from scadwright import bbox
from scadwright.anchor import get_node_anchors
from scadwright.ast.primitives import Cube
from scadwright.ast.transforms import Translate


# --- Default (None) on the base class ---


def test_node_default_fuse_extend_returns_none():
    """Shapes that don't override fuse_extend get the base-class None."""
    from scadwright.primitives import sphere
    s = sphere(r=5)
    a = get_node_anchors(s)["top"]
    assert s.fuse_extend(a, 0.01) is None


# --- Cube ---


def test_cube_fuse_extend_top_uncentered_returns_bumped_cube():
    """Top fuse on a non-centered cube: size[2] += eps, no translate.

    The +Z face moves out by eps; the -Z face stays at z=0.
    """
    c = Cube(size=(5.0, 5.0, 10.0))
    a = get_node_anchors(c)["top"]
    extended = c.fuse_extend(a, 0.01)
    assert isinstance(extended, Cube)
    assert extended.size == pytest.approx((5.0, 5.0, 10.01))
    bb = bbox(extended)
    assert bb.min == pytest.approx((0.0, 0.0, 0.0))
    assert bb.max == pytest.approx((5.0, 5.0, 10.01))


def test_cube_fuse_extend_bottom_uncentered_translates_down():
    """Bottom fuse on a non-centered cube: bumped + translate(-eps in z).

    The -Z face moves out to z=-eps; the +Z face stays at z=h.
    """
    c = Cube(size=(5.0, 5.0, 10.0))
    a = get_node_anchors(c)["bottom"]
    extended = c.fuse_extend(a, 0.01)
    assert isinstance(extended, Translate)
    assert extended.v == pytest.approx((0.0, 0.0, -0.01))
    assert isinstance(extended.child, Cube)
    assert extended.child.size == pytest.approx((5.0, 5.0, 10.01))
    bb = bbox(extended)
    # Top preserved at z=10; bottom extended to -eps.
    assert bb.min[2] == pytest.approx(-0.01)
    assert bb.max[2] == pytest.approx(10.0)


def test_cube_fuse_extend_rside_uncentered():
    """+X face: same pattern as top, just on a different axis."""
    c = Cube(size=(5.0, 5.0, 10.0))
    a = get_node_anchors(c)["rside"]
    extended = c.fuse_extend(a, 0.01)
    assert isinstance(extended, Cube)
    assert extended.size == pytest.approx((5.01, 5.0, 10.0))


def test_cube_fuse_extend_lside_uncentered_translates_x():
    """-X face: bumped + translate(-eps in x)."""
    c = Cube(size=(5.0, 5.0, 10.0))
    a = get_node_anchors(c)["lside"]
    extended = c.fuse_extend(a, 0.01)
    assert isinstance(extended, Translate)
    assert extended.v == pytest.approx((-0.01, 0.0, 0.0))
    assert extended.child.size == pytest.approx((5.01, 5.0, 10.0))


def test_cube_fuse_extend_centered_top():
    """Centered cube top fuse: size bumps, then translate +eps/2 to put
    the full eps on the +Z side instead of the symmetric ±eps/2 split.
    """
    c = Cube(size=(10.0, 10.0, 10.0), center=(True, True, True))
    a = get_node_anchors(c)["top"]
    extended = c.fuse_extend(a, 0.01)
    assert isinstance(extended, Translate)
    assert extended.v == pytest.approx((0.0, 0.0, 0.005))
    bb = bbox(extended)
    # Bottom preserved at -5; top extended to 5.01.
    assert bb.min[2] == pytest.approx(-5.0)
    assert bb.max[2] == pytest.approx(5.01)


def test_cube_fuse_extend_centered_bottom():
    """Centered cube bottom fuse: translate -eps/2 to put the full eps
    on the -Z side.
    """
    c = Cube(size=(10.0, 10.0, 10.0), center=(True, True, True))
    a = get_node_anchors(c)["bottom"]
    extended = c.fuse_extend(a, 0.01)
    assert isinstance(extended, Translate)
    assert extended.v == pytest.approx((0.0, 0.0, -0.005))
    bb = bbox(extended)
    assert bb.min[2] == pytest.approx(-5.01)
    assert bb.max[2] == pytest.approx(5.0)


def test_cube_fuse_extend_mixed_center():
    """Per-axis center: only the relevant axis's bool affects the delta."""
    # Centered in X and Y, not in Z.
    c = Cube(size=(4.0, 4.0, 10.0), center=(True, True, False))
    # Top anchor (+Z): center[2] is False → no translate.
    extended_top = c.fuse_extend(get_node_anchors(c)["top"], 0.01)
    assert isinstance(extended_top, Cube)  # no translate wrapper
    # Rside anchor (+X): center[0] is True → translate +eps/2 in x.
    extended_rside = c.fuse_extend(get_node_anchors(c)["rside"], 0.01)
    assert isinstance(extended_rside, Translate)
    assert extended_rside.v == pytest.approx((0.005, 0.0, 0.0))


def test_cube_fuse_extend_preserves_source_location():
    """The bumped cube and translate carry the original cube's source_location."""
    from scadwright.ast.base import SourceLocation
    loc = SourceLocation(file="test.py", line=42, func="test_fn")
    c = Cube(size=(5.0, 5.0, 10.0), source_location=loc)
    a = get_node_anchors(c)["bottom"]
    extended = c.fuse_extend(a, 0.01)
    # Translate carries it.
    assert extended.source_location == loc
    # Inner Cube also carries it.
    assert extended.child.source_location == loc
