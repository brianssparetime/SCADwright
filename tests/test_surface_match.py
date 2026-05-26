"""Unit tests for the surface-coincidence predicates in
``scadwright.ast._surface_match``.

Each predicate is exercised in isolation against constructed Anchors,
including the boundary cases the spec calls out (parallel-but-offset
axes, equal radii on different axes, touching-but-not-overlapping
axial extents).
"""

from __future__ import annotations

import math

import pytest

from scadwright.anchor import Anchor
from scadwright.ast._surface_match import (
    axial_extents_match_strict,
    axial_extents_overlap,
    axis_lines_coincide,
    compatible_inner_flags,
    conical_radii_match,
    cylindrical_radius_match,
    meridional_radii_match,
    planar_coincidence,
    spherical_match,
)


# Helpers


def _cyl(*, position, radius, length, axis=(0.0, 0.0, 1.0), normal=(1.0, 0.0, 0.0), inner=False):
    return Anchor(
        position=position,
        normal=normal,
        kind="cylindrical",
        axis=axis,
        radius=radius,
        length=length,
        inner=inner,
    )


def _cone(*, position, r1, r2, length, axis=(0.0, 0.0, 1.0), normal=(1.0, 0.0, 0.0), inner=False):
    return Anchor(
        position=position,
        normal=normal,
        kind="conical",
        axis=axis,
        r1=r1,
        r2=r2,
        length=length,
        inner=inner,
    )


def _sph(*, position, normal, axis_origin, radius, axis=(0.0, 0.0, 1.0),
         meridian_zero=(1.0, 0.0, 0.0), inner=False):
    return Anchor(
        position=position,
        normal=normal,
        kind="spherical",
        axis=axis,
        axis_origin=axis_origin,
        meridian_zero=meridian_zero,
        radius=radius,
        inner=inner,
    )


def _mer(*, position, normal, axis_origin, meridian_r, mid_r, end_r, meridian_s, length,
         axis=(0.0, 0.0, 1.0), meridian_zero=(1.0, 0.0, 0.0), inner=False):
    return Anchor(
        position=position,
        normal=normal,
        kind="meridional",
        axis=axis,
        axis_origin=axis_origin,
        meridian_zero=meridian_zero,
        meridian_r=meridian_r,
        mid_r=mid_r,
        end_r=end_r,
        meridian_s=meridian_s,
        length=length,
        inner=inner,
    )


def _planar(*, position, normal):
    return Anchor(position=position, normal=normal, kind="planar")


# axis_lines_coincide


def test_axis_lines_coincide_same_line_same_direction():
    a = _cyl(position=(5.0, 0.0, 7.5), radius=5.0, length=15.0)
    b = _cyl(position=(3.0, 0.0, 2.0), radius=3.0, length=4.0,
             normal=(-1.0, 0.0, 0.0), inner=True)
    assert axis_lines_coincide(a, b)


def test_axis_lines_coincide_same_line_opposite_direction():
    a = _cyl(position=(5.0, 0.0, 7.5), radius=5.0, length=15.0)
    b = _cyl(position=(3.0, 0.0, 2.0), radius=3.0, length=4.0,
             axis=(0.0, 0.0, -1.0), normal=(-1.0, 0.0, 0.0), inner=True)
    assert axis_lines_coincide(a, b)


def test_axis_lines_offset_parallel_does_not_coincide():
    """Two cylinders along z, offset in x. Axes are parallel but the
    lines are different."""
    a = _cyl(position=(5.0, 0.0, 7.5), radius=5.0, length=15.0)
    b = _cyl(position=(15.0, 0.0, 7.5), radius=5.0, length=15.0,
             normal=(1.0, 0.0, 0.0))
    # b's axis_origin is at (10, 0, 7.5) — not collinear with (0,0,*).
    assert not axis_lines_coincide(a, b)


def test_axis_lines_cross_axis_does_not_coincide():
    """One cylinder along z, one along y. Axes not parallel."""
    a = _cyl(position=(5.0, 0.0, 7.5), radius=5.0, length=15.0)
    b = _cyl(position=(0.0, 5.0, 0.0), radius=5.0, length=10.0,
             axis=(0.0, 1.0, 0.0), normal=(1.0, 0.0, 0.0))
    assert not axis_lines_coincide(a, b)


