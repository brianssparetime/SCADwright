"""Tests for ``Node.prefers_shift_at_anchor`` — the hook that lets cap-like
Components opt out of the cross-section-extend Tier 2 fallback in the
``attach(fuse=True)`` cascade.

The Tier 2 fallback produces an eps slab whose cross-section matches the
contact face. For a Component whose contact face IS the entire outermost
cross-section (annular caps on fillet rings, lids sized to match a host's
od), that slab's outer surface is coplanar with the host's outer surface
and the union has the coplanarity it was supposed to fix. The hook makes
the smart cascade pick ``bond='shift'`` instead at the affected anchor.
"""

from __future__ import annotations

import pytest

from scadwright import Component
from scadwright.ast.csg import Union
from scadwright.emit import emit_str
from scadwright.primitives import cube, cylinder
from scadwright.shapes import FilletRing, Tube


# --- Default behavior ---


def test_default_returns_false():
    """The base Node implementation declines to opt in."""
    assert cube(10).prefers_shift_at_anchor.__func__.__qualname__.startswith("Node.")
    # Call it on a few node types — defaults to False.
    from scadwright.anchor import Anchor
    a = Anchor(position=(0.0, 0.0, 0.0), normal=(0.0, 0.0, -1.0), kind="planar")
    assert cube(10).prefers_shift_at_anchor(a) is False
    assert cylinder(h=10, r=5).prefers_shift_at_anchor(a) is False
    assert Tube(h=10, od=20, id=16).prefers_shift_at_anchor(a) is False


def test_default_cascade_uses_overlap():
    """Without the hook opt-in on a Tier-2-bound Component, attach(fuse=True)
    goes through cross-section extension and emits a union containing the
    slab — distinct from the shift form."""

    class _NoExtension(Component):
        equations = "h > 0"

        def build(self):
            return cube([4, 4, self.h])

    host = cube([20, 20, 2])
    peg = _NoExtension(h=5)
    out_default = peg.attach(host, fuse=True)
    out_shift = peg.attach(host, fuse=True, bond="shift")
    # Default path goes through Tier 2 (slab) — emits union(peg, slab).
    # Shift path bypasses the slab.
    assert emit_str(out_default) != emit_str(out_shift)


# --- Hook opt-in triggers shift ---


class _CapLike(Component):
    """Test fixture: a Component that always prefers shift at any planar
    anchor. Stand-in for FilletRing-pattern Components."""

    equations = "h, w > 0"

    def build(self):
        return cube([self.w, self.w, self.h])

    def prefers_shift_at_anchor(self, anchor) -> bool:
        return anchor.kind == "planar"


def test_opt_in_triggers_shift_dispatch():
    """A Component that opts in via the hook gets bond='shift' under
    attach(fuse=True), even though its anchor would otherwise resolve
    to bond='overlap'."""
    host = cube([20, 20, 2])
    cap = _CapLike(h=5, w=20)
    out_default = cap.attach(host, fuse=True)
    out_explicit = cap.attach(host, fuse=True, bond="shift")
    # Both should emit the same SCAD — the hook is supposed to be
    # equivalent to passing bond='shift' explicitly.
    assert emit_str(out_default) == emit_str(out_explicit)


def test_opt_out_uses_overlap():
    """A Component that doesn't opt in (default False) keeps the overlap
    path, distinct from the shift path."""
    host = cube([20, 20, 2])

    class _Plain(Component):
        equations = "h > 0"

        def build(self):
            return cube([4, 4, self.h])

    peg = _Plain(h=5)
    out_default = peg.attach(host, fuse=True)
    out_shift = peg.attach(host, fuse=True, bond="shift")
    # Shouldn't match — default goes through overlap (cross-section
    # extension), shift bypasses extension.
    assert emit_str(out_default) != emit_str(out_shift)


# --- FilletRing override (the standard-library case) ---


def test_fillet_ring_opts_in_at_planar_caps():
    """FilletRing's bbox-derived bottom anchor should be flagged as
    cap-like. Top depends on slant; for outwards slant the top is the
    cone apex (still cap-like for our purposes — extension would be
    degenerate anyway)."""
    ring = FilletRing(id=10, od=20, base_angle=45)
    from scadwright.anchor import Anchor
    bottom = Anchor(position=(0, 0, 0), normal=(0, 0, -1), kind="planar")
    top = Anchor(position=(0, 0, 5), normal=(0, 0, 1), kind="planar")
    side = Anchor(position=(10, 0, 2.5), normal=(1, 0, 0), kind="planar")
    assert ring.prefers_shift_at_anchor(bottom) is True
    assert ring.prefers_shift_at_anchor(top) is True
    # Non-z-aligned anchors don't opt in (the fillet's side anchor
    # doesn't share dimensions with the host).
    assert ring.prefers_shift_at_anchor(side) is False


def test_fillet_ring_attach_emits_shift_geometry():
    """A FilletRing attached to a same-od Tube via attach(fuse=True)
    should resolve to the shift path, not the cross-section-extend path."""
    tube = Tube(h=10, od=20, id=16)
    ring = FilletRing(id=16, od=20, base_angle=45)
    via_cascade = ring.attach(tube, fuse=True)
    via_explicit_shift = ring.attach(tube, fuse=True, bond="shift")
    # The hook means the cascade picks shift; emit should match the
    # explicit shift form exactly.
    assert emit_str(via_cascade) == emit_str(via_explicit_shift)
