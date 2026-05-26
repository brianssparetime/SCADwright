"""Unit tests for Node.fuse_extend implementations.

These exercise the per-shape local-extension methods directly, without
going through attach() or fuse(). The behavior tests at the API level
live in test_fuse_phase1.py.

Standard-library shape audit (Stage 4 boundary):

  Has fuse_extend lever:
    - Cube (planar; cap bumps axial dimension)
    - Cylinder (planar caps + cylindrical/conical walls)
    - Sphere (spherical)
    - LinearExtrude (planar end-face)
    - Tube (cylindrical walls; rebuilds with od/id bumped)
    - Funnel (conical walls; rebuilds with bot/top od or id bumped)
    - Barrel (meridional walls; rebuilds with end_d/mid_d or thk bumped)

  No fuse_extend lever (rely on the other side of the contact, or
  fall through to cross_section_extend for planar):
    - RoundedBox, Capsule, RectTube, Prismoid, Wedge, PieSlice,
      UShapeChannel, FilletRing
    - Author-defined Components without an override

  Components without a lever still participate as the host side when
  the other side carries one — for example, a custom ElementHolder
  Component declaring outer_wall fuses cleanly against a Tube barrel
  because Tube provides the inner-wall radial lever.
"""

import pytest

from scadwright import bbox
from scadwright.anchor import get_node_anchors
from scadwright.ast.primitives import Cube
from scadwright.ast.transforms import Translate


# --- Default (None) on the base class ---


def test_node_default_fuse_extend_returns_none():
    """Shapes that don't override fuse_extend get the base-class None.
    Polyhedron is a concrete shape with no parametric lever — its
    fuse_extend falls through to Node's default.
    """
    from scadwright.ast.primitives import Polyhedron
    p = Polyhedron(
        points=((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)),
        faces=((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)),
    )
    a = get_node_anchors(p)["top"]
    assert p.fuse_extend(a, 0.01) is None


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


def test_cylinder_fuse_extend_cylindrical_wall_grows_radii():
    """The outer_wall anchor has kind='cylindrical'; outer extension
    bumps r1 and r2 by +eps along the radial direction."""
    from scadwright.primitives import cylinder
    c = cylinder(h=10, r=5)
    a = get_node_anchors(c)["outer_wall"]
    assert a.kind == "cylindrical"
    extended = c.fuse_extend(a, 0.01)
    assert extended is not None
    assert extended.r1 == pytest.approx(5.01)
    assert extended.r2 == pytest.approx(5.01)
    assert extended.h == pytest.approx(10.0)


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
    """A Polyhedron has no fuse_extend lever; wrapping it in Translate
    doesn't add one — recursion returns None all the way up."""
    from scadwright.ast.primitives import Polyhedron
    from scadwright.ast.transforms import Translate
    p = Polyhedron(
        points=((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)),
        faces=((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)),
    )
    wrapped = Translate(v=(0.0, 0.0, 10.0), child=p)
    a = get_node_anchors(wrapped)["top"]
    assert wrapped.fuse_extend(a, 0.01) is None


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


# --- Sphere: spherical anchor radial extension ---


def test_sphere_fuse_extend_outer_grows_radius():
    """Outer-facing spherical anchor (inner=False) bumps r by +eps."""
    from scadwright.ast.primitives import Sphere
    s = Sphere(r=5.0)
    a = get_node_anchors(s)["surface"]  # spherical, inner=False
    extended = s.fuse_extend(a, 0.01)
    assert isinstance(extended, Sphere)
    assert extended.r == pytest.approx(5.01)


def test_sphere_fuse_extend_works_for_face_anchors():
    """Sphere's bbox-derived face anchors are kind='spherical' and
    point at the same sphere — fuse_extend handles them too."""
    from scadwright.ast.primitives import Sphere
    s = Sphere(r=5.0)
    a = get_node_anchors(s)["top"]  # kind=spherical
    extended = s.fuse_extend(a, 0.01)
    assert isinstance(extended, Sphere)
    assert extended.r == pytest.approx(5.01)