# axial_extents_overlap / axial_extents_match_strict


def test_axial_extents_overlap_concentric_same_length():
    a = _cyl(position=(5.0, 0.0, 5.0), radius=5.0, length=10.0)
    b = _cyl(position=(5.0, 0.0, 5.0), radius=5.0, length=10.0, inner=True)
    assert axial_extents_overlap(a, b)
    assert axial_extents_match_strict(a, b)


def test_axial_extents_overlap_concentric_partial():
    """Short inner cylinder inside long outer cylinder. Walls overlap
    on the inner's axial range."""
    outer = _cyl(position=(0.0, 0.0, 25.0), radius=5.0, length=50.0)
    inner = _cyl(position=(0.0, 0.0, 25.0), radius=5.0, length=20.0, inner=True)
    assert axial_extents_overlap(inner, outer)
    assert not axial_extents_match_strict(inner, outer)


def test_axial_extents_touching_does_not_overlap():
    """Two cylinders stacked end-to-end: z=0..10 and z=10..20. Their
    extents touch at z=10 but don't overlap — the cap-to-cap planar
    match should take over."""
    lower = _cyl(position=(5.0, 0.0, 5.0), radius=5.0, length=10.0)
    upper = _cyl(position=(5.0, 0.0, 15.0), radius=5.0, length=10.0)
    assert not axial_extents_overlap(lower, upper)
    assert not axial_extents_match_strict(lower, upper)


def test_axial_extents_disjoint_does_not_overlap():
    lower = _cyl(position=(5.0, 0.0, 5.0), radius=5.0, length=10.0)
    upper = _cyl(position=(5.0, 0.0, 25.0), radius=5.0, length=10.0)
    assert not axial_extents_overlap(lower, upper)


# cylindrical_radius_match


def test_cylindrical_radius_match_equal():
    a = _cyl(position=(5.0, 0.0, 5.0), radius=5.0, length=10.0)
    b = _cyl(position=(5.0, 0.0, 5.0), radius=5.0, length=10.0, inner=True)
    assert cylindrical_radius_match(a, b)


def test_cylindrical_radius_match_unequal():
    a = _cyl(position=(5.0, 0.0, 5.0), radius=5.0, length=10.0)
    b = _cyl(position=(3.0, 0.0, 5.0), radius=3.0, length=10.0, inner=True)
    assert not cylindrical_radius_match(a, b)


# conical_radii_match


def test_conical_radii_match_equal():
    a = _cone(position=(7.5, 0.0, 5.0), r1=5.0, r2=10.0, length=10.0)
    b = _cone(position=(7.5, 0.0, 5.0), r1=5.0, r2=10.0, length=10.0, inner=True)
    assert conical_radii_match(a, b)


def test_conical_radii_match_unequal_r1():
    a = _cone(position=(7.5, 0.0, 5.0), r1=5.0, r2=10.0, length=10.0)
    b = _cone(position=(7.5, 0.0, 5.0), r1=4.0, r2=10.0, length=10.0, inner=True)
    assert not conical_radii_match(a, b)


# spherical_match


def test_spherical_match_same_center_same_radius():
    a = _sph(position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, 1.0),
             axis_origin=(0.0, 0.0, 0.0), radius=5.0)
    b = _sph(position=(0.0, 0.0, -5.0), normal=(0.0, 0.0, 1.0),
             axis_origin=(0.0, 0.0, 0.0), radius=5.0, inner=True)
    assert spherical_match(a, b)


def test_spherical_match_different_centers():
    a = _sph(position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, 1.0),
             axis_origin=(0.0, 0.0, 0.0), radius=5.0)
    b = _sph(position=(0.0, 0.0, 15.0), normal=(0.0, 0.0, 1.0),
             axis_origin=(0.0, 0.0, 10.0), radius=5.0, inner=True)
    assert not spherical_match(a, b)


