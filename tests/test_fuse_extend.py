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


# --- Cylinder ---


def test_cylinder_fuse_extend_top_uncentered():
    """Top fuse on a non-centered cylinder: h += eps, no translate."""
    from scadwright.ast.primitives import Cylinder
    c = Cylinder(h=10.0, r1=5.0, r2=5.0)
    a = get_node_anchors(c)["top"]
    extended = c.fuse_extend(a, 0.01)
    assert isinstance(extended, Cylinder)
    assert extended.h == pytest.approx(10.01)
    assert extended.r1 == pytest.approx(5.0)
    assert extended.r2 == pytest.approx(5.0)
    bb = bbox(extended)
    assert bb.min[2] == pytest.approx(0.0)
    assert bb.max[2] == pytest.approx(10.01)


def test_cylinder_fuse_extend_bottom_uncentered():
    """Bottom fuse on a non-centered cylinder: bumped + down(eps)."""
    from scadwright.ast.primitives import Cylinder
    c = Cylinder(h=10.0, r1=5.0, r2=5.0)
    a = get_node_anchors(c)["bottom"]
    extended = c.fuse_extend(a, 0.01)
    assert isinstance(extended, Translate)
    assert extended.v == pytest.approx((0.0, 0.0, -0.01))
    assert extended.child.h == pytest.approx(10.01)
    bb = bbox(extended)
    assert bb.min[2] == pytest.approx(-0.01)
    assert bb.max[2] == pytest.approx(10.0)  # top preserved


def test_cylinder_fuse_extend_centered():
    """Centered cylinder splits eps as ±eps/2."""
    from scadwright.ast.primitives import Cylinder
    c = Cylinder(h=10.0, r1=5.0, r2=5.0, center=True)
    a = get_node_anchors(c)["top"]
    extended = c.fuse_extend(a, 0.01)
    assert isinstance(extended, Translate)
    assert extended.v == pytest.approx((0.0, 0.0, 0.005))
    bb = bbox(extended)
    assert bb.min[2] == pytest.approx(-5.0)
    assert bb.max[2] == pytest.approx(5.01)


def test_cylinder_fuse_extend_cone_top():
    """Cone (r1 != r2) top fuse: bumped h, both radii preserved."""
    from scadwright.ast.primitives import Cylinder
    c = Cylinder(h=10.0, r1=5.0, r2=2.0)
    a = get_node_anchors(c)["top"]
    extended = c.fuse_extend(a, 0.01)
    assert isinstance(extended, Cylinder)
    assert extended.h == pytest.approx(10.01)
    assert extended.r1 == pytest.approx(5.0)
    assert extended.r2 == pytest.approx(2.0)


def test_cylinder_fuse_extend_apex_top_returns_none():
    """A cone that tapers to a point at the top (r2=0) has no top face
    to extend — fuse_extend returns None and the caller falls back."""
    from scadwright.ast.primitives import Cylinder
    c = Cylinder(h=10.0, r1=5.0, r2=0.0)
    a = get_node_anchors(c)["top"]
    assert c.fuse_extend(a, 0.01) is None


def test_cylinder_fuse_extend_apex_bottom_returns_none():
    """Same for a cone tapering to a point at the bottom (r1=0)."""
    from scadwright.ast.primitives import Cylinder
    c = Cylinder(h=10.0, r1=0.0, r2=5.0)
    a = get_node_anchors(c)["bottom"]
    assert c.fuse_extend(a, 0.01) is None


def test_cylinder_fuse_extend_cylindrical_wall_returns_none():
    """The outer_wall anchor on cylinder() has kind='cylindrical'.
    Phase 1 doesn't support radial extension; returns None."""
    from scadwright.primitives import cylinder
    c = cylinder(h=10, r=5)
    a = get_node_anchors(c)["outer_wall"]
    assert a.kind == "cylindrical"
    assert c.fuse_extend(a, 0.01) is None


# --- LinearExtrude ---


def test_linear_extrude_fuse_extend_top():
    """LinearExtrude top fuse: height += eps, no translate."""
    from scadwright.primitives import square
    from scadwright.ast.extrude import LinearExtrude
    e = square(size=(4, 4)).linear_extrude(height=10)
    assert isinstance(e, LinearExtrude)
    a = get_node_anchors(e)["top"]
    extended = e.fuse_extend(a, 0.01)
    assert isinstance(extended, LinearExtrude)
    assert extended.height == pytest.approx(10.01)
    bb = bbox(extended)
    assert bb.max[2] == pytest.approx(10.01)
    assert bb.min[2] == pytest.approx(0.0)


def test_linear_extrude_fuse_extend_bottom():
    """LinearExtrude bottom fuse: height += eps + translate(-eps in z)."""
    from scadwright.primitives import square
    e = square(size=(4, 4)).linear_extrude(height=10)
    a = get_node_anchors(e)["bottom"]
    extended = e.fuse_extend(a, 0.01)
    assert isinstance(extended, Translate)
    assert extended.v == pytest.approx((0.0, 0.0, -0.01))
    assert extended.child.height == pytest.approx(10.01)
    bb = bbox(extended)
    assert bb.min[2] == pytest.approx(-0.01)
    assert bb.max[2] == pytest.approx(10.0)