def test_sphere_fuse_extend_inner_anchor_shrinks_radius():
    """An inner=True spherical anchor on a sphere shrinks the radius
    by eps. Used in the symmetric peer dispatch when the host sphere
    is on the outside of a nested-sphere assembly."""
    from dataclasses import replace
    from scadwright.ast.primitives import Sphere
    s = Sphere(r=5.0)
    a = get_node_anchors(s)["surface"]
    a_inner = replace(a, inner=True, normal=(-a.normal[0], -a.normal[1], -a.normal[2]))
    extended = s.fuse_extend(a_inner, 0.01)
    assert isinstance(extended, Sphere)
    assert extended.r == pytest.approx(4.99)


def test_sphere_fuse_extend_planar_anchor_returns_none():
    """Spheres only have spherical anchors in get_node_anchors output,
    but a foreign planar anchor passed in returns None."""
    from dataclasses import replace
    from scadwright.ast.primitives import Sphere
    from scadwright.anchor import Anchor
    s = Sphere(r=5.0)
    a = Anchor(position=(0, 0, 5), normal=(0, 0, 1), kind="planar")
    assert s.fuse_extend(a, 0.01) is None


def test_sphere_fuse_extend_inner_to_zero_raises():
    from dataclasses import replace
    from scadwright.ast.primitives import Sphere
    from scadwright.errors import ValidationError
    s = Sphere(r=0.005)
    a = get_node_anchors(s)["surface"]
    a_inner = replace(a, inner=True, normal=(-a.normal[0], -a.normal[1], -a.normal[2]))
    with pytest.raises(ValidationError, match="shrink past zero radius"):
        s.fuse_extend(a_inner, 0.01)


# --- Cylinder: cylindrical / conical wall anchor radial extension ---


def test_cylinder_fuse_extend_outer_wall_grows_radii():
    """Outer wall of a true cylinder: both r1 and r2 bump by +eps."""
    from scadwright.ast.primitives import Cylinder
    c = Cylinder(h=10.0, r1=5.0, r2=5.0)
    a = get_node_anchors(c)["outer_wall"]
    extended = c.fuse_extend(a, 0.01)
    assert isinstance(extended, Cylinder)
    assert extended.r1 == pytest.approx(5.01)
    assert extended.r2 == pytest.approx(5.01)
    assert extended.h == pytest.approx(10.0)


def test_cone_fuse_extend_outer_wall_grows_both_radii():
    """Conical outer wall: r1 and r2 both bump by +eps; the cone
    slope is preserved within the eps band."""
    from scadwright.ast.primitives import Cylinder
    c = Cylinder(h=10.0, r1=5.0, r2=10.0)
    a = get_node_anchors(c)["outer_wall"]  # kind=conical for r1 != r2
    extended = c.fuse_extend(a, 0.01)
    assert isinstance(extended, Cylinder)
    assert extended.r1 == pytest.approx(5.01)
    assert extended.r2 == pytest.approx(10.01)


def test_cylinder_fuse_extend_inner_wall_shrinks_radii():
    """An inner=True cylindrical anchor shrinks the cylinder's radii."""
    from dataclasses import replace
    from scadwright.ast.primitives import Cylinder
    c = Cylinder(h=10.0, r1=5.0, r2=5.0)
    a = get_node_anchors(c)["outer_wall"]
    a_inner = replace(a, inner=True, normal=(-a.normal[0], -a.normal[1], -a.normal[2]))
    extended = c.fuse_extend(a_inner, 0.01)
    assert isinstance(extended, Cylinder)
    assert extended.r1 == pytest.approx(4.99)
    assert extended.r2 == pytest.approx(4.99)


def test_cylinder_fuse_extend_inner_to_negative_radius_raises():
    from dataclasses import replace
    from scadwright.ast.primitives import Cylinder
    from scadwright.errors import ValidationError
    c = Cylinder(h=10.0, r1=0.005, r2=0.005)
    a = get_node_anchors(c)["outer_wall"]
    a_inner = replace(a, inner=True, normal=(-a.normal[0], -a.normal[1], -a.normal[2]))
    with pytest.raises(ValidationError, match="negative radius"):
        c.fuse_extend(a_inner, 0.01)


