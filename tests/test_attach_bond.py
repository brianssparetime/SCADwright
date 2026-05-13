"""Tests for the ``bond=`` and ``bridge=`` kwargs on ``Node.attach`` and
``boolops.fuse``.

``bond`` controls the planar eps mechanism (values: ``"overlap"``,
``"shift"``). ``bridge`` builds a structural fill for convex-outer curved
hosts. They don't combine. ``bond='bridge'`` from the old API raises a
migration-hint error.
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


def test_bond_bridge_migration_hint():
    """bond='bridge' was the curved-host bond; it's been replaced by the
    bridge=True kwarg. The validator emits a migration-hint error."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="bridge=True"):
        peg.attach(hub, on="outer_wall", angle=0, orient=True, bond="bridge")


def test_bond_with_fuse_false_raises():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with pytest.raises(ValidationError, match="contradicts bond"):
        peg.attach(plate, fuse=False, bond="overlap")


def test_bond_and_bridge_contradict():
    """bond= is for planar eps; bridge=True is curved-host fill. Passing
    both raises."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="doesn't combine with bridge"):
        peg.attach(
            hub, on="outer_wall", angle=0, orient=True,
            bond="overlap", bridge=True,
        )


def test_bond_implies_fuse_true():
    """bond=... should produce eps-modified geometry even without fuse=True."""
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    placed_with_bond = peg.attach(plate, bond="shift")
    placed_with_fuse = peg.attach(plate, fuse=True, bond="shift")
    assert placed_with_bond.v == pytest.approx(placed_with_fuse.v)
    placed_exact = peg.attach(plate, fuse=False)
    assert placed_with_bond.v != placed_exact.v


# --- bond="overlap" ---


def test_bond_overlap_planar_success():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    placed = peg.attach(plate, bond="overlap")
    assert isinstance(placed, Translate)

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
    with pytest.raises(ValidationError, match="bridge=True"):
        peg.attach(hub, on="outer_wall", bond="overlap")


# --- bridge=True ---


def test_bridge_on_cylinder_wall_with_orient():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    placed = peg.attach(hub, on="outer_wall", angle=0, orient=True, bridge=True)
    assert isinstance(placed, Union)


def test_bridge_on_planar_host_raises():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with pytest.raises(ValidationError, match="bridge=True requires a curved"):
        peg.attach(plate, bridge=True)


def test_bridge_error_points_to_fuse():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with pytest.raises(ValidationError, match="fuse=True"):
        peg.attach(plate, bridge=True)


def test_bridge_without_orient_raises_on_non_coaxial():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="coaxial"):
        peg.attach(hub, on="outer_wall", angle=0, bridge=True)


def test_bridge_on_inner_wall_raises():
    from scadwright.shapes import Tube
    tube = Tube(od=20, id=10, h=15)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="inner"):
        peg.attach(tube, on="inner_wall", angle=0, orient=True, bridge=True)


def test_bridge_on_sphere_with_polar():
    ball = sphere(r=10)
    peg = cube([2, 2, 5])
    placed = peg.attach(
        ball, on="surface", polar=90, angle=0, orient=True, bridge=True,
    )
    assert isinstance(placed, Union)


# --- bond="shift" ---


def test_bond_shift_planar_succeeds():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    placed = peg.attach(plate, bond="shift")
    assert isinstance(placed, Translate)
    # peg's bottom (2, 2, 0) goes to plate's top (10, 10, 2) with eps offset.
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


# --- disable_eps_fuse() collapses bond= and the bridge's peg-side slice ---


def test_disable_eps_fuse_overrides_bond_overlap():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with disable_eps_fuse():
        placed = peg.attach(plate, bond="overlap")
    assert isinstance(placed, Translate)
    assert placed.v[2] == pytest.approx(2.0)  # exact, no eps


def test_disable_eps_fuse_keeps_bridge_geometry():
    """Under disable scope, bridge=True still builds bridge geometry —
    the structural fill is preserved (it's not eps). Only the peg-side
    eps slice (gated on fuse=True) drops."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with disable_eps_fuse():
        placed = peg.attach(
            hub, on="outer_wall", angle=0, orient=True, bridge=True, fuse=True,
        )
    # Bridge result is still a Union (placed_peg, bridge).
    assert isinstance(placed, Union)


def test_disable_eps_fuse_overrides_bond_shift():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with disable_eps_fuse():
        placed = peg.attach(plate, bond="shift")
    assert placed.v[2] == pytest.approx(2.0)


# --- existing fuse=True behavior unchanged on planar ---


def test_fuse_true_planar_unchanged():
    """fuse=True without bond= should still hit overlap (Tier 1)."""
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    placed = peg.attach(plate, fuse=True)
    placed_explicit = peg.attach(plate, bond="overlap")
    assert placed.v == pytest.approx(placed_explicit.v)


def test_fuse_true_on_curved_raises():
    """fuse=True on a convex-outer curved host raises and points at
    bridge=True. (Previously this auto-bridged.)"""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="bridge=True"):
        peg.attach(hub, on="outer_wall", angle=0, orient=True, fuse=True)


