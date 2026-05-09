"""Tests for the ``bond=`` kwarg on ``Node.attach`` and ``boolops.fuse``.

Phase A: bond= is additive. Existing ``fuse=True`` behavior unchanged;
explicit ``bond="overlap"`` / ``bond="bridge"`` / ``bond="shift"`` give
strict per-bond dispatch with clear errors for misuse.
"""

import pytest

from scadwright import disable_eps_fuse
from scadwright.ast.csg import Union
from scadwright.ast.transforms import Translate
from scadwright.boolops import fuse
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder, sphere


# --- argument validation ---


def test_invalid_bond_value_raises():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with pytest.raises(ValidationError, match="bond= must be one of"):
        peg.attach(plate, bond="bogus")


def test_bond_with_fuse_false_raises():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with pytest.raises(ValidationError, match="contradicts bond"):
        peg.attach(plate, fuse=False, bond="overlap")


def test_bond_implies_fuse_true():
    """bond=... should produce eps-modified geometry even without fuse=True."""
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    # bond="shift" without fuse=True should still apply the eps shift.
    placed_with_bond = peg.attach(plate, bond="shift")
    placed_with_fuse = peg.attach(plate, fuse=True, bond="shift")
    assert placed_with_bond.v == pytest.approx(placed_with_fuse.v)
    # And not equivalent to fuse=False (which would give exact contact).
    placed_exact = peg.attach(plate, fuse=False)
    assert placed_with_bond.v != placed_exact.v


# --- bond="overlap" ---


def test_bond_overlap_planar_success():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    placed = peg.attach(plate, bond="overlap")
    # Result should be a Translate wrapping (extended cube + shift to top).
    assert isinstance(placed, Translate)
    # Should NOT contain a Union (parametric Tier 1 path = no slab).
    def has_union(node, depth=10):
        if depth == 0:
            return False
        if isinstance(node, Union):
            return True
        for attr in ("child", "children"):
            v = getattr(node, attr, None)
            if v is None:
                continue
            if isinstance(v, tuple):
                if any(has_union(c, depth - 1) for c in v):
                    return True
            elif has_union(v, depth - 1):
                return True
        return False
    assert not has_union(placed)


def test_bond_overlap_on_curved_host_raises():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="bond='overlap'.*planar"):
        peg.attach(hub, on="outer_wall", bond="overlap")


def test_bond_overlap_error_points_to_bridge():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="bond='bridge'"):
        peg.attach(hub, on="outer_wall", bond="overlap")


# --- bond="bridge" ---


def test_bond_bridge_on_cylinder_wall_with_orient():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    placed = peg.attach(hub, on="outer_wall", angle=0, orient=True, bond="bridge")
    # Bridge dispatch returns union(placed_peg, bridge).
    assert isinstance(placed, Union)


def test_bond_bridge_on_planar_host_raises():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with pytest.raises(ValidationError, match="bond='bridge'.*curved"):
        peg.attach(plate, bond="bridge")


def test_bond_bridge_error_points_to_overlap():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with pytest.raises(ValidationError, match="bond='overlap'"):
        peg.attach(plate, bond="bridge")


def test_bond_bridge_without_orient_raises_on_non_coaxial():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    # Without orient=True, peg's bottom normal is (0,0,-1); host's
    # outer_wall normal is (1,0,0). Not coaxial.
    with pytest.raises(ValidationError, match="coaxial"):
        peg.attach(hub, on="outer_wall", angle=0, bond="bridge")


def test_bond_bridge_on_inner_wall_raises():
    from scadwright.shapes import Tube
    tube = Tube(od=20, id=10, h=15)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="inner"):
        peg.attach(tube, on="inner_wall", angle=0, orient=True, bond="bridge")


def test_bond_bridge_on_sphere_with_polar():
    ball = sphere(r=10)
    peg = cube([2, 2, 5])
    placed = peg.attach(
        ball, on="surface", polar=90, angle=0, orient=True, bond="bridge",
    )
    assert isinstance(placed, Union)


# --- bond="shift" ---


def test_bond_shift_planar_succeeds():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    placed = peg.attach(plate, bond="shift")
    assert isinstance(placed, Translate)
    # peg's bottom (2, 2, 0) goes to plate's top (10, 10, 2) with eps offset.
    # offset = (10-2, 10-2, 2-0) - eps * (0,0,1) = (8, 8, 1.99).
    assert placed.v[0] == pytest.approx(8.0)
    assert placed.v[1] == pytest.approx(8.0)
    assert placed.v[2] == pytest.approx(1.99)  # 2.0 - 0.01


