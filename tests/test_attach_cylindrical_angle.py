"""Tests for ``Node.attach(angle=...)`` and ``at_radial=`` parametric placement
on cylindrical, conical, and rim-bearing planar anchors.

``attach()`` and ``add_text()`` both consume the same ``angle=`` and
``at_radial=`` kwargs for parametric angular and radial position on
cylindrical, conical, and rim anchor surfaces.
"""

import math

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder, sphere
from scadwright.shapes import Funnel, Tube


# --- Cylindrical anchor: angle rotates position and normal around the axis ---


def test_cylindrical_angle_zero_matches_unrotated():
    """``angle=0`` reproduces today's behavior (peg at +X meridian)."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    explicit = peg.attach(hub, on="outer_wall", angle=0)
    default = peg.attach(hub, on="outer_wall")
    # Both should land in the same place geometrically.
    assert bbox(explicit).center == pytest.approx(bbox(default).center)


def test_cylindrical_angle_90_lands_on_plus_y_meridian():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="outer_wall", angle=90)
    # Peg's bottom-center should land at (0, 10, 10) — the +Y meridian
    # at the wall's mid-height. Peg is 2x2x5, so its centroid is at
    # (0, 10, 12.5).
    cx, cy, cz = bbox(attached).center
    assert cx == pytest.approx(0.0, abs=1e-6)
    assert cy == pytest.approx(10.0)
    assert cz == pytest.approx(12.5)


def test_cylindrical_angle_alias_back_equals_90():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    via_alias = peg.attach(hub, on="outer_wall", angle="back")
    via_numeric = peg.attach(hub, on="outer_wall", angle=90)
    assert bbox(via_alias).center == pytest.approx(bbox(via_numeric).center)


def test_cylindrical_angle_negative_rotates_clockwise():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="outer_wall", angle=-90)
    cx, cy, cz = bbox(attached).center
    assert cx == pytest.approx(0.0, abs=1e-6)
    assert cy == pytest.approx(-10.0)


def test_cylindrical_angle_180_lands_on_minus_x():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="outer_wall", angle=180)
    cx, cy, cz = bbox(attached).center
    assert cx == pytest.approx(-10.0)
    assert cy == pytest.approx(0.0, abs=1e-6)


def test_cylindrical_angle_with_orient_composes():
    """``orient=True`` aligns self against the rotated normal — the peg
    lays sideways along the rotated direction."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="outer_wall", angle=90, orient=True)
    scad = emit_str(attached)
    # The orient path emits a rotate(); without it, only translate would appear.
    assert "rotate(" in scad


def test_cylindrical_angle_with_bridge_requires_orient():
    """``bridge=True`` on a cylindrical wall requires coaxial normals.
    Without orient=True (or manual alignment), the call is oblique and
    raises."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="coaxial normals"):
        peg.attach(hub, on="outer_wall", angle=90, bridge=True)


def test_cylindrical_angle_rejects_at_radial():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="at_radial= is not valid on a cylindrical"):
        peg.attach(hub, on="outer_wall", angle=30, at_radial=5)


# --- Conical anchor: slanted surface normal ---


def test_conical_angle_uses_slanted_normal_widening():
    """A cone widening upward has a slanted normal pointing outward
    and slightly down. ``orient=True`` should rotate the peg accordingly."""
    cone = cylinder(h=10, r1=2, r2=5)  # widens upward
    peg = cube([2, 2, 5])
    attached = peg.attach(cone, on="outer_wall", angle=0, orient=True)
    scad = emit_str(attached)
    # Slanted normal computed: slope=(3, 10), L=sqrt(109), normal=(10/L, 0, -3/L).
    # Peg's bottom normal (0, 0, -1) gets rotated to oppose this.
    assert "rotate(" in scad


def test_conical_angle_uses_slanted_normal_narrowing():
    """A cone narrowing upward has a slanted normal pointing outward
    and slightly up."""
    cone = cylinder(h=10, r1=5, r2=2)
    peg = cube([2, 2, 5])
    attached = peg.attach(cone, on="outer_wall", angle=0, orient=True)
    scad = emit_str(attached)
    assert "rotate(" in scad


def test_conical_angle_position_at_mid_wall_radius():
    """Cone outer_wall anchor sits at mid-wall radius. With angle=0,
    the peg's bottom should land at that radius on +X."""
    r1, r2, h = 2.0, 5.0, 10.0
    cone = cylinder(h=h, r1=r1, r2=r2)
    peg = cube([2, 2, 5])
    attached = peg.attach(cone, on="outer_wall", angle=0)
    cx = bbox(attached).center[0]
    # Mid-wall radius = (2 + 5) / 2 = 3.5. Peg's centroid x lands at that.
    assert cx == pytest.approx((r1 + r2) / 2.0, abs=0.01)