# --- standalone fuse(a, b, bond=..., bridge=...) ---


def test_fuse_function_bond_overlap():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    result = fuse(peg, plate, on="top", using_anchor="bottom", bond="overlap")
    assert isinstance(result, Union)


def test_fuse_function_bridge():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    peg_rotated = peg.rotate([0, 90, 0])
    result = fuse(
        peg_rotated, hub, on="outer_wall", using_anchor="bottom", bridge=True,
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


def test_fuse_function_bond_bridge_migration_hint():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    peg_rotated = peg.rotate([0, 90, 0])
    with pytest.raises(ValidationError, match="bridge=True"):
        fuse(
            peg_rotated, hub, on="outer_wall", using_anchor="bottom",
            bond="bridge",
        )


def test_fuse_function_overlap_on_curved_raises():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="bond='overlap'.*planar"):
        fuse(peg, hub, on="outer_wall", using_anchor="bottom", bond="overlap")


def test_fuse_function_bridge_on_planar_raises():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with pytest.raises(ValidationError, match="bridge=True requires a curved"):
        fuse(peg, plate, on="top", using_anchor="bottom", bridge=True)


def test_fuse_function_bond_and_bridge_contradict():
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="doesn't combine with bridge"):
        fuse(
            peg, hub, on="outer_wall", using_anchor="bottom",
            bond="shift", bridge=True,
        )


# --- smart cascade (fuse=True without bond=) raises when no path applies ---


def test_fuse_true_raises_when_no_path_applies():
    """A spherical peg on a planar host: overlap needs planar+planar
    (peg's anchor is spherical); bridge needs a *curved* host (host is
    planar). fuse=True raises with workaround pointers."""
    floor = cube([40, 40, 2])
    with pytest.raises(ValidationError, match="no applicable eps mechanism"):
        sphere(r=5).attach(floor, fuse=True)


def test_fuse_true_error_names_paths():
    floor = cube([40, 40, 2])
    with pytest.raises(ValidationError) as exc_info:
        sphere(r=5).attach(floor, fuse=True)
    msg = str(exc_info.value)
    assert "bond='overlap'" in msg
    assert "bridge=True" in msg
    assert "bond='shift'" in msg
    assert "disable_eps_fuse" in msg


def test_fuse_function_smart_cascade_raises():
    """Standalone fuse() also raises in the no-applicable case.

    Two Tube inner_wall anchors: both kind='cylindrical' with
    surface_params['inner']=True. Bridge requires convex-outer; overlap
    requires planar+planar. Neither fits.
    """
    from scadwright.shapes import Tube

    a = Tube(od=20, id=10, h=15)
    b = Tube(od=30, id=12, h=20)
    with pytest.raises(ValidationError, match="no applicable eps mechanism"):
        fuse(a, b, on="inner_wall", using_anchor="inner_wall")
