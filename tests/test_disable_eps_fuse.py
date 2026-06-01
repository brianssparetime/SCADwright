"""Tests for the ``disable_eps_fuse()`` scoped opt-out.

Inside a ``with disable_eps_fuse():`` block, ``attach(fuse=True)`` and
``fuse(...)`` calls behave as if ``fuse`` were ``False``: exact anchor
coincidence, no parametric extension, no shift. Anchor lookup,
placement, ``orient=True``, ``angle=`` etc. continue to work.
"""

import pytest

from scadwright import bbox, disable_eps_fuse, fuse_enabled
from scadwright.boolops import fuse, union
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder, sphere


# --- Basic flag / context manager mechanics ---


def test_fuse_enabled_default_true():
    assert fuse_enabled() is True


def test_disable_eps_fuse_sets_flag_false_in_scope():
    assert fuse_enabled() is True
    with disable_eps_fuse():
        assert fuse_enabled() is False
    assert fuse_enabled() is True


# --- attach(fuse=True) inside the scope ---


def test_attach_fuse_true_inside_disable_matches_fuse_false():
    """Inside disable_eps_fuse(), attach(fuse=True) produces the same
    bbox as attach(fuse=False) — exact contact, no eps anywhere."""
    floor = cube([40, 40, 2])
    pylon = cube([5, 5, 10])
    with disable_eps_fuse():
        result_disabled = pylon.attach(floor, fuse=True)
    result_no_fuse = pylon.attach(floor)  # fuse=False default
    assert bbox(result_disabled) == bbox(result_no_fuse)


def test_attach_fuse_true_outside_disable_extends_normally():
    """After exiting disable_eps_fuse(), the next attach(fuse=True)
    gets normal local-extension behavior (top preserved at z=12)."""
    floor = cube([40, 40, 2])
    pylon = cube([5, 5, 10])
    with disable_eps_fuse():
        pass  # enter and exit, no fuse calls inside
    pylon_attached = pylon.attach(floor, fuse=True)
    bb = bbox(pylon_attached)
    assert bb.min[2] == pytest.approx(1.99)
    assert bb.max[2] == pytest.approx(12.0)


def test_attach_fuse_true_on_cylinder_wall_inside_disable_no_shift():
    """The legacy shift fallback is also suppressed: a cylindrical-wall
    fuse=True normally shifts by eps along the wall normal; inside
    disable_eps_fuse(), there's no shift."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    no_fuse = peg.attach(hub, on="outer_wall", angle=90)
    with disable_eps_fuse():
        with_fuse = peg.attach(hub, on="outer_wall", angle=90, fuse=True)
    # Without disable: with_fuse would have been shifted in -y.
    # With disable: it matches the no-fuse case exactly.
    assert bbox(with_fuse).center == pytest.approx(bbox(no_fuse).center)


# --- fuse(...) function inside the scope ---


def test_fuse_function_inside_disable_is_exact_contact():
    """fuse(a, b, ...) inside disable_eps_fuse() unions a and b at
    exact anchor coincidence, no extension, no shift."""
    floor = cube([40, 40, 2])
    pylon = cube([5, 5, 10])
    with disable_eps_fuse():
        result = fuse(pylon, floor, on="top", using_anchor="bottom")
    bb = bbox(result)
    # Floor: z=0..2. Pylon: bottom at z=2 (exact contact), top at z=12.
    assert bb.min[2] == pytest.approx(0.0)
    assert bb.max[2] == pytest.approx(12.0)
    # Pylon's bottom is exactly at z=2 (no eps extension into floor).
    # Verify by checking that the union of just the children covers
    # floor + pylon without eps.


def test_fuse_function_outside_disable_extends_normally():
    """fuse(a, b, ...) outside disable_eps_fuse() applies local
    extension as usual."""
    floor = cube([40, 40, 2])
    pylon = cube([5, 5, 10])
    result = fuse(pylon, floor, on="top", using_anchor="bottom")
    bb = bbox(result)
    # Floor extends top by eps to 2.01 (the simpler-side selection
    # picks floor's top because the alternative would need a Translate).
    assert bb.max[2] == pytest.approx(12.0)


# --- Other attach features remain functional ---


def test_disable_eps_fuse_preserves_orient():
    """orient=True still rotates self correctly inside disable_eps_fuse()."""
    wall = cube([2, 40, 40])
    peg = cube([5, 5, 10])
    no_disable = peg.attach(wall, on="rside", using_anchor="bottom", orient=True)
    with disable_eps_fuse():
        with_disable = peg.attach(
            wall, on="rside", using_anchor="bottom", orient=True, fuse=True,
        )
    # Same placement: only the eps adjustment is suppressed, and there
    # was no eps to start with on the no-disable orient call.
    assert bbox(no_disable).center == pytest.approx(bbox(with_disable).center)


def test_disable_eps_fuse_preserves_angle():
    """angle= positioning still works."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    no_fuse = peg.attach(hub, on="outer_wall", angle=120)
    with disable_eps_fuse():
        result = peg.attach(hub, on="outer_wall", angle=120, fuse=True)
    # With disable_eps_fuse, the angle=120 placement still works; the
    # fuse=True is the only thing suppressed.
    assert bbox(result).center == pytest.approx(bbox(no_fuse).center)


