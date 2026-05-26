"""Unit tests for the curved-contact dispatchers in placement.py.

Exercises _dispatch_curved_overlap (asymmetric, used by Node.fuse) and
_dispatch_curved_overlap_symmetric (peer, used by boolops.fuse) — in
isolation, without going through Node.fuse or the standalone fuse()
yet. The side-selection rule (inner=False extends first, falls to
inner=True, then raises) is the contract being verified here.
"""

from __future__ import annotations

import pytest

from scadwright.ast._surface_match import find_contacts
from scadwright.ast.base import SourceLocation
from scadwright.ast.csg import Union
from scadwright.ast.placement import (
    _dispatch_curved_overlap,
    _dispatch_curved_overlap_symmetric,
)
from scadwright.anchor import get_node_anchors
from scadwright.errors import ValidationError
from scadwright.primitives import cube
from scadwright.shapes import Funnel, Tube


def _loc():
    return SourceLocation.from_caller()


# --- Asymmetric (chained, Node.fuse path) ---


def test_curved_asymmetric_self_outer_extends_first():
    """Holder (outer, inner=False) inside Barrel (inner, inner=True):
    self_anchor.inner=False → holder's fuse_extend tried first; Tube
    supports it → result wraps the extended holder."""
    holder = Tube(h=8, od=10, id=4).up(20)
    barrel = Tube(h=50, od=20, id=10)
    matches = find_contacts(get_node_anchors(holder), get_node_anchors(barrel))
    m = [m for m in matches if m.kind == "cylindrical"][0]
    result = _dispatch_curved_overlap(
        holder, m.self_anchor, barrel, m.host_anchor, 0.01, _loc(),
    )
    assert isinstance(result, Union)
    # Two children: extended self (Translate wrapping new Tube with bumped od)
    # and host (the barrel).
    assert len(result.children) == 2


def test_curved_asymmetric_self_inner_host_extends():
    """Reverse the chain: Tube barrel (outer of the pair) acts as self,
    holder (inner) is the host. self_anchor.inner=True → host's
    fuse_extend tried first."""
    holder = Tube(h=8, od=10, id=4).up(20)
    barrel = Tube(h=50, od=20, id=10)
    # Call with barrel as self, holder as host (reversed).
    matches = find_contacts(get_node_anchors(barrel), get_node_anchors(holder))
    m = [m for m in matches if m.kind == "cylindrical"][0]
    # barrel.inner_wall has inner=True → self_anchor.inner=True path.
    result = _dispatch_curved_overlap(
        barrel, m.self_anchor, holder, m.host_anchor, 0.01, _loc(),
    )
    assert isinstance(result, Union)


def test_curved_asymmetric_neither_side_has_lever_raises():
    """A Cube (no curved fuse_extend) against another Cube via a
    synthetic cylindrical anchor on both sides: neither side can extend
    → raise."""
    from dataclasses import replace
    from scadwright.anchor import Anchor

    outer_cube = cube([10, 10, 20])
    inner_cube = cube([5, 5, 10])

    cyl_outer = Anchor(
        position=(5.0, 5.0, 10.0),
        normal=(1.0, 0.0, 0.0),
        kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=5.0, length=20.0, inner=False,
    )
    cyl_inner = Anchor(
        position=(2.5, 2.5, 5.0),
        normal=(-1.0, 0.0, 0.0),
        kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=5.0, length=10.0, inner=True,
    )
    with pytest.raises(ValidationError, match="neither side has a fuse_extend lever"):
        _dispatch_curved_overlap(
            outer_cube, cyl_outer, inner_cube, cyl_inner, 0.01, _loc(),
        )


# --- Symmetric (peer, boolops.fuse path) ---


def test_curved_symmetric_outer_a_extends():
    """Peer form: a is outer, b is inner. a's fuse_extend tried first."""
    a = Tube(h=20, od=10, id=4)
    b = Tube(h=20, od=20, id=10)  # b's inner_wall matches a's outer_wall
    matches = find_contacts(get_node_anchors(a), get_node_anchors(b))
    m = [m for m in matches if m.kind == "cylindrical"][0]
    result = _dispatch_curved_overlap_symmetric(
        a, m.self_anchor, b, m.host_anchor, 0.01, _loc(),
    )
    assert isinstance(result, Union)


def test_curved_symmetric_outer_b_extends():
    """Swap a and b: outer is now b. The dispatcher still picks the
    outer side first."""
    a = Tube(h=20, od=20, id=10)  # a's inner_wall matches b's outer_wall
    b = Tube(h=20, od=10, id=4)
    matches = find_contacts(get_node_anchors(a), get_node_anchors(b))
    m = [m for m in matches if m.kind == "cylindrical"][0]
    result = _dispatch_curved_overlap_symmetric(
        a, m.self_anchor, b, m.host_anchor, 0.01, _loc(),
    )
    assert isinstance(result, Union)


def test_curved_symmetric_neither_side_has_lever_raises():
    """Both sides Cubes with synthetic cylindrical anchors: neither
    extends → raise."""
    from scadwright.anchor import Anchor
    a = cube([10, 10, 20])
    b = cube([5, 5, 10])
    a_anchor = Anchor(
        position=(5.0, 5.0, 10.0), normal=(1.0, 0.0, 0.0),
        kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=5.0, length=20.0, inner=False,
    )
    b_anchor = Anchor(
        position=(2.5, 2.5, 5.0), normal=(-1.0, 0.0, 0.0),
        kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=5.0, length=10.0, inner=True,
    )
    with pytest.raises(ValidationError, match="neither side has a fuse_extend lever"):
        _dispatch_curved_overlap_symmetric(
            a, a_anchor, b, b_anchor, 0.01, _loc(),
        )