def test_spherical_match_different_radii():
    a = _sph(position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, 1.0),
             axis_origin=(0.0, 0.0, 0.0), radius=5.0)
    b = _sph(position=(0.0, 0.0, 3.0), normal=(0.0, 0.0, 1.0),
             axis_origin=(0.0, 0.0, 0.0), radius=3.0, inner=True)
    assert not spherical_match(a, b)


# meridional_radii_match


def test_meridional_radii_match_equal():
    common = dict(
        position=(8.0, 0.0, 10.0),
        normal=(1.0, 0.0, 0.0),
        axis_origin=(0.0, 0.0, 10.0),
        meridian_r=50.0, mid_r=8.0, end_r=5.0, meridian_s=1, length=20.0,
    )
    a = _mer(**common)
    b = _mer(**{**common, "inner": True, "normal": (-1.0, 0.0, 0.0)})
    assert meridional_radii_match(a, b)


def test_meridional_radii_match_different_mid_r():
    a_kwargs = dict(
        position=(8.0, 0.0, 10.0),
        normal=(1.0, 0.0, 0.0),
        axis_origin=(0.0, 0.0, 10.0),
        meridian_r=50.0, mid_r=8.0, end_r=5.0, meridian_s=1, length=20.0,
    )
    b_kwargs = {**a_kwargs, "mid_r": 7.0, "inner": True, "normal": (-1.0, 0.0, 0.0)}
    assert not meridional_radii_match(_mer(**a_kwargs), _mer(**b_kwargs))


# planar_coincidence


def test_planar_coincidence_basic():
    a = _planar(position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, 1.0))
    b = _planar(position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, -1.0))
    assert planar_coincidence(a, b)


def test_planar_coincidence_offset_position():
    a = _planar(position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, 1.0))
    b = _planar(position=(1.0, 0.0, 5.0), normal=(0.0, 0.0, -1.0))
    assert not planar_coincidence(a, b)


def test_planar_coincidence_same_direction_normals():
    """Two planar anchors at the same position with normals pointing
    the same way — same face from same side, not a contact."""
    a = _planar(position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, 1.0))
    b = _planar(position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, 1.0))
    assert not planar_coincidence(a, b)


# compatible_inner_flags


def test_compatible_inner_flags_one_each():
    a = _cyl(position=(5.0, 0.0, 5.0), radius=5.0, length=10.0, inner=False)
    b = _cyl(position=(5.0, 0.0, 5.0), radius=5.0, length=10.0, inner=True)
    assert compatible_inner_flags(a, b)


def test_compatible_inner_flags_both_outer():
    a = _cyl(position=(5.0, 0.0, 5.0), radius=5.0, length=10.0, inner=False)
    b = _cyl(position=(5.0, 0.0, 5.0), radius=5.0, length=10.0, inner=False)
    assert not compatible_inner_flags(a, b)


def test_compatible_inner_flags_both_inner():
    a = _cyl(position=(5.0, 0.0, 5.0), radius=5.0, length=10.0, inner=True)
    b = _cyl(position=(5.0, 0.0, 5.0), radius=5.0, length=10.0, inner=True)
    assert not compatible_inner_flags(a, b)


# Canonicalization: richer metadata wins regardless of insertion order


def test_canonical_anchors_prefers_richer_metadata_over_insertion_order():
    """Two anchors at the same canonical (kind, pos, normal, inner):
    one bbox-style (planar, no surface_params), one class-scope-style
    (planar with rim_radius/axis/meridian_zero). The richer one wins
    regardless of which was inserted first.
    """
    from scadwright.ast._surface_match import _canonical_anchors

    bare = Anchor(position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, 1.0), kind="planar")
    rich = Anchor(
        position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, 1.0), kind="planar",
        axis=(0.0, 0.0, 1.0), meridian_zero=(1.0, 0.0, 0.0),
        rim_radius=5.0,
    )
    # Insert bare first.
    canon = _canonical_anchors({"+z": bare, "top": rich})
    assert len(canon) == 1
    name, a = canon[0]
    assert a is rich
    # Reverse insertion order — same result.
    canon = _canonical_anchors({"top": rich, "+z": bare})
    assert len(canon) == 1
    name, a = canon[0]
    assert a is rich