def test_bond_shift_curved_host_succeeds():
    """bond='shift' always works, even on curved hosts."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    placed = peg.attach(hub, on="outer_wall", angle=0, bond="shift")
    assert isinstance(placed, Translate)


def test_bond_shift_with_custom_eps():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    placed = peg.attach(plate, bond="shift", eps=0.05)
    assert placed.v[2] == pytest.approx(2.0 - 0.05)


# --- disable_eps_fuse() collapses every bond to exact contact ---


def test_disable_eps_fuse_overrides_bond_overlap():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with disable_eps_fuse():
        placed = peg.attach(plate, bond="overlap")
    # Exact contact: no eps offset, no extended union.
    assert isinstance(placed, Translate)
    assert placed.v[2] == pytest.approx(2.0)  # exact, no eps


def test_disable_eps_fuse_overrides_bond_bridge():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with disable_eps_fuse():
        placed = peg.attach(
            hub, on="outer_wall", angle=0, orient=True, bond="bridge",
        )
    # Should be a Translate (no Union, no bridge geometry).
    assert isinstance(placed, Translate)


def test_disable_eps_fuse_overrides_bond_shift():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with disable_eps_fuse():
        placed = peg.attach(plate, bond="shift")
    # Exact contact, no eps shift.
    assert placed.v[2] == pytest.approx(2.0)


# --- existing fuse=True behavior unchanged ---


def test_fuse_true_planar_unchanged():
    """fuse=True without bond= should still hit overlap (Tier 1)."""
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    placed = peg.attach(plate, fuse=True)
    # Same shape as bond="overlap" output.
    placed_explicit = peg.attach(plate, bond="overlap")
    assert placed.v == pytest.approx(placed_explicit.v)


def test_fuse_true_curved_unchanged():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    placed = peg.attach(hub, on="outer_wall", angle=0, orient=True, fuse=True)
    placed_explicit = peg.attach(
        hub, on="outer_wall", angle=0, orient=True, bond="bridge",
    )
    # Both produce a Union with the bridge.
    assert isinstance(placed, Union)
    assert isinstance(placed_explicit, Union)


# --- standalone fuse(a, b, bond=...) ---


def test_fuse_function_bond_overlap():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    result = fuse(peg, plate, on="top", using_anchor="bottom", bond="overlap")
    assert isinstance(result, Union)


def test_fuse_function_bond_bridge():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    # Peg's bottom normal needs to oppose hub's outer_wall normal —
    # rotate peg first.
    peg_rotated = peg.rotate([0, 90, 0])
    result = fuse(
        peg_rotated, hub, on="outer_wall", using_anchor="bottom", bond="bridge",
    )
    assert isinstance(result, Union)


def test_fuse_function_bond_shift():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    result = fuse(peg, plate, on="top", using_anchor="bottom", bond="shift")
    assert isinstance(result, Union)


def test_fuse_function_invalid_bond_raises():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with pytest.raises(ValidationError, match="bond= must be one of"):
        fuse(peg, plate, on="top", using_anchor="bottom", bond="bogus")


def test_fuse_function_overlap_on_curved_raises():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="bond='overlap'.*planar"):
        fuse(peg, hub, on="outer_wall", using_anchor="bottom", bond="overlap")


def test_fuse_function_bridge_on_planar_raises():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with pytest.raises(ValidationError, match="bond='bridge'.*curved"):
        fuse(peg, plate, on="top", using_anchor="bottom", bond="bridge")


# --- smart cascade (fuse=True without bond=) raises when no bond applies ---


def test_fuse_true_raises_when_no_bond_applies():
    """A spherical peg on a planar host: neither bond fits.
    bond='overlap' needs planar+planar (peg's anchor is spherical).
    bond='bridge' needs the *host* to be curved (host is planar).
    fuse=True should raise with both reasons + workaround pointers.
    """
    floor = cube([40, 40, 2])
    with pytest.raises(ValidationError, match="no applicable bond"):
        sphere(r=5).attach(floor, fuse=True)


def test_fuse_true_error_names_both_bonds():
    floor = cube([40, 40, 2])
    with pytest.raises(ValidationError) as exc_info:
        sphere(r=5).attach(floor, fuse=True)
    msg = str(exc_info.value)
    assert "bond='overlap'" in msg
    assert "bond='bridge'" in msg
    assert "bond='shift'" in msg
    assert "disable_eps_fuse" in msg


def test_fuse_function_smart_cascade_raises():
    """Standalone fuse() also raises in the no-applicable-bond case.

    Two Tube inner_wall anchors: both kind='cylindrical' with
    surface_params['inner']=True. Bridge requires convex-outer host
    on at least one side; overlap requires planar+planar. Neither fits.
    """
    from scadwright.shapes import Tube

    a = Tube(od=20, id=10, h=15)
    b = Tube(od=30, id=12, h=20)
    with pytest.raises(ValidationError, match="no applicable bond"):
        fuse(a, b, on="inner_wall", using_anchor="inner_wall")
