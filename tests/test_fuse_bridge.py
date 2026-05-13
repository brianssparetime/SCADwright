"""Tests for curved-surface attach via the bridge mechanism.

When attach targets a convex-outer curved on-anchor (cylindrical /
conical / spherical), passing bridge=True builds a structural piece
that fills the inscription gap between peg's flat near-face and the
host's curved surface. Bridge = peg_xsec extruded into host direction
by analytical inscription depth, differenced with host. The peg-side
eps overlap is gated on fuse=True (default False on attach; default
True on boolops.fuse).
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
    """attach(bridge=True) on cylinder outer_wall with orient=True returns
    union(placed_peg, bridge) where bridge is a Difference (prism - host)."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    result = peg.attach(hub, on="outer_wall", angle=0, orient=True, bridge=True)
    assert isinstance(result, Union)
    assert any(isinstance(c, Difference) for c in result.children)


def test_bridge_on_cylinder_od_places_peg_tangent_then_fills_gap():
    """With orient=True and bridge=True+fuse=True on cylinder OD, the peg
    sits tangent and the bridge fills the inscription gap and overlaps
    the peg by eps. Verify peg's far face is at cylinder_radius + peg
    axial extent."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])  # 5 mm long, 2x2 cross-section
    result = peg.attach(
        hub, on="outer_wall", angle=0, orient=True, bridge=True, fuse=True,
    )
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
    """Sphere bbox-derived anchors are kind='spherical', so attaching
    to a sphere with bridge=True builds the structural fill."""
    ball = sphere(r=10)
    peg = cube([2, 2, 5])
    result = peg.attach(ball, on="top", orient=True, bridge=True)
    assert isinstance(result, Union)
    assert any(isinstance(c, Difference) for c in result.children)


# --- Bridge construction: cone outer wall ---


def test_bridge_on_cone_outer_wall():
    """Conical anchor has r1, r2 in surface_params. Bridge uses the
    larger as a conservative radius."""
    cone = cylinder(h=10, r1=5, r2=10)
    peg = cube([2, 2, 5])
    result = peg.attach(cone, on="outer_wall", angle=0, orient=True, bridge=True)
    assert isinstance(result, Union)
    assert any(isinstance(c, Difference) for c in result.children)


# --- bridge=True alone (no fuse=) produces flush bridge, no -eps slice ---


def _find_prism_extrude_height(node):
    """Walk a bridge result (Union of placed_peg + Difference(prism, host))
    to find the LinearExtrude height inside the prism. That height equals
    depth_total when eps_overlap is false, depth_total + eps when true.
    """
    from scadwright.ast.extrude import LinearExtrude

    found = []

    def walk(n):
        if isinstance(n, LinearExtrude):
            found.append(n.height)
            return
        for attr in ("child", "children"):
            v = getattr(n, attr, None)
            if v is None:
                continue
            if isinstance(v, tuple):
                for c in v:
                    walk(c)
            else:
                walk(v)

    walk(node)
    return found[0] if found else None


def test_bridge_alone_omits_peg_side_eps_slice():
    """bridge=True without fuse=True extrudes the cross-section to
    depth_total (flush peg side). bridge=True with fuse=True extrudes
    to depth_total + eps (peg-side overlap)."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    flush = peg.attach(hub, on="outer_wall", angle=0, orient=True, bridge=True)
    overlapped = peg.attach(
        hub, on="outer_wall", angle=0, orient=True, bridge=True, fuse=True,
    )
    h_flush = _find_prism_extrude_height(flush)
    h_overlap = _find_prism_extrude_height(overlapped)
    assert h_flush is not None and h_overlap is not None
    # Overlap adds exactly one eps (default 0.01) to the prism height.
    assert h_overlap - h_flush == pytest.approx(0.01, abs=1e-9)


# --- fuse=True alone on curved host: raise ---