def test_cylinder_fuse_extend_planar_branch_unchanged():
    """Existing planar cap behavior must not regress: bump h, keep
    radii; non-centered cylinder with top anchor → bare Cylinder."""
    from scadwright.ast.primitives import Cylinder
    c = Cylinder(h=10.0, r1=5.0, r2=5.0)
    a = get_node_anchors(c)["top"]
    extended = c.fuse_extend(a, 0.01)
    # Top anchor on uncentered cylinder: no translate wrap.
    assert isinstance(extended, Cylinder)
    assert extended.h == pytest.approx(10.01)
    assert extended.r1 == pytest.approx(5.0)
    assert extended.r2 == pytest.approx(5.0)


# --- Tube (Component): cylindrical wall extension via rebuild ---


def test_tube_fuse_extend_outer_wall_grows_od():
    """Tube outer extension: od += 2*eps, id preserved."""
    from scadwright.shapes import Tube
    t = Tube(h=20.0, od=10.0, id=6.0)
    a = t.get_anchors()["outer_wall"]
    extended = t.fuse_extend(a, 0.01)
    assert isinstance(extended, Tube)
    assert extended.od == pytest.approx(10.02)
    assert extended.id == pytest.approx(6.0)
    assert extended.h == pytest.approx(20.0)
    assert extended.thk == pytest.approx(2.01)


def test_tube_fuse_extend_inner_wall_shrinks_id():
    """Tube inner extension: id -= 2*eps, od preserved."""
    from scadwright.shapes import Tube
    t = Tube(h=20.0, od=10.0, id=6.0)
    a = t.get_anchors()["inner_wall"]
    extended = t.fuse_extend(a, 0.01)
    assert isinstance(extended, Tube)
    assert extended.od == pytest.approx(10.0)
    assert extended.id == pytest.approx(5.98)
    assert extended.thk == pytest.approx(2.01)


def test_tube_fuse_extend_inner_to_zero_raises():
    from scadwright.shapes import Tube
    from scadwright.errors import ValidationError
    t = Tube(h=20.0, od=10.0, id=0.005)
    a = t.get_anchors()["inner_wall"]
    with pytest.raises(ValidationError, match="bore can't shrink"):
        t.fuse_extend(a, 0.01)


def test_tube_fuse_extend_planar_anchor_returns_none():
    """Tube fuse_extend handles cylindrical walls only; planar caps
    fall to the cross-section path through Component.cross_section_extend."""
    from scadwright.shapes import Tube
    t = Tube(h=20.0, od=10.0, id=6.0)
    a = t.get_anchors()["top"]  # planar cap
    assert t.fuse_extend(a, 0.01) is None


# --- Funnel (Component): conical wall extension via rebuild ---


def test_funnel_fuse_extend_outer_wall_bumps_both_ods():
    from scadwright.shapes import Funnel
    f = Funnel(h=20.0, thk=2.0, bot_od=20.0, top_od=30.0)
    a = f.get_anchors()["outer_wall"]
    extended = f.fuse_extend(a, 0.01)
    assert isinstance(extended, Funnel)
    assert extended.bot_od == pytest.approx(20.02)
    assert extended.top_od == pytest.approx(30.02)
    assert extended.thk == pytest.approx(2.0)


def test_funnel_fuse_extend_inner_wall_shrinks_both_ids():
    from scadwright.shapes import Funnel
    f = Funnel(h=20.0, thk=2.0, bot_od=20.0, top_od=30.0)  # bot_id=16, top_id=26
    a = f.get_anchors()["inner_wall"]
    extended = f.fuse_extend(a, 0.01)
    assert isinstance(extended, Funnel)
    assert extended.bot_id == pytest.approx(15.98)
    assert extended.top_id == pytest.approx(25.98)
    assert extended.thk == pytest.approx(2.0)


def test_funnel_fuse_extend_inner_to_zero_raises():
    from scadwright.shapes import Funnel
    from scadwright.errors import ValidationError
    f = Funnel(h=20.0, thk=2.0, bot_id=0.005, top_id=30.0)
    a = f.get_anchors()["inner_wall"]
    with pytest.raises(ValidationError, match="shrink past zero"):
        f.fuse_extend(a, 0.01)