def test_conical_angle_rejects_at_radial():
    cone = cylinder(h=10, r1=2, r2=5)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="at_radial= is not valid on a conical"):
        peg.attach(cone, on="outer_wall", angle=30, at_radial=5)


# --- Cap anchor with rim_radius ---


def test_top_angle_zero_lands_on_rim_at_plus_x():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="top", angle=0)
    cx, cy, cz = bbox(attached).center
    # Peg's bottom-center at (10, 0, 20); centroid at (10, 0, 22.5).
    assert cx == pytest.approx(10.0)
    assert cy == pytest.approx(0.0, abs=1e-6)
    assert cz == pytest.approx(22.5)


def test_top_angle_90_lands_on_rim_at_plus_y():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="top", angle=90)
    cx, cy, cz = bbox(attached).center
    assert cx == pytest.approx(0.0, abs=1e-6)
    assert cy == pytest.approx(10.0)
    assert cz == pytest.approx(22.5)


def test_top_angle_with_at_radial_overrides_rim_radius():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="top", angle=0, at_radial=5)
    cx, cy, _ = bbox(attached).center
    assert cx == pytest.approx(5.0)
    assert cy == pytest.approx(0.0, abs=1e-6)


def test_top_angle_with_at_radial_zero_centers_on_cap():
    """``at_radial=0`` is the legitimate "center of cap" case — same as
    today's ``attach(hub, on="top")``."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    centered = peg.attach(hub, on="top", angle=0, at_radial=0)
    default = peg.attach(hub, on="top")
    assert bbox(centered).center == pytest.approx(bbox(default).center)


def test_bottom_angle_lands_on_bottom_rim():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="bottom", angle=0)
    cx, cy, cz = bbox(attached).center
    # Peg's bottom-center at the bottom rim points down — but the
    # default `using_anchor="bottom"` puts peg's bottom face on the contact point.
    # With no orient, peg sits with its bottom-face *on* z=0. centroid at z=2.5.
    # Wait — the bottom anchor's normal is -Z, peg's using_anchor="bottom" anchor
    # normal is also -Z, and without orient they don't oppose. Peg's
    # bottom-face goes to position (10, 0, 0); centroid at (10, 0, 2.5).
    assert cx == pytest.approx(10.0)
    assert cy == pytest.approx(0.0, abs=1e-6)
    assert cz == pytest.approx(2.5)


def test_top_angle_rejects_negative_at_radial():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="at_radial= must be non-negative"):
        peg.attach(hub, on="top", angle=0, at_radial=-1)


def test_top_angle_alias_string():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    via_alias = peg.attach(hub, on="top", angle="rside")
    via_numeric = peg.attach(hub, on="top", angle=0)
    assert bbox(via_alias).center == pytest.approx(bbox(via_numeric).center)


# --- Validation ---


def test_cube_top_does_not_support_angle():
    """A cube's ``top`` is planar without rim_radius — angle= is rejected."""
    box = cube([10, 10, 10])
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="not supported"):
        peg.attach(box, on="top", angle=30)


def test_at_radial_without_angle_raises():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="at_radial= requires angle="):
        peg.attach(hub, on="top", at_radial=5)


def test_invalid_angle_string_raises():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="angle must be one of"):
        peg.attach(hub, on="outer_wall", angle="bogus")


def test_angle_bool_raises():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="must be a string or numeric"):
        peg.attach(hub, on="outer_wall", angle=True)


# --- Cone slanted normal helper ---


def test_cone_slanted_normal_cylinder_returns_radial():
    from scadwright.ast.placement import _cone_slanted_normal
    nx, ny, nz = _cone_slanted_normal(5.0, 5.0, 10.0)
    assert nx == pytest.approx(1.0)
    assert ny == pytest.approx(0.0)
    assert nz == pytest.approx(0.0)