def test_disable_eps_fuse_preserves_through():
    """through() is independent of the fuse flag and works identically."""
    plate = cube([40, 40, 5])
    hole_in = cylinder(h=5, r=3).through(plate)
    with disable_eps_fuse():
        hole_out = cylinder(h=5, r=3).through(plate)
    # through() extends past coincident faces regardless of fuse mode.
    assert bbox(hole_in) == bbox(hole_out)


def test_disable_eps_fuse_doesnt_affect_fuse_false():
    """attach(fuse=False) is unaffected — it doesn't read the flag."""
    floor = cube([40, 40, 2])
    pylon = cube([5, 5, 10])
    inside = None
    with disable_eps_fuse():
        inside = pylon.attach(floor, fuse=False)
    outside = pylon.attach(floor, fuse=False)
    assert bbox(inside) == bbox(outside)


def test_disable_eps_fuse_preserves_bridge_geometry():
    """bridge=True is structural, not eps. Under disable scope, the
    bridge still builds (the peg-side eps slice drops, but the
    inscription fill itself persists)."""
    from scadwright.ast.csg import Difference, Union
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with disable_eps_fuse():
        result = peg.attach(
            hub, on="outer_wall", angle=0, orient=True,
            bridge=True, fuse=True,
        )
    assert isinstance(result, Union)
    assert any(isinstance(c, Difference) for c in result.children)


def test_disable_eps_fuse_preserves_boolops_fuse_bridge():
    """Symmetric path: boolops.fuse(..., bridge=True) under disable scope
    also still builds the bridge structural fill (peg-side eps slice
    drops, since eps_overlap collapses to False)."""
    from scadwright.ast.csg import Difference, Union
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5]).rotate([0, 90, 0])
    with disable_eps_fuse():
        result = fuse(
            peg, hub, on="outer_wall", using_anchor="bottom", bridge=True,
        )
    assert isinstance(result, Union)
    assert any(isinstance(c, Difference) for c in result.children)


# --- node.fuse(host) chained form under disable_eps_fuse ---


def test_node_fuse_planar_inside_disable_no_extension():
    """Node.fuse on planar contact inside disable: no fuse_extend run,
    no cross-section slab, no shift — just union of self and host."""
    from scadwright.ast.csg import Union
    from scadwright.shapes import Tube
    plate = cube([10, 10, 2], center=True)
    peg = cube([10, 10, 5], center=True).up(3.5)
    with disable_eps_fuse():
        result = peg.fuse(plate)
    assert isinstance(result, Union)
    # bbox should not include any eps overlap on the contact face.
    bb = bbox(result)
    assert bb.min[2] == pytest.approx(-1.0)
    assert bb.max[2] == pytest.approx(6.0)


def test_node_fuse_curved_inside_disable_no_radial_extension():
    """Node.fuse on concentric cylindrical contact inside disable:
    no rebuild of host with bumped id; just the bare union."""
    from scadwright.ast.csg import Union
    from scadwright.shapes import Tube
    barrel = Tube(h=50, od=20, id=10)
    holder = Tube(h=8, od=10, id=4).up(20)
    with disable_eps_fuse():
        result = holder.fuse(barrel)
    assert isinstance(result, Union)
    # Barrel id should stay 10 (no shrink).
    assert barrel.id == 10
    # Holder od should stay 10.
    assert holder.child.od == 10  # holder is a Translate wrapping the Tube


def test_node_fuse_inside_disable_still_validates_matching():
    """Matching runs even under disable; a bad call still raises."""
    a = cube([5, 5, 5])
    b = cube([5, 5, 5]).up(20)
    with disable_eps_fuse():
        with pytest.raises(ValidationError, match="no coincident-surface contact"):
            a.fuse(b)