# --- Barrel (Component): meridional wall extension via rebuild ---


def test_barrel_fuse_extend_outer_wall_grows_both_diameters():
    from scadwright.shapes import Barrel
    b = Barrel(h=40.0, end_d=20.0, mid_d=28.0, thk=2.0)
    a = b.get_anchors()["outer_wall"]
    extended = b.fuse_extend(a, 0.01)
    assert isinstance(extended, Barrel)
    assert extended.end_d == pytest.approx(20.02)
    assert extended.mid_d == pytest.approx(28.02)
    assert extended.thk == pytest.approx(2.0)
    assert extended.h == pytest.approx(40.0)


def test_barrel_fuse_extend_inner_wall_thickens_wall():
    from scadwright.shapes import Barrel
    b = Barrel(h=40.0, end_d=20.0, mid_d=28.0, thk=2.0)
    a = b.get_anchors()["inner_wall"]
    extended = b.fuse_extend(a, 0.01)
    assert isinstance(extended, Barrel)
    # Outer profile unchanged; thk grows.
    assert extended.end_d == pytest.approx(20.0)
    assert extended.mid_d == pytest.approx(28.0)
    assert extended.thk == pytest.approx(2.01)


def test_barrel_fuse_extend_inner_on_solid_barrel_raises():
    from scadwright.shapes import Barrel
    from scadwright.errors import ValidationError
    b = Barrel(h=40.0, end_d=20.0, mid_d=28.0)  # thk=None, solid
    a = b.get_anchors()["inner_wall"]
    with pytest.raises(ValidationError, match="solid"):
        b.fuse_extend(a, 0.01)


def test_barrel_fuse_extend_planar_anchor_returns_none():
    from scadwright.shapes import Barrel
    b = Barrel(h=40.0, end_d=20.0, mid_d=28.0, thk=2.0)
    a = b.get_anchors()["top"]
    assert b.fuse_extend(a, 0.01) is None


# --- Pass-through wrappers (Color, PreviewModifier, ForceRender, Echo) ---


def test_color_fuse_extend_recurses_into_child():
    """Color is metadata-only: fuse_extend recurses into the child and
    re-wraps the extended result in Color."""
    from scadwright.ast.transforms import Color
    c = Cube(size=(5.0, 5.0, 10.0))
    colored = Color(c="red", child=c, alpha=1.0)
    a = get_node_anchors(colored)["top"]
    extended = colored.fuse_extend(a, 0.01)
    assert isinstance(extended, Color)
    assert extended.c == "red"
    inner = extended.child
    assert isinstance(inner, Cube)
    assert inner.size == pytest.approx((5.0, 5.0, 10.01))


def test_preview_modifier_fuse_extend_recurses():
    """PreviewModifier wraps a node with a sigil; metadata-only."""
    from scadwright.ast.transforms import PreviewModifier
    c = Cube(size=(5.0, 5.0, 10.0))
    wrapped = PreviewModifier(mode="highlight", child=c)
    a = get_node_anchors(wrapped)["top"]
    extended = wrapped.fuse_extend(a, 0.01)
    assert isinstance(extended, PreviewModifier)
    assert extended.mode == "highlight"
    assert extended.child.size == pytest.approx((5.0, 5.0, 10.01))


def test_force_render_fuse_extend_recurses():
    from scadwright.ast.transforms import ForceRender
    c = Cube(size=(5.0, 5.0, 10.0))
    wrapped = ForceRender(child=c, convexity=4)
    a = get_node_anchors(wrapped)["top"]
    extended = wrapped.fuse_extend(a, 0.01)
    assert isinstance(extended, ForceRender)
    assert extended.convexity == 4
    assert extended.child.size == pytest.approx((5.0, 5.0, 10.01))


def test_echo_fuse_extend_recurses_when_wrapping_child():
    """Echo wrapping a child is metadata; passes through."""
    from scadwright.ast.transforms import Echo
    c = Cube(size=(5.0, 5.0, 10.0))
    wrapped = Echo(values=(("msg", "hi"),), child=c)
    a = get_node_anchors(wrapped)["top"]
    extended = wrapped.fuse_extend(a, 0.01)
    assert isinstance(extended, Echo)
    assert extended.child.size == pytest.approx((5.0, 5.0, 10.01))