def test_cone_slanted_normal_widening_tilts_down():
    from scadwright.ast.placement import _cone_slanted_normal
    nx, ny, nz = _cone_slanted_normal(2.0, 5.0, 10.0)
    # slope = (3, 10), L = sqrt(109), normal = (10/L, 0, -3/L)
    L = math.sqrt(109)
    assert nx == pytest.approx(10 / L)
    assert nz == pytest.approx(-3 / L)


def test_cone_slanted_normal_narrowing_tilts_up():
    from scadwright.ast.placement import _cone_slanted_normal
    nx, ny, nz = _cone_slanted_normal(5.0, 2.0, 10.0)
    # slope = (-3, 10), L = sqrt(109), normal = (10/L, 0, 3/L)
    L = math.sqrt(109)
    assert nx == pytest.approx(10 / L)
    assert nz == pytest.approx(3 / L)


# --- Backward compatibility: existing attach() calls unaffected ---


def test_existing_attach_calls_unchanged():
    """Without angle= or radius=, attach() behaves exactly as before."""
    plate = cube([40, 40, 2])
    peg = cube([2, 2, 5])
    attached = peg.attach(plate)
    cz = bbox(attached).center[2]
    # Plate's top is z=2; peg's bottom-center anchor lands there;
    # peg's centroid at z=2 + 2.5 = 4.5.
    assert cz == pytest.approx(4.5)


def test_attach_with_at_kwarg_and_angle():
    """``at=`` (which face of self touches the anchor) composes with angle=."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    # Default using_anchor="bottom"; switch to using_anchor="top" — peg's top face on the wall.
    attached = peg.attach(hub, on="outer_wall", angle=0, using_anchor="top")
    cz = bbox(attached).center[2]
    # Peg's top-center anchor goes to (10, 0, 10); peg extends -z by full height.
    # Centroid at z=10 - 2.5 = 7.5.
    assert cz == pytest.approx(7.5)


# --- Composition with the cylinder's center= and outer transforms ---


def test_centered_cylinder_angle_lands_at_correct_z():
    """A centered cylinder (``center=True``) has z_mid=0 and z extents
    [-h/2, h/2]. ``outer_wall`` should anchor at mid-wall z=0 and
    ``angle=`` should rotate around the axis as usual."""
    hub = cylinder(h=20, r=10, center=True)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="outer_wall", angle=90)
    cx, cy, cz = bbox(attached).center
    # Anchor at world (0, 10, 0); peg centroid at (0, 10, 2.5).
    assert cx == pytest.approx(0.0, abs=1e-6)
    assert cy == pytest.approx(10.0)
    assert cz == pytest.approx(2.5)


def test_top_and_bottom_rim_angle_land_at_same_xy():
    """``angle=N`` on top rim and bottom rim of the same cylinder must
    land at the same (x, y) position. The user's mental model is that
    angle is measured CCW around the cylinder's central axis, so placing
    matching features (e.g. bolts on both faces) at the same angle
    produces features that line up vertically. This works because rim
    anchors carry the cylinder's central axis (not the cap's outward
    normal) in ``surface_params["axis"]``, so the rotation axis is the
    same for top and bottom."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    top = peg.attach(hub, on="top", angle=90)
    bottom = peg.attach(hub, on="bottom", angle=90)
    assert bbox(top).center[0] == pytest.approx(bbox(bottom).center[0], abs=1e-6)
    assert bbox(top).center[1] == pytest.approx(bbox(bottom).center[1], abs=1e-6)
    # And both should land at +Y, not -Y.
    assert bbox(top).center[1] == pytest.approx(10.0)


