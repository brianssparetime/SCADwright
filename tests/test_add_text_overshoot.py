"""Tests for the cutter host-side overshoot. The placement code shifts the
cutter past the host surface by ``TEXT_HOST_OVERSHOOT`` on the host-facing
side so CGAL's difference (inset) or union (raised) clears the polygon
approximation of curved hosts cleanly. These tests assert the cutter
bbox actually reaches that far past the nominal surface.

The numeric threshold is ``TEXT_HOST_OVERSHOOT * 0.85`` — a little slack to
absorb glyph-edge curvature (a flat-prism cutter's outer face is further
outside the cylinder at the tangential edges than at the center, so the
center is the conservative measurement) and floating-point noise."""

from __future__ import annotations

import math

import pytest

from scadwright.api.tolerances import TEXT_HOST_OVERSHOOT
from scadwright.bbox import bbox
from scadwright.primitives import cube, cylinder
from scadwright.shapes import Tube


_TOL = TEXT_HOST_OVERSHOOT * 0.85


def _cutter_bbox(host, **add_text_kwargs):
    """Build a text cutter against `host` and return its bbox.

    Uses ``text_geometry`` so we get the cutter alone (without the host
    unioned/differenced in). The result's bbox is the cutter's extent
    in the host's coordinate frame.
    """
    cutter = host.text_geometry(**add_text_kwargs)
    return bbox(cutter)


# --- Planar ---


def test_planar_inset_outer_overshoots_surface():
    """Inset on the top face of a cube: cutter's max-z must reach above
    the cube's top (z=10) by at least the host-eps threshold."""
    host = cube([20, 20, 10])
    bb = _cutter_bbox(host, label="X", on="top", relief=-0.4, font_size=4)
    assert bb.max[2] >= 10 + _TOL, (
        f"inset cutter max-z={bb.max[2]:.4f}; should overshoot top face "
        f"(z=10) by at least {_TOL:.4f}"
    )


def test_planar_raised_innermost_buried_in_host():
    """Raised on the top face: cutter's min-z (deepest point) must be
    below the cube's top by at least the host-eps threshold, so the
    union's seam is buried in solid host."""
    host = cube([20, 20, 10])
    bb = _cutter_bbox(host, label="X", on="top", relief=0.4, font_size=4)
    assert bb.min[2] <= 10 - _TOL, (
        f"raised cutter min-z={bb.min[2]:.4f}; should bury below the top "
        f"face (z=10) by at least {_TOL:.4f}"
    )


# --- Cylindrical (the user-reported case) ---


def _max_radial_distance(bb):
    """Max radial distance from the cylinder axis (assumed +Z through origin)
    that the bbox reaches. Uses the four xy-corners."""
    corners = [
        (bb.min[0], bb.min[1]),
        (bb.min[0], bb.max[1]),
        (bb.max[0], bb.min[1]),
        (bb.max[0], bb.max[1]),
    ]
    return max(math.hypot(x, y) for x, y in corners)


def _min_radial_distance(bb):
    """Min radial distance from the cylinder axis the bbox reaches.
    For a glyph-shaped cutter that doesn't straddle the axis, this is
    the minimum-magnitude corner — but we want the closest *point*, so
    project onto the radial axis the glyph sits along. Simpler: take
    the bbox center's radial distance minus the half-extent along it.
    """
    cx = (bb.min[0] + bb.max[0]) / 2.0
    cy = (bb.min[1] + bb.max[1]) / 2.0
    center_r = math.hypot(cx, cy)
    # Half-extent in radial direction (project the corner-to-corner extent
    # onto the radial unit vector through the center).
    if center_r < 1e-12:
        return 0.0
    ux, uy = cx / center_r, cy / center_r
    half = (
        abs((bb.max[0] - bb.min[0]) * ux)
        + abs((bb.max[1] - bb.min[1]) * uy)
    ) / 2.0
    return max(0.0, center_r - half)


def test_cylindrical_inset_outer_overshoots_surface():
    """The user-reported case: inset engraving on an outer wall. The
    cutter's outer radial extent must comfortably exceed the cylinder
    surface to prevent CGAL precision artifacts against the polygon."""
    R = 20.0
    host = cylinder(h=30, r=R, fn=48)
    bb = _cutter_bbox(host, label="X", on="outer_wall", relief=-0.4, font_size=4)
    r_max = _max_radial_distance(bb)
    assert r_max >= R + _TOL, (
        f"cylindrical inset cutter max radial={r_max:.4f}; should reach "
        f"at least {R + _TOL:.4f} (R + {_TOL:.4f}) to clear polygon "
        f"discrepancy"
    )


def test_cylindrical_raised_innermost_buried():
    """Raised on outer wall: cutter's inner radial face must be inside
    the cylinder by at least the host-eps threshold."""
    R = 20.0
    host = cylinder(h=30, r=R, fn=48)
    bb = _cutter_bbox(host, label="X", on="outer_wall", relief=0.4, font_size=4)
    r_min = _min_radial_distance(bb)
    assert r_min <= R - _TOL, (
        f"cylindrical raised cutter min radial={r_min:.4f}; should be "
        f"inside R={R} by at least {_TOL:.4f}"
    )


# --- Conical ---


def test_conical_inset_overshoots_surface_at_mid():
    """Inset on a tapered cylinder. Check the mid-axial radial extent
    against the mid-radius."""
    host = cylinder(h=20, r1=10, r2=6, fn=48)  # r_mid = 8
    bb = _cutter_bbox(host, label="X", on="outer_wall", relief=-0.4, font_size=4)
    r_max = _max_radial_distance(bb)
    assert r_max >= 8 + _TOL, (
        f"conical inset cutter max radial={r_max:.4f}; should overshoot "
        f"mid-radius=8 by at least {_TOL:.4f}"
    )


# --- Rim arc ---


def test_rim_arc_inset_overshoots_rim_plane():
    """Inset on a Tube rim (the top face): the cutter's max-z must
    reach above the rim plane (z=10) by at least the host-eps threshold."""
    host = Tube(h=10, od=30, id=20)
    bb = _cutter_bbox(host, label="X", on="top", relief=-0.4, font_size=4)
    assert bb.max[2] >= 10 + _TOL, (
        f"rim inset cutter max-z={bb.max[2]:.4f}; should overshoot rim "
        f"(z=10) by at least {_TOL:.4f}"
    )


# --- Far-side overshoot stays small for inset (visible-depth invariant) ---


def test_inset_cut_depth_within_tight_tolerance_of_requested():
    """The far-side overshoot is small (TEXT_FAR_OVERSHOOT, 0.01mm) so the
    visible cut depth equals the requested relief plus at most that. This
    test guards against accidentally bumping the far-side overshoot too,
    which would make every cut deeper than requested."""
    relief = 0.4
    host = cube([20, 20, 10])
    bb = _cutter_bbox(host, label="X", on="top", relief=-relief, font_size=4)
    # Cutter's deepest point should be ~(10 - relief) inside the cube,
    # not noticeably deeper.
    deepest = 10 - bb.min[2]
    # Allow up to 0.05mm extra (well under typical FDM resolution).
    assert deepest <= relief + 0.05, (
        f"cut depth {deepest:.4f} exceeds requested relief {relief} by "
        f"more than 0.05mm — far-side overshoot may be too large"
    )
