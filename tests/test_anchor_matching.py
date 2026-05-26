"""Integration tests for ``find_contacts`` and ``cross_kind_bridge_candidates``.

These exercise the match engine against real ``get_node_anchors``
outputs from the standard-library shapes, where anchor declarations
follow the framework's conventions (correct normals on inner walls,
etc.).
"""

from __future__ import annotations

import pytest

from scadwright.anchor import get_node_anchors
from scadwright.ast._surface_match import (
    cross_kind_bridge_candidates,
    find_contacts,
)
from scadwright.primitives import cube, cylinder, sphere
from scadwright.shapes import Funnel, Tube


# Planar contact (Cube on top of Cube)


def test_planar_cube_on_cube_finds_one_contact():
    """A Cube placed on top of a same-sized Cube has exactly one planar
    contact: self.bottom ↔ host.top. Centered fixtures so face-center
    positions coincide."""
    plate = cube([10, 10, 2], center=True)  # bbox z=-1..1
    peg = cube([10, 10, 5], center=True).up(3.5)  # bbox z=1..6; bottom at z=1
    matches = find_contacts(get_node_anchors(peg), get_node_anchors(plate))
    assert len(matches) == 1
    m = matches[0]
    assert m.kind == "planar"
    assert m.concentric is False
    assert m.self_name == "bottom"
    assert m.host_name == "top"


def test_planar_cubes_no_overlap_zero_matches():
    """Cubes separated in space have no coincident faces."""
    a = cube([5, 5, 5])
    b = cube([5, 5, 5]).up(20)
    matches = find_contacts(get_node_anchors(a), get_node_anchors(b))
    assert matches == []


# Concentric cylindrical contact (Tube inside Tube)


def test_concentric_tubes_match_on_walls():
    """A short Tube concentric inside a longer Tube. The holder's
    outer_wall matches the host's inner_wall (cylindrical, axis Z,
    matching radius, one inner=True one inner=False, overlapping
    axial extent)."""
    barrel = Tube(h=50, od=20, id=10)
    holder = Tube(h=8, od=10, id=4).up(20)  # od matches barrel id
    matches = find_contacts(get_node_anchors(holder), get_node_anchors(barrel))
    cyl_matches = [m for m in matches if m.kind == "cylindrical"]
    assert len(cyl_matches) == 1
    m = cyl_matches[0]
    assert m.concentric is True
    assert m.self_name == "outer_wall"
    assert m.host_name == "inner_wall"


def test_concentric_tubes_no_cap_match_when_axial_offset():
    """Holder positioned mid-bore; its top/bottom planar caps don't
    coincide with the barrel's top/bottom. Only the wall match
    should appear."""
    barrel = Tube(h=50, od=20, id=10)
    holder = Tube(h=8, od=10, id=4).up(20)
    matches = find_contacts(get_node_anchors(holder), get_node_anchors(barrel))
    kinds = {m.kind for m in matches}
    assert "cylindrical" in kinds
    assert "planar" not in kinds


# End-to-end cylindrical: cap-to-cap planar, NOT wall


def test_end_to_end_tubes_match_at_caps_not_walls():
    """Two tubes stacked at matching OD: top cap of lower ↔ bottom cap
    of upper. Walls share an edge, not a surface — the axial-extent
    overlap rule rejects the wall match."""
    lower = Tube(h=20, od=20, id=10)
    upper = Tube(h=20, od=20, id=10).up(20)  # bottom at z=20 = top of lower
    matches = find_contacts(get_node_anchors(upper), get_node_anchors(lower))
    # Expect exactly one planar match: upper.bottom ↔ lower.top.
    planar = [m for m in matches if m.kind == "planar"]
    cylindrical = [m for m in matches if m.kind == "cylindrical"]
    assert len(planar) == 1
    assert planar[0].self_name == "bottom"
    assert planar[0].host_name == "top"
    assert cylindrical == []


# Concentric conical (Funnel inside Funnel)


def test_concentric_funnels_match_on_conical_walls():
    """Outer Funnel and inner Funnel sized so the inner's outer_wall
    matches the outer's inner_wall. Same axial range, matching r1/r2
    (strict)."""
    outer = Funnel(h=20, thk=2, bot_od=20, top_od=30)  # bot_id=16, top_id=26
    inner = Funnel(h=20, thk=2, bot_od=16, top_od=26)  # inner.outer_wall == outer.inner_wall
    matches = find_contacts(get_node_anchors(inner), get_node_anchors(outer))
    conical = [m for m in matches if m.kind == "conical"]
    assert len(conical) == 1
    assert conical[0].concentric is True
    assert conical[0].self_name == "outer_wall"
    assert conical[0].host_name == "inner_wall"


# Concentric spherical


def test_concentric_spheres_match_on_surface():
    """Two coincident spheres (one inside the other would need
    inner=True on the inside-facing surface — Sphere primitive
    doesn't declare an inner anchor today). Two spheres at the same
    position with same radius produce face-anchor matches with
    compatible_inner_flags = False (both outer), so no match."""
    a = sphere(r=5)
    b = sphere(r=5)
    matches = find_contacts(get_node_anchors(a), get_node_anchors(b))
    # Both spheres' face anchors are inner=False (no inner declared
    # on the primitive); compatible_inner_flags rejects them.
    spherical = [m for m in matches if m.kind == "spherical"]
    assert spherical == []


def test_sphere_inside_spherical_shell_matches():
    """Sphere primitive (outer surface, inner=False) fits inside a
    SphericalShell whose inner_wall has the matching radius. The
    SphericalShell is the producer of inner-spherical anchors."""
    from scadwright.shapes import SphericalShell
    inner = sphere(d=14)
    shell = SphericalShell(od=20, id=14)
    matches = find_contacts(get_node_anchors(inner), get_node_anchors(shell))
    spherical = [m for m in matches if m.kind == "spherical"]
    assert len(spherical) == 1
    m = spherical[0]
    assert m.concentric is True
    assert m.host_name == "inner_wall"


# Cross-kind bridge candidates


def test_cross_kind_bridge_candidates_planar_peg_against_cylindrical_wall():
    """A peg with planar bottom + cylindrical host (Tube outer_wall):
    cross_kind_bridge_candidates lists the pair so the dispatcher can
    point at attach(bridge=True)."""
    peg = cube([2, 2, 5])
    tube = Tube(h=20, od=20, id=10)
    candidates = cross_kind_bridge_candidates(
        get_node_anchors(peg), get_node_anchors(tube)
    )
    # bbox-face planar anchors on the cube (6 unique) ×
    # outer_wall + inner_wall on the tube (2). Expect both surfaces.
    assert any(c[4] is False for c in candidates)  # outer host
    assert any(c[4] is True for c in candidates)   # inner host


def test_cross_kind_bridge_candidates_empty_when_no_curved_host():
    """Cross-kind hint shouldn't fire when neither side is curved."""
    a = cube([5, 5, 5])
    b = cube([10, 10, 2])
    candidates = cross_kind_bridge_candidates(
        get_node_anchors(a), get_node_anchors(b)
    )
    assert candidates == []


# Determinism


def test_find_contacts_sorted_by_name():
    """Results are sorted by (self_name, host_name) for stable error
    messages and tie-breaks."""
    barrel = Tube(h=50, od=20, id=10)
    holder = Tube(h=8, od=10, id=4).up(20)
    matches = find_contacts(get_node_anchors(holder), get_node_anchors(barrel))
    names = [(m.self_name, m.host_name) for m in matches]
    assert names == sorted(names)
