"""Tests for ``Node.attach(angle=...)`` and ``radius=`` parametric placement
on cylindrical, conical, and rim-bearing planar anchors.

Closes the asymmetry between ``add_text(meridian=...)`` and the generic
``attach()`` flow — both can now consume parametric angular position
on the same anchor surfaces.
"""

import math

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder, sphere


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


def test_cylindrical_angle_with_fuse_offsets_along_rotated_normal():
    """``fuse=True`` pushes self into the contact face along the rotated
    anchor normal (radial direction at the rotated angle)."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    no_fuse = peg.attach(hub, on="outer_wall", angle=90)
    with_fuse = peg.attach(hub, on="outer_wall", angle=90, fuse=True)
    # Fuse pushes peg radially inward by eps. With angle=90, that's -y.
    assert bbox(with_fuse).center[1] < bbox(no_fuse).center[1]


def test_cylindrical_angle_rejects_radius():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="radius= is not valid on a cylindrical"):
        peg.attach(hub, on="outer_wall", angle=30, radius=5)


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


def test_conical_angle_rejects_radius():
    cone = cylinder(h=10, r1=2, r2=5)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="radius= is not valid on a conical"):
        peg.attach(cone, on="outer_wall", angle=30, radius=5)


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


def test_top_angle_with_radius_overrides_rim_radius():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="top", angle=0, radius=5)
    cx, cy, _ = bbox(attached).center
    assert cx == pytest.approx(5.0)
    assert cy == pytest.approx(0.0, abs=1e-6)


def test_top_angle_with_radius_zero_centers_on_cap():
    """``radius=0`` is the legitimate "center of cap" case — same as
    today's ``attach(hub, on="top")``."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    centered = peg.attach(hub, on="top", angle=0, radius=0)
    default = peg.attach(hub, on="top")
    assert bbox(centered).center == pytest.approx(bbox(default).center)


def test_bottom_angle_lands_on_bottom_rim():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    attached = peg.attach(hub, on="bottom", angle=0)
    cx, cy, cz = bbox(attached).center
    # Peg's bottom-center at the bottom rim points down — but the
    # default `at="bottom"` puts peg's bottom face on the contact point.
    # With no orient, peg sits with its bottom-face *on* z=0. centroid at z=2.5.
    # Wait — the bottom anchor's normal is -Z, peg's at="bottom" anchor
    # normal is also -Z, and without orient they don't oppose. Peg's
    # bottom-face goes to position (10, 0, 0); centroid at (10, 0, 2.5).
    assert cx == pytest.approx(10.0)
    assert cy == pytest.approx(0.0, abs=1e-6)
    assert cz == pytest.approx(2.5)


def test_top_angle_rejects_negative_radius():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="radius= must be non-negative"):
        peg.attach(hub, on="top", angle=0, radius=-1)


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


def test_radius_without_angle_raises():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="radius= requires angle="):
        peg.attach(hub, on="top", radius=5)


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
    # Default at="bottom"; switch to at="top" — peg's top face on the wall.
    attached = peg.attach(hub, on="outer_wall", angle=0, at="top")
    cz = bbox(attached).center[2]
    # Peg's top-center anchor goes to (10, 0, 10); peg extends -z by full height.
    # Centroid at z=10 - 2.5 = 7.5.
    assert cz == pytest.approx(7.5)