def test_canonical_anchors_friendly_name_breaks_tie_when_richness_equal():
    """Two anchors with identical metadata: friendly name wins over
    axis-sign alias."""
    from scadwright.ast._surface_match import _canonical_anchors

    a1 = Anchor(position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, 1.0), kind="planar")
    a2 = Anchor(position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, 1.0), kind="planar")
    canon = _canonical_anchors({"+z": a1, "top": a2})
    assert canon[0][0] == "top"


# Proximity check used to gate the bridge hint in zero-match errors.


def test_planar_on_cylindrical_true_for_position_on_wall():
    """A planar anchor whose position lies on the cylindrical surface
    (correct radius from axis, axial offset within length) passes."""
    from scadwright.ast._surface_match import _planar_position_on_curved_surface
    cyl = Anchor(
        position=(10.0, 0.0, 10.0), normal=(1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), axis_origin=(0.0, 0.0, 10.0),
        radius=10.0, length=20.0, inner=False,
    )
    planar = Anchor(
        position=(10.0, 0.0, 5.0), normal=(-1.0, 0.0, 0.0), kind="planar",
    )
    assert _planar_position_on_curved_surface(planar, cyl) is True


def test_planar_on_cylindrical_false_for_wrong_radius():
    """Position correct axially but wrong distance from axis: rejected."""
    from scadwright.ast._surface_match import _planar_position_on_curved_surface
    cyl = Anchor(
        position=(10.0, 0.0, 10.0), normal=(1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), axis_origin=(0.0, 0.0, 10.0),
        radius=10.0, length=20.0, inner=False,
    )
    planar = Anchor(
        position=(5.0, 0.0, 5.0), normal=(-1.0, 0.0, 0.0), kind="planar",
    )
    assert _planar_position_on_curved_surface(planar, cyl) is False


def test_planar_on_cylindrical_false_for_outside_axial_extent():
    """Correct radius but beyond the wall's axial range: rejected."""
    from scadwright.ast._surface_match import _planar_position_on_curved_surface
    cyl = Anchor(
        position=(10.0, 0.0, 10.0), normal=(1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), axis_origin=(0.0, 0.0, 10.0),
        radius=10.0, length=20.0, inner=False,
    )
    planar = Anchor(
        position=(10.0, 0.0, 100.0), normal=(-1.0, 0.0, 0.0), kind="planar",
    )
    assert _planar_position_on_curved_surface(planar, cyl) is False


def test_planar_on_conical_uses_linear_interpolation_for_radius():
    """Cone with r1=5 at -length/2, r2=10 at +length/2. At axial 0 the
    expected radius is 7.5; a planar position at radius 7.5 hits."""
    from scadwright.ast._surface_match import _planar_position_on_curved_surface
    cone = Anchor(
        position=(7.5, 0.0, 0.0), normal=(1.0, 0.0, 0.0), kind="conical",
        axis=(0.0, 0.0, 1.0), axis_origin=(0.0, 0.0, 0.0),
        r1=5.0, r2=10.0, length=20.0, inner=False,
    )
    planar_on = Anchor(
        position=(7.5, 0.0, 0.0), normal=(-1.0, 0.0, 0.0), kind="planar",
    )
    planar_off = Anchor(
        position=(7.5, 0.0, 5.0), normal=(-1.0, 0.0, 0.0), kind="planar",
    )
    assert _planar_position_on_curved_surface(planar_on, cone) is True
    # At axial 5 the expected radius is 8.75, not 7.5.
    assert _planar_position_on_curved_surface(planar_off, cone) is False


def test_planar_on_spherical_true_for_position_at_radius():
    """Distance from sphere center equals radius: hits."""
    from scadwright.ast._surface_match import _planar_position_on_curved_surface
    sph = Anchor(
        position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, 1.0), kind="spherical",
        axis=(0.0, 0.0, 1.0), axis_origin=(0.0, 0.0, 0.0),
        meridian_zero=(1.0, 0.0, 0.0), radius=5.0, inner=False,
    )
    planar_on = Anchor(
        position=(3.0, 4.0, 0.0), normal=(-1.0, 0.0, 0.0), kind="planar",
    )
    planar_off = Anchor(
        position=(3.0, 4.0, 3.0), normal=(-1.0, 0.0, 0.0), kind="planar",
    )
    assert _planar_position_on_curved_surface(planar_on, sph) is True
    assert _planar_position_on_curved_surface(planar_off, sph) is False


