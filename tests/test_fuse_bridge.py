"""Tests for Phase 3 curved-surface fuse via the bridge mechanism.

Bridge construction: when attach(fuse=True) targets a convex-outer
curved on-anchor (cylindrical/conical/spherical), the framework builds
a piece that fills the inscription gap between peg's flat near-face
and host's curved surface. Bridge = peg_xsec extruded into host
direction by analytical inscription depth, differenced with host.
"""

import math

import pytest

from scadwright import bbox
from scadwright.ast.csg import Difference, Union
from scadwright.boolops import fuse, union
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder, sphere
from scadwright.shapes import Tube


# --- Bridge construction: cylinder OD ---


def test_bridge_on_cylinder_od_returns_union_with_difference():
    """attach(fuse=True) on cylinder outer_wall with orient=True dispatches
    through the bridge mechanism. Result tree: union(placed_peg, bridge)
    where bridge is a Difference (prism - host)."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    result = peg.attach(hub, on="outer_wall", angle=0, orient=True, fuse=True)
    assert isinstance(result, Union)
    assert any(isinstance(c, Difference) for c in result.children)


def test_bridge_on_cylinder_od_places_peg_tangent_then_fills_gap():
    """With orient=True and fuse=True on cylinder OD, the bridge dispatch
    places the peg sitting tangent to the cylinder wall (peg's at-anchor
    on cylinder surface, peg's body extending radially outward), and
    fills the small inscription gap with bridge material. Verify peg's
    far face is at cylinder_radius + peg_axial_extent."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])  # 5 mm long, 2x2 cross-section
    result = peg.attach(hub, on="outer_wall", angle=0, orient=True, fuse=True)
    bb = bbox(result)
    # Peg's far +X face should be at world x = 10 (cylinder OD) + 5 (peg
    # axial extent along normal) = 15.
    assert bb.max[0] == pytest.approx(15.0, abs=1e-3)
    # Peg's near +X face is at x=10 (tangent to cylinder); bridge sits
    # at x slightly less than 10 (extending eps into peg material on the
    # peg side, and into the inscription gap on the host side).
    assert bb.min[0] < 10.0  # bridge dips into the inscription gap region


# --- Bridge construction: sphere outer ---


def test_bridge_on_sphere_outer_returns_union_with_difference():
    """Sphere bbox-derived anchors are kind='spherical' (Phase 3 prereq).
    Attaching to a sphere with fuse=True builds a bridge."""
    ball = sphere(r=10)
    peg = cube([2, 2, 5])
    result = peg.attach(ball, on="top", orient=True, fuse=True)
    assert isinstance(result, Union)
    assert any(isinstance(c, Difference) for c in result.children)


# --- Bridge construction: cone outer wall ---


def test_bridge_on_cone_outer_wall():
    """Conical anchor has r1, r2 in surface_params. Bridge uses the
    larger as a conservative radius."""
    cone = cylinder(h=10, r1=5, r2=10)
    peg = cube([2, 2, 5])
    result = peg.attach(cone, on="outer_wall", angle=0, orient=True, fuse=True)
    assert isinstance(result, Union)
    assert any(isinstance(c, Difference) for c in result.children)


# --- Concave inner: bridge bypassed ---


def test_concave_inner_wall_bypasses_bridge():
    """Concave inner walls (Tube.inner_wall has surface_params['inner']=True)
    naturally inscribe peg corners into wall material. Bridge is skipped;
    the call falls through to legacy shift, no Difference in the tree."""
    pipe = Tube(od=20, id=10, h=20)
    peg = cube([2, 2, 5])
    result = peg.attach(pipe, on="inner_wall", angle=0, orient=True, fuse=True)
    # Result is a Translate (legacy shift), not a Union with Difference.
    from scadwright.ast.transforms import Translate as _Translate
    assert isinstance(result, _Translate)


# --- Oblique attach raises ---


def test_oblique_attach_on_curved_host_raises():
    """attach(fuse=True) on a curved host without coaxial normals raises.
    Without orient=True, peg's bottom (normal -Z) doesn't oppose
    cylinder's outer_wall normal (+X at angle=0)."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="coaxial normals"):
        peg.attach(hub, on="outer_wall", angle=0, fuse=True)


def test_fuse_function_bridges_when_a_is_curved_host():
    """fuse() is symmetric: bridges whether the curved side is a or b.
    Here a (cylinder) is curved, b (peg) is planar — bridge fills the
    inscription gap on a's outer wall."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5]).up(50)  # somewhere in space; bottom face faces -Z
    # Configure anchors so peg.bottom (-Z) opposes hub.bottom (-Z)... no,
    # use a coaxial pair: peg.bottom anti-parallel hub.top.
    # Reverse: a=peg-rotated-onto-hub, b=hub. That uses b_curved branch.
    # For a_curved branch, swap roles: a is hub (curved), b is peg.
    # Need coaxial. Use hub.top (+Z, planar rim) as a's anchor — but
    # planar isn't curved. Use outer_wall instead.
    # Simplest: pre-orient the peg so its at-anchor normal opposes
    # hub.outer_wall normal. cube.bottom normal is -Z; if we rotate peg
    # 90° around -Y, peg.bottom normal becomes -X, anti-parallel to
    # hub.outer_wall normal +X. But fuse() doesn't auto-orient. Use a
    # peg whose normal already opposes by construction.
    # Use peg.lside (normal -X) on hub.outer_wall (normal +X). Coaxial.
    result = fuse(hub, peg, at="outer_wall", on="lside")
    # a=hub is curved (outer_wall, kind=cylindrical), b=peg is planar
    # (lside). Symmetric branch fires.
    from scadwright.ast.csg import Difference
    assert any(isinstance(c, Difference) for c in result.children)


def test_oblique_fuse_on_curved_host_raises():
    """The standalone fuse() function applies the same coaxial check
    when b is the curved host."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="coaxial normals"):
        # Without orient/manual rotation, peg normal doesn't oppose host.
        fuse(peg, hub, on="outer_wall", at="bottom")


# --- Inscription depth math ---


def test_inscription_depth_formula():
    """The bridge's depth equals R - sqrt(R² - r_max²) where R is host
    radius and r_max is peg's max radial extent in the tangent plane."""
    from scadwright.ast._fuse_bridge import _inscription_depth, _peg_max_radial_extent
    from scadwright.anchor import Anchor

    # Centered 2x2x5 peg so the at-anchor sits at the cube's bottom
    # face center (0,0,0) and corner extents in the tangent (XY) plane
    # are (±1, ±1) → max radial = sqrt(2).
    peg = cube([2, 2, 5], center="xy")
    peg_anchor = Anchor(
        position=(0.0, 0.0, 0.0),
        normal=(0.0, 0.0, -1.0),
        kind="planar",
    )
    host_anchor = Anchor(
        position=(0.0, 0.0, 0.0),
        normal=(1.0, 0.0, 0.0),
        kind="cylindrical",
        surface_params=(("axis", (0.0, 0.0, 1.0)), ("radius", 10.0)),
    )
    r = _peg_max_radial_extent(peg, peg_anchor)
    assert r == pytest.approx(math.sqrt(2))
    d = _inscription_depth(host_anchor, r)
    expected = 10.0 - math.sqrt(100.0 - 2.0)
    assert d == pytest.approx(expected, abs=1e-9)


def test_inscription_depth_fits_huge_peg():
    """If peg is bigger than host radius, inscription_depth caps at the
    radius. Doesn't try to compute sqrt of negative."""
    from scadwright.ast._fuse_bridge import _inscription_depth
    from scadwright.anchor import Anchor

    host_anchor = Anchor(
        position=(0.0, 0.0, 0.0),
        normal=(1.0, 0.0, 0.0),
        kind="cylindrical",
        surface_params=(("radius", 5.0),),
    )
    d = _inscription_depth(host_anchor, peg_max_radial=20.0)
    assert d == 5.0


# --- Coaxial normal check ---


def test_coaxial_normals_within_tolerance():
    from scadwright.ast._fuse_bridge import coaxial_normals
    assert coaxial_normals((0, 0, 1), (0, 0, -1))
    assert coaxial_normals((1, 0, 0), (-1, 0, 0))
    assert not coaxial_normals((1, 0, 0), (0, 1, 0))
    assert not coaxial_normals((1, 0, 0), (1, 0, 0))  # parallel, not anti


def test_coaxial_normals_floating_point_tolerance():
    """Tiny floating-point drift around angle=90° rotations shouldn't
    falsely flag normals as oblique."""
    from scadwright.ast._fuse_bridge import coaxial_normals
    eps_drift = 1e-15
    assert coaxial_normals((0, 0, 1.0), (eps_drift, eps_drift, -1.0))


# --- Sphere anchor kind ---


def test_sphere_bbox_anchors_are_spherical():
    """Phase 3 prereq: Sphere's bbox-derived anchors carry kind='spherical'
    so curved-host fuse dispatches via bridge instead of trying the planar
    path (which Phase 2 used to raise on)."""
    from scadwright.anchor import get_node_anchors
    s = sphere(r=7)
    anchors = get_node_anchors(s)
    for name in ("top", "bottom", "lside", "rside", "front", "back"):
        assert anchors[name].kind == "spherical", f"{name} anchor"
        assert anchors[name].surface_param("radius") == 7.0


# --- disable_eps_fuse() opt-out applies to bridge too ---


def test_disable_eps_fuse_skips_bridge():
    """The scope-wide disable_eps_fuse() opt-out skips all fuse machinery,
    including the new bridge mechanism. Result is exact-contact union with
    the peg tangent and no bridge."""
    from scadwright.api.fuse_mode import disable_eps_fuse
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with disable_eps_fuse():
        result = peg.attach(hub, on="outer_wall", angle=0, orient=True, fuse=True)
    # No bridge: result is a single Translate (placed peg).
    from scadwright.ast.transforms import Translate as _Translate
    assert isinstance(result, _Translate)