def test_fuse_true_on_curved_host_raises_with_bridge_hint():
    """fuse=True alone on a convex-outer curved host no longer auto-bridges;
    it raises and points at bridge=True."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="bridge=True"):
        peg.attach(hub, on="outer_wall", angle=0, orient=True, fuse=True)


# --- Concave inner: bridge not applicable ---


def test_concave_inner_wall_with_bridge_raises():
    """bridge=True on a concave inner wall raises — the bridge is for
    convex-outer hosts."""
    pipe = Tube(od=20, id=10, h=20)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="inner"):
        peg.attach(pipe, on="inner_wall", angle=0, orient=True, bridge=True)


def test_concave_inner_wall_with_fuse_raises():
    """fuse=True on a concave inner wall raises (no planar contact, no
    bridge case). bond='shift' is the recovery path."""
    pipe = Tube(od=20, id=10, h=20)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="no applicable eps mechanism"):
        peg.attach(pipe, on="inner_wall", angle=0, orient=True, fuse=True)


def test_concave_inner_wall_with_bond_shift():
    """bond='shift' is the recovery path for concave inner walls."""
    from scadwright.ast.transforms import Translate as _Translate

    pipe = Tube(od=20, id=10, h=20)
    peg = cube([2, 2, 5])
    result = peg.attach(
        pipe, on="inner_wall", angle=0, orient=True, bond="shift",
    )
    assert isinstance(result, _Translate)


# --- Coaxial check ---


def test_bridge_without_coaxial_normals_raises():
    """bridge=True without coaxial peg/host normals raises. Without
    orient=True, peg's bottom (normal -Z) doesn't oppose cylinder's
    outer_wall normal (+X at angle=0)."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="coaxial normals"):
        peg.attach(hub, on="outer_wall", angle=0, bridge=True)


def test_fuse_function_bridges_when_a_is_curved_host():
    """fuse() is symmetric: bridges whether the curved side is a or b.
    Here a (cylinder) is curved, b (peg) is planar — bridge fills the
    inscription gap on a's outer wall. Use coaxial anchors so no orient
    is needed: peg.lside (normal -X) opposes hub.outer_wall (normal +X)."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5]).up(50)
    result = fuse(
        hub, peg, using_anchor="outer_wall", on="lside", bridge=True,
    )
    assert any(isinstance(c, Difference) for c in result.children)


def test_oblique_fuse_function_on_curved_host_raises():
    """fuse(..., bridge=True) applies the coaxial check too."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="coaxial normals"):
        fuse(peg, hub, on="outer_wall", using_anchor="bottom", bridge=True)


# --- Inscription depth math ---


def test_inscription_depth_formula():
    """The bridge's depth equals R - sqrt(R² - r_max²) where R is host
    radius and r_max is peg's max radial extent in the tangent plane."""
    from scadwright.ast._fuse_bridge import _inscription_depth, _peg_max_radial_extent
    from scadwright.anchor import Anchor

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
        axis=(0.0, 0.0, 1.0),
        radius=10.0,
        length=20.0,
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
        axis=(0.0, 0.0, 1.0),
        radius=5.0,
        length=20.0,
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
    """Sphere's bbox-derived anchors carry kind='spherical' so the bridge
    dispatcher accepts them. (Planar cross-section would fail on a bbox-
    face tangent point.)"""
    from scadwright.anchor import get_node_anchors
    s = sphere(r=7)
    anchors = get_node_anchors(s)
    for name in ("top", "bottom", "lside", "rside", "front", "back"):
        assert anchors[name].kind == "spherical", f"{name} anchor"
        assert anchors[name].radius == 7.0


# --- disable_eps_fuse(): bridge persists, eps slice drops ---


def test_disable_eps_fuse_keeps_bridge_drops_overlap():
    """disable_eps_fuse() suppresses eps geometry — fuse=True collapses
    to False inside the scope, so a bridge built there is flush (no
    peg-side -eps slice). The bridge structural fill itself persists.
    """
    from scadwright.api.fuse_mode import disable_eps_fuse
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with disable_eps_fuse():
        result_inside = peg.attach(
            hub, on="outer_wall", angle=0, orient=True, bridge=True, fuse=True,
        )
    # Bridge geometry still present.
    assert isinstance(result_inside, Union)
    assert any(isinstance(c, Difference) for c in result_inside.children)
    # Prism height equals depth_total (no +eps).
    result_outside = peg.attach(
        hub, on="outer_wall", angle=0, orient=True, bridge=True, fuse=True,
    )
    h_inside = _find_prism_extrude_height(result_inside)
    h_outside = _find_prism_extrude_height(result_outside)
    assert h_outside - h_inside == pytest.approx(0.01, abs=1e-9)