def test_linear_extrude_fuse_extend_centered():
    """Centered LinearExtrude top fuse splits eps as +eps/2."""
    from scadwright.primitives import square
    e = square(size=(4, 4)).linear_extrude(height=10, center=True)
    a = get_node_anchors(e)["top"]
    extended = e.fuse_extend(a, 0.01)
    assert isinstance(extended, Translate)
    assert extended.v == pytest.approx((0.0, 0.0, 0.005))


def test_linear_extrude_fuse_extend_preserves_other_kwargs():
    """Twist, slices, scale, convexity, fn/fa/fs all carry through to the
    bumped extrude. The eps-band twist/scale drift is documented but
    geometrically invisible."""
    from scadwright.primitives import square
    e = square(size=(4, 4)).linear_extrude(
        height=10, twist=720, scale=(0.5, 0.5), convexity=4, fn=64,
    )
    a = get_node_anchors(e)["top"]
    extended = e.fuse_extend(a, 0.01)
    # No translate wrapper for top + uncentered.
    assert extended.height == pytest.approx(10.01)
    assert extended.twist == pytest.approx(720)
    assert extended.scale == pytest.approx((0.5, 0.5))
    assert extended.convexity == 4
    assert extended.fn == 64


# --- Transform recursion ---


def test_translate_fuse_extend_recurses_to_cube():
    """Cube.up(5).fuse_extend(top, eps) extends the inner cube and
    re-wraps in the same translate."""
    c = Cube(size=(5.0, 5.0, 10.0)).up(5)
    a = get_node_anchors(c)["top"]
    extended = c.fuse_extend(a, 0.01)
    # Outer Translate(v=(0,0,5)) preserved; inner Cube bumped.
    assert isinstance(extended, Translate)
    assert extended.v == pytest.approx((0.0, 0.0, 5.0))
    assert isinstance(extended.child, Cube)
    assert extended.child.size == pytest.approx((5.0, 5.0, 10.01))
    bb = bbox(extended)
    # Cube originally at z=5..15; extended top to z=15.01; bottom preserved at 5.
    assert bb.min[2] == pytest.approx(5.0)
    assert bb.max[2] == pytest.approx(15.01)


def test_translate_fuse_extend_chain():
    """Cube.up(5).right(3).fuse_extend(top, eps): nested Translates each
    peel off one layer."""
    c = Cube(size=(5.0, 5.0, 10.0)).up(5).right(3)
    a = get_node_anchors(c)["top"]
    extended = c.fuse_extend(a, 0.01)
    bb = bbox(extended)
    assert bb.min == pytest.approx((3.0, 0.0, 5.0))
    assert bb.max == pytest.approx((8.0, 5.0, 15.01))


def test_translate_fuse_extend_returns_none_when_child_doesnt_support():
    """Sphere doesn't support fuse_extend → wrapping it in Translate also
    doesn't, recursion returns None all the way up."""
    from scadwright.primitives import sphere
    s = sphere(r=5).up(10)
    a = get_node_anchors(s)["top"]
    assert s.fuse_extend(a, 0.01) is None


def test_rotate_fuse_extend_around_z_extends_local_axis():
    """Anchor names track the cube's LOCAL face — the framework rotates
    the anchor's position/normal but keeps the name. So extending the
    'top' anchor on Cube.rotate([0,0,90]) bumps the cube's local +Z (the
    rotation around Z preserves the +Z face's identity). The recursion
    into the Rotate wrapper uses the inverse rotation to recover the
    cube's local-frame anchor, then bumps the right axis.
    """
    from scadwright.ast.transforms import Rotate
    c = Cube(size=(5.0, 5.0, 10.0)).rotate([0, 0, 90])
    a = get_node_anchors(c)["top"]
    # The world-frame anchor: position rotated, normal still +Z (R_z
    # preserves the Z axis).
    extended = c.fuse_extend(a, 0.01)
    assert isinstance(extended, Rotate)
    assert isinstance(extended.child, Cube)
    # The cube's local +Z (top) was extended — size[2] bumps.
    assert extended.child.size == pytest.approx((5.0, 5.0, 10.01))


def test_rotate_fuse_extend_around_x_back_extends_local_y():
    """Cube.rotate([90, 0, 0]).fuse_extend(back, eps) inverse-rotates
    the back anchor (cube's local +Y) and extends size[1] of the inner
    cube — the rotation just changes how the result appears in world
    space, not which local face was extended."""
    from scadwright.ast.transforms import Rotate
    c = Cube(size=(5.0, 5.0, 10.0)).rotate([90, 0, 0])
    a = get_node_anchors(c)["back"]
    extended = c.fuse_extend(a, 0.01)
    assert isinstance(extended, Rotate)
    inner = extended.child
    # Local +Y face → size[1] bumps, no translate (sign=+1, not centered).
    assert isinstance(inner, Cube)
    assert inner.size == pytest.approx((5.0, 5.01, 10.0))


def test_mirror_fuse_extend_recurses_to_cube():
    """Cube.mirror([1, 0, 0]).fuse_extend recurses through the Mirror.
    Anchor names still track the cube's local face; extending the
    cube's 'rside' bumps size[0]."""
    from scadwright.ast.transforms import Mirror
    c = Cube(size=(5.0, 5.0, 10.0)).mirror([1, 0, 0])
    a = get_node_anchors(c)["rside"]
    extended = c.fuse_extend(a, 0.01)
    assert isinstance(extended, Mirror)
    # rside is +X, sign=+1, no translate.
    assert isinstance(extended.child, Cube)
    assert extended.child.size == pytest.approx((5.01, 5.0, 10.0))


# --- Source location preservation ---


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