def test_rotated_cylinder_angle_composes_correctly():
    """Outer rotation transforms the cylindrical anchor's position,
    normal, AND surface_params["axis"] (via _transform_surface_params).
    ``_apply_attach_angle`` reads the transformed axis and rotates
    around it, so angular placement composes correctly with outer
    rotations of the parent cylinder."""
    # Rotate the cylinder 90° around +X: cylinder's local +Z (axis)
    # ends up along world -Y.
    hub = cylinder(h=20, r=10).rotate([90, 0, 0])
    peg = cube([2, 2, 5])
    # Cylinder-local +Y meridian (angle=90) at mid-wall = local (0, R, h/2).
    # After R_x(90): world (0, -h/2, R) = (0, -10, 10).
    attached = peg.attach(hub, on="outer_wall", angle=90)
    cx, cy, cz = bbox(attached).center
    # Peg's bottom-center anchor lands at (0, -10, 10). Without orient,
    # peg sits with its bottom face on that point, centroid at +Z half-peg
    # away. Peg height 5 → centroid at z=12.5.
    assert cx == pytest.approx(0.0, abs=1e-6)
    assert cy == pytest.approx(-10.0)
    assert cz == pytest.approx(12.5)


# --- Translation: angle= must rotate around the cylinder's actual axis line ---


def test_translated_cylinder_angle_rotates_around_actual_axis():
    """``angle=`` on a translated cylinder must rotate around the
    cylinder's axis line (which has moved with the host), not around
    the world-origin axis-direction. Regression for the prior bug
    where ``rotation.apply_point(anchor.position)`` rotated relative
    to the world origin and produced wrong xy positions when the host
    wasn't centered."""
    hub = cylinder(h=20, r=10).right(50)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="outer_wall", angle=90)
    cx, cy, cz = bbox(attached).center
    # +Y meridian on the translated hub is at world (50, 10, mid-wall).
    assert cx == pytest.approx(50.0)
    assert cy == pytest.approx(10.0)
    assert cz == pytest.approx(12.5)


# --- at_z= : axial offset along the cylinder's central axis ---


def test_cylindrical_at_z_shifts_along_axis():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="outer_wall", at_z=5)
    cx, cy, cz = bbox(attached).center
    # mid-wall = z=10; +5 axial = z=15; peg centroid at z=15+2.5=17.5.
    assert cx == pytest.approx(10.0)
    assert cy == pytest.approx(0.0, abs=1e-6)
    assert cz == pytest.approx(17.5)


def test_cylindrical_at_z_negative_shifts_below_midwall():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="outer_wall", at_z=-3)
    cx, cy, cz = bbox(attached).center
    # mid-wall z=10; -3 axial → z=7; peg centroid at 7+2.5=9.5.
    assert cz == pytest.approx(9.5)


def test_cylindrical_at_z_zero_matches_default():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    explicit = peg.attach(hub, on="outer_wall", at_z=0)
    default = peg.attach(hub, on="outer_wall")
    assert bbox(explicit).center == pytest.approx(bbox(default).center)


def test_at_z_composes_with_angle():
    """``angle=`` and ``at_z=`` together place at the requested meridian
    AND axial offset on the same wall."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="outer_wall", angle=90, at_z=5)
    cx, cy, cz = bbox(attached).center
    # +Y meridian (angle=90), z=mid+5=15, peg centroid z=17.5.
    assert cx == pytest.approx(0.0, abs=1e-6)
    assert cy == pytest.approx(10.0)
    assert cz == pytest.approx(17.5)


def test_at_z_on_translated_cylinder_follows_axis_line():
    """``at_z=`` shifts along the cylinder's axis line, not world +Z, so
    the translation correctly tracks the host's position."""
    hub = cylinder(h=20, r=10).right(50)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="outer_wall", at_z=5)
    cx, cy, cz = bbox(attached).center
    # mid-wall is z=10, +5 axial → z=15, peg centroid z=17.5.
    # +X meridian on translated hub is world x=60, y=0.
    assert cx == pytest.approx(60.0)
    assert cy == pytest.approx(0.0, abs=1e-6)
    assert cz == pytest.approx(17.5)


def test_at_z_on_rotated_cylinder_follows_rotated_axis():
    """For a cylinder rotated 90° around +X, the central axis is now
    world -Y. ``at_z=5`` should shift along that direction."""
    hub = cylinder(h=20, r=10).rotate([90, 0, 0])
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="outer_wall", at_z=5)
    cx, cy, cz = bbox(attached).center
    # Local: +X-meridian mid-wall = (10, 0, 10). After R_x(90): (10, -10, 0).
    # Axis direction after rotation: (0, -1, 0). +5 along axis → (10, -15, 0).
    # Peg centroid offsets in +z by half-peg (no orient), so z=2.5.
    assert cx == pytest.approx(10.0)
    assert cy == pytest.approx(-15.0)
    assert cz == pytest.approx(2.5)