# Planar near-miss candidates


def test_planar_near_miss_finds_offset_pair_with_matching_planes():
    """Two planar anchors with anti-parallel normals on the same plane
    but different reference positions: reported as near-miss with the
    offset magnitude."""
    from scadwright.ast._surface_match import planar_near_miss_candidates
    self_anchors = {
        "bottom": Anchor(
            position=(5.0, 0.0, 1.0), normal=(0.0, 0.0, -1.0), kind="planar",
        ),
    }
    host_anchors = {
        "top": Anchor(
            position=(0.0, 0.0, 1.0), normal=(0.0, 0.0, 1.0), kind="planar",
        ),
    }
    near = planar_near_miss_candidates(self_anchors, host_anchors)
    assert len(near) == 1
    s_name, h_name, offset = near[0]
    assert s_name == "bottom"
    assert h_name == "top"
    assert offset == pytest.approx(5.0)


def test_planar_near_miss_skips_coincident_positions():
    """Positions coincide → that's a real match, not a near-miss."""
    from scadwright.ast._surface_match import planar_near_miss_candidates
    self_anchors = {
        "bottom": Anchor(
            position=(0.0, 0.0, 1.0), normal=(0.0, 0.0, -1.0), kind="planar",
        ),
    }
    host_anchors = {
        "top": Anchor(
            position=(0.0, 0.0, 1.0), normal=(0.0, 0.0, 1.0), kind="planar",
        ),
    }
    assert planar_near_miss_candidates(self_anchors, host_anchors) == []


def test_planar_near_miss_skips_when_planes_dont_coincide():
    """Anti-parallel normals but the position displacement has an
    out-of-plane component: not a near-miss, just truly no contact."""
    from scadwright.ast._surface_match import planar_near_miss_candidates
    self_anchors = {
        "bottom": Anchor(
            position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, -1.0), kind="planar",
        ),
    }
    host_anchors = {
        "top": Anchor(
            position=(0.0, 0.0, 1.0), normal=(0.0, 0.0, 1.0), kind="planar",
        ),
    }
    assert planar_near_miss_candidates(self_anchors, host_anchors) == []


# diagnose_match_failure — explicit-form match-failure reasons


def test_diagnose_kind_mismatch_planar_self_curved_host():
    """Planar self + curved host → bridge case suggestion."""
    from scadwright.ast._surface_match import diagnose_match_failure
    planar = Anchor(position=(0.0, 0.0, 0.0), normal=(0.0, 0.0, -1.0), kind="planar")
    cyl = Anchor(
        position=(10.0, 0.0, 10.0), normal=(1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), axis_origin=(0.0, 0.0, 10.0),
        radius=10.0, length=20.0, inner=False,
    )
    reasons = diagnose_match_failure(planar, cyl)
    assert len(reasons) == 1
    assert "bridge case" in reasons[0]
    assert "bridge=True" in reasons[0]


def test_diagnose_planar_near_miss_suggests_attach_fuse():
    """Planar+planar same plane, positions offset → attach(fuse=True)."""
    from scadwright.ast._surface_match import diagnose_match_failure
    a = Anchor(position=(5.0, 0.0, 1.0), normal=(0.0, 0.0, -1.0), kind="planar")
    b = Anchor(position=(0.0, 0.0, 1.0), normal=(0.0, 0.0, 1.0), kind="planar")
    reasons = diagnose_match_failure(a, b)
    assert any("planar positions don't coincide" in r for r in reasons)
    assert any("attach(host, fuse=True)" in r for r in reasons)


def test_diagnose_planar_normals_not_opposed():
    """Both normals +Z (not anti-parallel) → flagged."""
    from scadwright.ast._surface_match import diagnose_match_failure
    a = Anchor(position=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0), kind="planar")
    b = Anchor(position=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0), kind="planar")
    reasons = diagnose_match_failure(a, b)
    assert any("normals don't oppose" in r for r in reasons)


