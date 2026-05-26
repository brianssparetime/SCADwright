"""Tests for the peer auto-match form of ``boolops.fuse(a, b)``.

The explicit (both anchors named) path is exercised in
``test_attach_bond.py``. Here we verify the new auto-match behavior:
matching runs, dispatch picks the right side, errors fire on the
spec's matrix.
"""

from __future__ import annotations

import pytest

from scadwright.ast.csg import Union
from scadwright.boolops import fuse
from scadwright.errors import ValidationError
from scadwright.primitives import cube
from scadwright.shapes import Funnel, Tube


# --- Basic peer auto-match ---


def test_fuse_peer_no_anchors_planar_cube_on_cube():
    """Two same-sized cubes touching at planar faces: auto-match finds
    the contact, dispatch builds the union."""
    plate = cube([10, 10, 2], center=True)
    peg = cube([10, 10, 5], center=True).up(3.5)
    result = fuse(peg, plate)
    assert isinstance(result, Union)


def test_fuse_peer_concentric_tubes():
    """The lens-housing pattern in peer form: holder inside barrel."""
    barrel = Tube(h=50, od=20, id=10)
    holder = Tube(h=8, od=10, id=4).up(20)
    result = fuse(holder, barrel)
    assert isinstance(result, Union)


def test_fuse_peer_concentric_funnels():
    """Two concentric Funnels with mating walls."""
    outer = Funnel(h=20, thk=2, bot_od=20, top_od=30)
    inner = Funnel(h=20, thk=2, bot_od=16, top_od=26)
    result = fuse(inner, outer)
    assert isinstance(result, Union)


# --- Single-anchor naming ---


def test_fuse_peer_only_on_named_auto_matches_self():
    """on= names host's anchor; self auto-matches against it."""
    barrel = Tube(h=50, od=20, id=10)
    holder = Tube(h=8, od=10, id=4).up(20)
    result = fuse(holder, barrel, on="inner_wall")
    assert isinstance(result, Union)


def test_fuse_peer_only_from_anchor_named_auto_matches_host():
    """from_anchor= names self's anchor; host auto-matches against it."""
    barrel = Tube(h=50, od=20, id=10)
    holder = Tube(h=8, od=10, id=4).up(20)
    result = fuse(holder, barrel, from_anchor="outer_wall")
    assert isinstance(result, Union)


def test_fuse_peer_using_anchor_and_from_anchor_alias_conflict_raises():
    """using_anchor= and from_anchor= are aliases; can't pass both."""
    a = cube([5, 5, 5])
    b = cube([5, 5, 5])
    with pytest.raises(ValidationError, match="only one of using_anchor"):
        fuse(a, b, using_anchor="bottom", from_anchor="bottom")


# --- Errors ---


def test_fuse_peer_zero_matches_raises():
    a = cube([5, 5, 5])
    b = cube([5, 5, 5]).up(20)
    with pytest.raises(ValidationError, match="no coincident-surface contact"):
        fuse(a, b)


def test_fuse_peer_bridge_kwarg_without_anchors_raises():
    """bridge=True needs both on= and using_anchor=. Auto-match form
    rejects bridge= without anchors."""
    peg = cube([2, 2, 5])
    tube = Tube(h=20, od=20, id=10)
    with pytest.raises(ValidationError, match="require both on= and"):
        fuse(peg, tube, bridge=True)


def test_fuse_peer_bond_kwarg_without_anchors_raises():
    a = cube([5, 5, 5])
    b = cube([5, 5, 5])
    with pytest.raises(ValidationError, match="require both on= and"):
        fuse(a, b, bond="overlap")


# --- disable_eps_fuse integration ---


def test_fuse_peer_disable_eps_skips_extension():
    from scadwright.api.fuse_mode import disable_eps_fuse
    barrel = Tube(h=50, od=20, id=10)
    holder = Tube(h=8, od=10, id=4).up(20)
    with disable_eps_fuse():
        result = fuse(holder, barrel)
    assert isinstance(result, Union)
    # No extension: both children should be the original (or aligned) shapes.
    assert len(result.children) == 2


def test_fuse_peer_disable_eps_still_raises_on_no_match():
    from scadwright.api.fuse_mode import disable_eps_fuse
    a = cube([5, 5, 5])
    b = cube([5, 5, 5]).up(20)
    with disable_eps_fuse():
        with pytest.raises(ValidationError, match="no coincident-surface contact"):
            fuse(a, b)


# --- Legacy explicit path still works ---


def test_fuse_legacy_explicit_anchors_with_bond_shift_preserved():
    """Existing test_attach_bond.py covers this in detail; sanity check
    here that the explicit-both-anchors path didn't regress."""
    peg = cube([3, 3, 5])
    plate = cube([10, 10, 2])
    result = fuse(
        peg, plate, on="top", using_anchor="bottom", bond="shift",
    )
    assert isinstance(result, Union)