def test_echo_without_child_returns_none():
    """Bare Echo (no child) is a statement, not a shape wrapper. Its
    fuse_extend falls to the base-class None."""
    from scadwright.ast.transforms import Echo
    from scadwright.anchor import Anchor
    bare = Echo(values=(("x", 1),), child=None)
    # Any anchor; the call should return None unconditionally.
    a = Anchor(position=(0, 0, 0), normal=(0, 0, 1), kind="planar")
    assert bare.fuse_extend(a, 0.01) is None


def test_color_then_preview_modifier_chains_through():
    """Stacked metadata wrappers each recurse; final result has both
    wrappers preserved around the bumped child."""
    from scadwright.ast.transforms import Color, PreviewModifier
    c = Cube(size=(5.0, 5.0, 10.0))
    wrapped = Color(
        c="red",
        child=PreviewModifier(mode="highlight", child=c),
        alpha=1.0,
    )
    a = get_node_anchors(wrapped)["top"]
    extended = wrapped.fuse_extend(a, 0.01)
    assert isinstance(extended, Color)
    assert isinstance(extended.child, PreviewModifier)
    assert isinstance(extended.child.child, Cube)
    assert extended.child.child.size == pytest.approx((5.0, 5.0, 10.01))


# --- Geometry-mutating wrappers (Scale, Resize, MultMatrix) — not recursed ---


def test_scale_wrapped_fuse_extend_returns_none():
    """Scale doesn't implement fuse_extend (eps would scale with
    geometry). The default base-class None is returned."""
    from scadwright.ast.transforms import Scale
    c = Cube(size=(5.0, 5.0, 10.0))
    wrapped = Scale(factor=(2.0, 2.0, 2.0), child=c)
    a = get_node_anchors(wrapped)["top"]
    assert wrapped.fuse_extend(a, 0.01) is None


def test_resize_wrapped_fuse_extend_returns_none():
    from scadwright.ast.transforms import Resize
    c = Cube(size=(5.0, 5.0, 10.0))
    wrapped = Resize(new_size=(10.0, 10.0, 20.0), child=c)
    a = get_node_anchors(wrapped)["top"]
    assert wrapped.fuse_extend(a, 0.01) is None


# --- SphericalShell (Component): spherical wall extension via rebuild ---


def test_spherical_shell_fuse_extend_outer_wall_grows_od():
    from scadwright.shapes import SphericalShell
    s = SphericalShell(od=20.0, id=14.0)
    a = s.get_anchors()["outer_wall"]
    extended = s.fuse_extend(a, 0.01)
    assert isinstance(extended, SphericalShell)
    assert extended.od == pytest.approx(20.02)
    assert extended.id == pytest.approx(14.0)
    assert extended.thk == pytest.approx(3.01)


def test_spherical_shell_fuse_extend_inner_wall_shrinks_id():
    from scadwright.shapes import SphericalShell
    s = SphericalShell(od=20.0, id=14.0)
    a = s.get_anchors()["inner_wall"]
    extended = s.fuse_extend(a, 0.01)
    assert isinstance(extended, SphericalShell)
    assert extended.od == pytest.approx(20.0)
    assert extended.id == pytest.approx(13.98)
    assert extended.thk == pytest.approx(3.01)


def test_spherical_shell_fuse_extend_inner_to_zero_raises():
    from scadwright.errors import ValidationError
    from scadwright.shapes import SphericalShell
    s = SphericalShell(od=20.0, id=0.005)
    a = s.get_anchors()["inner_wall"]
    with pytest.raises(ValidationError, match="shrink past zero"):
        s.fuse_extend(a, 0.01)


def test_spherical_shell_fuse_extend_planar_anchor_returns_none():
    from scadwright.shapes import SphericalShell
    from scadwright.anchor import Anchor
    s = SphericalShell(od=20.0, id=14.0)
    planar = Anchor(position=(0, 0, 10), normal=(0, 0, 1), kind="planar")
    assert s.fuse_extend(planar, 0.01) is None