def test_diagnose_cylindrical_axial_extent_overlap_failure():
    """Axes coincide, radii match, inner flags compat, axial extents
    don't overlap → axial-extent reason."""
    from scadwright.ast._surface_match import diagnose_match_failure
    a = Anchor(
        position=(5.0, 0.0, 100.0), normal=(1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=5.0, length=10.0, inner=False,
    )
    b = Anchor(
        position=(5.0, 0.0, 10.0), normal=(-1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=5.0, length=20.0, inner=True,
    )
    reasons = diagnose_match_failure(a, b)
    assert any("axial extents don't overlap" in r for r in reasons)


def test_diagnose_cylindrical_radius_mismatch():
    from scadwright.ast._surface_match import diagnose_match_failure
    a = Anchor(
        position=(5.0, 0.0, 5.0), normal=(1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=5.0, length=10.0, inner=False,
    )
    b = Anchor(
        position=(3.0, 0.0, 5.0), normal=(-1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=3.0, length=10.0, inner=True,
    )
    reasons = diagnose_match_failure(a, b)
    assert any("radii differ" in r for r in reasons)


def test_diagnose_cylindrical_inner_flag_mismatch():
    """Both anchors inner=False on different cylindrical surfaces:
    the inner-flag rule message fires. (When the surfaces literally
    coincide, the same-side-wall shortcut kicks in instead — see
    test_diagnose_same_side_wall_suggests_union.)
    """
    from scadwright.ast._surface_match import diagnose_match_failure
    a = Anchor(
        position=(5.0, 0.0, 5.0), normal=(1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=5.0, length=10.0, inner=False,
    )
    b = Anchor(
        position=(3.0, 0.0, 5.0), normal=(1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=3.0, length=10.0, inner=False,
    )
    reasons = diagnose_match_failure(a, b)
    assert any("inner=False" in r for r in reasons)


def test_diagnose_spherical_center_mismatch():
    from scadwright.ast._surface_match import diagnose_match_failure
    a = Anchor(
        position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, 1.0), kind="spherical",
        axis=(0.0, 0.0, 1.0), axis_origin=(0.0, 0.0, 0.0),
        meridian_zero=(1.0, 0.0, 0.0), radius=5.0, inner=False,
    )
    b = Anchor(
        position=(0.0, 0.0, 15.0), normal=(0.0, 0.0, 1.0), kind="spherical",
        axis=(0.0, 0.0, 1.0), axis_origin=(0.0, 0.0, 10.0),
        meridian_zero=(1.0, 0.0, 0.0), radius=5.0, inner=True,
    )
    reasons = diagnose_match_failure(a, b)
    assert any("sphere centers don't coincide" in r for r in reasons)


def test_diagnose_multiple_failures_listed_together():
    """Mismatch in multiple ways: each reason appears.

    Both anchors are on the world Z axis (a at the +x meridian, b at
    the -x meridian, each consistent with its own radius). They share
    inner=False (so flags are incompatible), radii differ, and axial
    extents are far apart — three failures in one pair.
    """
    from scadwright.ast._surface_match import diagnose_match_failure
    a = Anchor(
        position=(5.0, 0.0, 100.0), normal=(1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=5.0, length=10.0, inner=False,
    )
    b = Anchor(
        position=(-3.0, 0.0, 5.0), normal=(-1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=3.0, length=10.0, inner=False,
    )
    reasons = diagnose_match_failure(a, b)
    assert any("inner=False" in r for r in reasons)
    assert any("radii differ" in r for r in reasons)
    assert any("axial extents don't overlap" in r for r in reasons)


# same_side_wall_candidates / _is_same_curved_surface


def test_is_same_curved_surface_cylindrical_identical_surface():
    """Two cylindrical anchors at the same axis, radius, and axial
    extent: same surface, regardless of inner flag."""
    from scadwright.ast._surface_match import _is_same_curved_surface
    a = Anchor(
        position=(5.0, 0.0, 5.0), normal=(1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=5.0, length=10.0, inner=False,
    )
    b = Anchor(
        position=(5.0, 0.0, 5.0), normal=(1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=5.0, length=10.0, inner=False,
    )
    assert _is_same_curved_surface(a, b) is True


def test_is_same_curved_surface_cylindrical_different_radius():
    from scadwright.ast._surface_match import _is_same_curved_surface
    a = Anchor(
        position=(5.0, 0.0, 5.0), normal=(1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=5.0, length=10.0, inner=False,
    )
    b = Anchor(
        position=(3.0, 0.0, 5.0), normal=(1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=3.0, length=10.0, inner=False,
    )
    assert _is_same_curved_surface(a, b) is False


def test_is_same_curved_surface_spherical_coincident():
    from scadwright.ast._surface_match import _is_same_curved_surface
    a = Anchor(
        position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, 1.0), kind="spherical",
        axis=(0.0, 0.0, 1.0), axis_origin=(0.0, 0.0, 0.0),
        meridian_zero=(1.0, 0.0, 0.0), radius=5.0, inner=False,
    )
    b = Anchor(
        position=(5.0, 0.0, 0.0), normal=(1.0, 0.0, 0.0), kind="spherical",
        axis=(0.0, 0.0, 1.0), axis_origin=(0.0, 0.0, 0.0),
        meridian_zero=(1.0, 0.0, 0.0), radius=5.0, inner=False,
    )
    assert _is_same_curved_surface(a, b) is True


def test_same_side_wall_candidates_telescoping_tubes():
    """Two same-OD tubes overlapping axially: outer walls describe
    the same surface from the same side."""
    from scadwright.anchor import get_node_anchors
    from scadwright.ast._surface_match import same_side_wall_candidates
    from scadwright.shapes import Tube
    lower = Tube(h=20, od=20, id=10)
    upper = Tube(h=20, od=20, id=10).up(10)
    candidates = same_side_wall_candidates(
        get_node_anchors(upper), get_node_anchors(lower),
    )
    # Outer walls match same-side; inner walls (both inner=True) also match.
    outer = [c for c in candidates if c[0] == "outer_wall" and c[1] == "outer_wall"]
    inner = [c for c in candidates if c[0] == "inner_wall" and c[1] == "inner_wall"]
    assert len(outer) == 1
    assert outer[0][2] == "cylindrical"
    assert outer[0][3] is False  # both convex-outer
    assert len(inner) == 1
    assert inner[0][3] is True   # both concave-inner


def test_same_side_wall_candidates_empty_when_one_inner_one_outer():
    """The standard concentric case (one inner, one outer): not a
    same-side situation, real fuse match instead."""
    from scadwright.anchor import get_node_anchors
    from scadwright.ast._surface_match import same_side_wall_candidates
    from scadwright.shapes import Tube
    barrel = Tube(h=50, od=20, id=10)
    holder = Tube(h=8, od=10, id=4).up(20)  # od=10 matches barrel.id=10
    candidates = same_side_wall_candidates(
        get_node_anchors(holder), get_node_anchors(barrel),
    )
    # holder.outer_wall (inner=False) vs barrel.inner_wall (inner=True):
    # different sides, so not a same-side candidate.
    assert candidates == []


def test_diagnose_same_side_wall_suggests_union():
    """Two cylindrical anchors with identical surface and same inner
    flag → diagnose_match_failure returns the union() hint instead
    of the bare 'inner=False' rule statement."""
    from scadwright.ast._surface_match import diagnose_match_failure
    a = Anchor(
        position=(5.0, 0.0, 5.0), normal=(1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=5.0, length=10.0, inner=False,
    )
    b = Anchor(
        position=(5.0, 0.0, 5.0), normal=(1.0, 0.0, 0.0), kind="cylindrical",
        axis=(0.0, 0.0, 1.0), radius=5.0, length=10.0, inner=False,
    )
    reasons = diagnose_match_failure(a, b)
    assert len(reasons) == 1
    assert "same cylindrical surface from the same side" in reasons[0]
    assert "union(self, host)" in reasons[0]