def test_conical_at_z_adjusts_radius_to_stay_on_surface():
    """For a cone, axial offset moves to a different radius. The new
    anchor stays on the cone wall (not floating off-surface)."""
    cone = cylinder(h=20, r1=10, r2=2)
    peg = cube([2, 2, 5])
    attached = peg.attach(cone, on="outer_wall", at_z=5)
    cx, cy, cz = bbox(attached).center
    # slope = (2 - 10) / 20 = -0.4. r_mid = 6. At at_z=5: r = 6 + (-0.4)*5 = 4.
    # z = mid (10) + 5 = 15. Peg centroid z = 17.5.
    assert cx == pytest.approx(4.0)
    assert cy == pytest.approx(0.0, abs=1e-6)
    assert cz == pytest.approx(17.5)


def test_conical_inner_wall_at_z_uses_correct_outward_direction():
    """Inner walls have anchor.normal pointing toward the axis. The
    radial adjustment for at_z= must use the OUTWARD-from-axis direction
    (-anchor.normal for inner walls), so an inner cone widening upward
    correctly increases the inner radius at a higher at_z."""
    f = Funnel(h=20, bot_id=20, top_id=10, thk=2)
    peg = cube([2, 2, 5])
    attached = peg.attach(f, on="inner_wall", at_z=5)
    cx, cy, cz = bbox(attached).center
    # Funnel inner: bot_id/2=10, top_id/2=5. Inner narrows upward.
    # r_mid_inner = (10 + 5)/2 = 7.5. slope = (5 - 10)/20 = -0.25.
    # At at_z=5: inner radius = 7.5 + (-0.25)*5 = 6.25.
    assert cx == pytest.approx(6.25)
    assert cy == pytest.approx(0.0, abs=1e-6)
    assert cz == pytest.approx(17.5)


