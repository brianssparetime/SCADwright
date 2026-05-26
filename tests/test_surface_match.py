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
