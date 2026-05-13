"""Tests for the silent-no-op detection added to the fuse bridge path.

Closes the gap between cross-section fuse (which has always validated
the peg's anchor against its bbox) and bridge fuse (which previously
silently no-opped on degenerate geometry).
"""

import pytest

from scadwright.anchor import Anchor
from scadwright.ast._fuse_bridge import build_curved_bridge
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder, sphere


def test_bridge_raises_on_off_face_peg_anchor():
    """A peg whose at-anchor isn't on its outermost face should error,
    not produce a silent no-op."""
    peg = cube([4, 4, 6])
    # Anchor in the cube's interior, with a +Z normal — not on the
    # outermost face (the actual top is at z=6).
    bad_anchor = Anchor(position=(2.0, 2.0, 3.0), normal=(0.0, 0.0, 1.0))
    host = cylinder(h=20, r=10)
    host_anchor = Anchor(
        position=(10.0, 0.0, 10.0),
        normal=(1.0, 0.0, 0.0),
        kind="cylindrical",
        axis=(0.0, 0.0, 1.0),
        radius=10.0,
        length=20.0,
    )
    with pytest.raises(ValidationError, match="bridge.*outermost face"):
        build_curved_bridge(
            peg, bad_anchor, host, host_anchor,
            shift=(0.0, 0.0, 0.0), eps=0.01, eps_overlap=True,
        )


def test_bridge_raises_on_degenerate_peg_bbox():
    """A peg whose bbox is degenerate in 2+ axes can't span a planar
    contact region — the bridge prism would have empty cross-section."""
    # A 2D-ish object: a flat square with zero z extent.
    peg = cube([4, 4, 0])
    flat_anchor = Anchor(position=(2.0, 2.0, 0.0), normal=(0.0, 0.0, 1.0))
    host = cylinder(h=20, r=10)
    host_anchor = Anchor(
        position=(10.0, 0.0, 10.0),
        normal=(1.0, 0.0, 0.0),
        kind="cylindrical",
        axis=(0.0, 0.0, 1.0),
        radius=10.0,
        length=20.0,
    )
    # cube(z=0) has 1 zero-extent axis (z); 2 non-zero. That's fine
    # for the existing cross-section gate (requires 2+ non-zero), so
    # check a more degenerate case: a line.
    peg_line = cube([4, 0, 0])
    line_anchor = Anchor(position=(2.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0))
    with pytest.raises(ValidationError, match="bridge.*near-zero extent"):
        build_curved_bridge(
            peg_line, line_anchor, host, host_anchor,
            shift=(0.0, 0.0, 0.0), eps=0.01, eps_overlap=True,
        )


def test_bridge_passes_on_legitimate_peg():
    """A normal cube peg with its bottom anchor on a cylindrical wall
    should NOT raise — sanity check the validation isn't too strict."""
    peg = cube([4, 4, 6])
    # cube(center=False)'s bottom face is at z=0 with normal (0,0,-1).
    bottom_anchor = Anchor(
        position=(2.0, 2.0, 0.0), normal=(0.0, 0.0, -1.0)
    )
    host = cylinder(h=20, r=10)
    host_anchor = Anchor(
        position=(10.0, 0.0, 10.0),
        normal=(1.0, 0.0, 0.0),
        kind="cylindrical",
        axis=(0.0, 0.0, 1.0),
        radius=10.0,
        length=20.0,
    )
    bridge = build_curved_bridge(
        peg, bottom_anchor, host, host_anchor,
        shift=(0.0, 0.0, 0.0), eps=0.01, eps_overlap=True,
    )
    assert bridge is not None


def test_bridge_passes_through_attach_chain():
    """End-to-end: a normal cube on a cylinder via attach(bridge=True)
    still works after the validation was added."""
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    placed = peg.attach(hub, on="outer_wall", angle=0, orient=True, bridge=True)
    assert placed is not None


def test_bridge_passes_on_sphere_host_with_polar():
    """Spherical host with polar/azimuth placement also goes through
    the bridge — make sure the new validation doesn't break it."""
    ball = sphere(r=10)
    peg = cube([2, 2, 5])
    placed = peg.attach(
        ball, on="surface", polar=90, angle=0, orient=True, bridge=True,
    )
    assert placed is not None