def test_at_z_on_rim_anchor_raises():
    """Rim anchors don't have a meaningful axial-offset direction; the
    radial offset on a rim is ``radius=`` instead."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError) as exc:
        peg.attach(hub, on="top", at_z=5)
    msg = str(exc.value)
    assert "at_z" in msg
    assert "rim" in msg.lower() or "radius" in msg


def test_at_z_on_cube_face_raises():
    """Plain bbox-derived planar anchor has no surface axis; reject
    at_z= clearly."""
    box = cube([10, 10, 10])
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError) as exc:
        peg.attach(box, on="rside", at_z=5)
    assert "at_z" in str(exc.value)


def test_at_z_past_cone_tip_raises():
    """For a steep cone, an at_z that drives the local radius non-positive
    is a clear user error — raise rather than silently producing junk."""
    cone = cylinder(h=20, r1=10, r2=2)
    peg = cube([2, 2, 5])
    # Slope = -0.4; r_mid = 6. To make local radius <= 0, at_z >= 15.
    with pytest.raises(ValidationError) as exc:
        peg.attach(cone, on="outer_wall", at_z=20)
    msg = str(exc.value)
    assert "cone tip" in msg.lower() or "radius" in msg


def test_tube_at_z_works_on_outer_wall():
    """``at_z=`` works on Tube and Funnel surface-aware anchors, not
    just the raw cylinder() primitive."""
    tube = Tube(h=20, od=20, thk=2)
    peg = cube([2, 2, 5])
    attached = peg.attach(tube, on="outer_wall", at_z=5)
    cx, cy, cz = bbox(attached).center
    # Tube outer wall: mid-wall z=10, radius=10. at_z=5 → z=15.
    assert cx == pytest.approx(10.0)
    assert cz == pytest.approx(17.5)


# --- Cone slanted normal: orient=True with at_z= alone lays flush ---


def test_cone_at_z_alone_uses_slanted_normal_for_orient():
    """``orient=True`` with just ``at_z=`` (no ``angle=``) on a cone wall
    should lay the part flush against the slanted surface — same as
    ``angle=0, at_z=N``. Regression for the previous behavior where
    ``_apply_attach_at_z`` left the radial-reference normal in place,
    making the orient direction differ between the two equivalent
    spellings."""
    cone = cylinder(h=20, r1=10, r2=2)  # narrowing-up
    peg = cube([2, 2, 5])
    via_at_z_only = peg.attach(cone, on="outer_wall", at_z=5, orient=True)
    via_angle_zero = peg.attach(cone, on="outer_wall", angle=0, at_z=5, orient=True)
    # The two spellings must produce identical world positions.
    assert bbox(via_at_z_only).center == pytest.approx(
        bbox(via_angle_zero).center, abs=1e-6,
    )


def test_funnel_inner_wall_orient_uses_inner_slanted_normal():
    """Inner cones lay parts flush AGAINST the inner surface (normal
    pointing toward the axis), not against an out-of-bore plane. With
    ``inner=`` flag plumbed through ``_cone_slanted_normal``, a Funnel
    inner_wall + orient=True puts the peg with its bottom face on the
    inner cone surface; without the flag, the peg ended up oriented
    the other way (perpendicular to a normal pointing the wrong way)."""
    f = Funnel(h=20, bot_id=20, top_id=10, thk=2)  # inner narrows upward
    peg = cube([4, 4, 1])
    p = peg.attach(f, on="inner_wall", angle=0, orient=True)
    # The peg should land with its bottom-face center on the inner wall
    # at the +X meridian, mid-wall: ( (bot_id/2 + top_id/2)/2, 0, h/2 ) =
    # ( (10 + 5)/2, 0, 10 ) = (7.5, 0, 10). Centroid offsets along the
    # (rotated) +Z direction by half-thickness (0.5). The exact
    # centroid depends on the slanted-normal direction, but the bbox
    # center's x must remain within (0, bot_id/2) — i.e. INSIDE the
    # bore. If the flag had been wrong, x would be outside the bore.
    cx, cy, cz = bbox(p).center
    assert 0.0 < cx < 10.0


# --- Rim meridian_zero: rotation around the cylinder's own axis follows host ---


def test_rotated_host_rim_angle_follows_local_meridian():
    """When the host is rotated around its own axis (R_z(45°) here), the
    rim's +X-meridian direction rotates with it. ``attach(top, angle=0)``
    must land at the rotated +X meridian, not at world +X.

    This is the rim analog of the wall behavior, which has always
    worked because the wall anchor's normal is the +X-meridian direction
    that transforms naturally with the host. The rim now stores the
    same intent in ``surface_params["meridian_zero"]``."""
    hub = cylinder(h=20, r=10).rotate([0, 0, 45])
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="top", angle=0)
    cx, cy, cz = bbox(attached).center
    # Rotated +X meridian on the top rim is at world (cos45*r, sin45*r, h).
    assert cx == pytest.approx(10.0 * math.cos(math.radians(45)))
    assert cy == pytest.approx(10.0 * math.sin(math.radians(45)))
    assert cz == pytest.approx(22.5)  # cap z=20, peg centroid z=22.5


def test_rotated_host_rim_angle_consistent_with_wall():
    """For a host rotated around its own axis, ``attach(top, angle=N)``
    and ``attach(outer_wall, angle=N)`` should agree on the angular
    position (same xy direction, just different z). Regression for the
    pre-fix asymmetry where wall used the transformed meridian-zero
    direction (anchor.normal) and rim used hardcoded world +X."""
    hub = cylinder(h=20, r=10).rotate([0, 0, 30])
    peg = cube([2, 2, 5])
    rim = peg.attach(hub, on="top", angle=45)
    wall = peg.attach(hub, on="outer_wall", angle=45)
    rim_xy_dir = (bbox(rim).center[0], bbox(rim).center[1])
    wall_xy_dir = (bbox(wall).center[0], bbox(wall).center[1])
    # Both should be at the same angular direction from the cylinder axis.
    # Their (x, y) magnitudes are both 10 (the radius), and the angles
    # should match.
    rim_angle = math.atan2(rim_xy_dir[1], rim_xy_dir[0])
    wall_angle = math.atan2(wall_xy_dir[1], wall_xy_dir[0])
    assert rim_angle == pytest.approx(wall_angle, abs=1e-6)
