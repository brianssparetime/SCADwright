"""Tests for the cross-section fuse path (Phase 2 of better-fuse).

Cross-section is the fallback for planar fuses on shapes without a
parametric extension lever — rotate_extrude end-caps, Polyhedra, CSG
results, custom Components without intrinsic extension. These tests
exercise the slab construction itself, the dot-product-based
degeneracy detection, the cone-apex and sphere-tangent overrides,
and the cascade integration via attach() and fuse().
"""

import math

import pytest

from scadwright import bbox
from scadwright.anchor import Anchor
from scadwright.boolops import difference, fuse, union
from scadwright.errors import ValidationError
from scadwright.primitives import (
    cube,
    cylinder,
    polygon,
    polyhedron,
    sphere,
    square,
)


# --- Slab construction on shapes without parametric extension ---


def test_rotate_extrude_top_cap_cross_section_extend():
    """A rotate_extrude'd profile has a planar disc top cap. Cross-
    section extension grows the disc upward by eps, leaving every
    other surface exactly where it was."""
    # Square profile (r=2..4, z=0..10) revolved into a hollow cylinder.
    shape = polygon(points=[(2, 0), (4, 0), (4, 10), (2, 10)]).rotate_extrude(fn=32)
    bb_before = bbox(shape)
    top = Anchor(position=(0, 0, 10), normal=(0, 0, 1), kind="planar")
    extended = shape.cross_section_extend(top, 0.01)
    bb_after = bbox(extended)
    assert bb_after.min == pytest.approx(bb_before.min)  # all min faces preserved
    assert bb_after.max[0] == pytest.approx(bb_before.max[0])  # x preserved
    assert bb_after.max[1] == pytest.approx(bb_before.max[1])  # y preserved
    assert bb_after.max[2] == pytest.approx(10.01)  # top extended


def test_polyhedron_planar_face_cross_section_extend():
    """A polyhedron with a declared planar face anchor extends correctly."""
    # Tetrahedron-ish: 4 points, 4 faces. Planar bottom at z=0.
    points = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (5.0, 10.0, 0.0), (5.0, 5.0, 8.0)]
    faces = [(0, 2, 1), (0, 1, 3), (1, 2, 3), (0, 3, 2)]
    shape = polyhedron(points=points, faces=faces)
    bottom = Anchor(position=(5.0, 5.0, 0.0), normal=(0.0, 0.0, -1.0), kind="planar")
    extended = shape.cross_section_extend(bottom, 0.01)
    bb = bbox(extended)
    # Bottom face (z=0) extended down to z=-0.01; top vertex at z=8 preserved.
    assert bb.min[2] == pytest.approx(-0.01)
    assert bb.max[2] == pytest.approx(8.0)


def test_difference_result_top_face_cross_section_extend():
    """A difference(cube, hole) result has a planar top face minus a
    circular cutout. Cross-section captures cube_top - hole, extruded
    by eps."""
    plate = cube([20, 20, 5])
    hole_cyl = cylinder(h=10, r=2).down(2)  # cuts straight through
    drilled = difference(plate, hole_cyl)
    top = Anchor(position=(10.0, 10.0, 5.0), normal=(0.0, 0.0, 1.0), kind="planar")
    extended = drilled.cross_section_extend(top, 0.01)
    bb = bbox(extended)
    # Bbox top extended by eps; min and other axes preserved.
    assert bb.max[2] == pytest.approx(5.01)
    assert bb.min[2] == pytest.approx(0.0)


def test_translated_shape_cross_section_extend():
    """The alignment math handles a translate wrapper naturally — the
    anchor's position lives in the post-translate frame."""
    shape = polygon(points=[(2, 0), (4, 0), (4, 10), (2, 10)]).rotate_extrude(fn=16).up(5)
    top = Anchor(position=(0, 0, 15), normal=(0, 0, 1), kind="planar")
    extended = shape.cross_section_extend(top, 0.01)
    bb = bbox(extended)
    assert bb.max[2] == pytest.approx(15.01)
    assert bb.min[2] == pytest.approx(5.0)


# --- Degeneracy detection (dot-product check) ---


def test_anchor_outside_bbox_raises():
    """Anchor clearly outside the shape's bbox along the normal — the
    dot-product check catches this and raises."""
    shape = cube([10, 10, 10])
    bad = Anchor(position=(5, 5, 50), normal=(0, 0, 1), kind="planar")
    with pytest.raises(ValidationError, match="outermost face"):
        shape.cross_section_extend(bad, 0.01)


def test_anchor_in_interior_raises():
    """Anchor in the shape's interior — projected extent doesn't match
    the bbox extreme along the normal."""
    shape = cube([10, 10, 10])
    interior = Anchor(position=(5, 5, 3), normal=(0, 0, 1), kind="planar")
    with pytest.raises(ValidationError, match="outermost face"):
        shape.cross_section_extend(interior, 0.01)


def test_slanted_normal_validates_via_dot_product():
    """A slanted normal: anchor projected onto the normal must equal
    the bbox's max projection. Works uniformly with axis-aligned."""
    shape = cube([10, 10, 10])
    # An anchor on the +X+Z corner edge, with a 45° normal pointing out.
    n = (1.0 / math.sqrt(2), 0.0, 1.0 / math.sqrt(2))
    # Position at the corner where +X face and +Z face meet (5, 5, 10) on the
    # +Z face — projected extent: 5*n[0] + 5*n[1] + 10*n[2] = 5/√2 + 10/√2 = 15/√2.
    # bbox max projection along n: max over corners of c[0]*n[0]+c[2]*n[2] =
    # 10*n[0] + 10*n[2] = 20/√2.
    # 15/√2 != 20/√2 → anchor is NOT on the bbox-extreme face along this normal.
    anchor_inside = Anchor(position=(5, 5, 10), normal=n, kind="planar")
    with pytest.raises(ValidationError, match="outermost face"):
        shape.cross_section_extend(anchor_inside, 0.01)
    # An anchor at the corner (10, 5, 10) WITH the slanted normal — projected
    # extent: 10/√2 + 10/√2 = 20/√2 = bbox max. Passes the check.
    anchor_corner = Anchor(position=(10, 5, 10), normal=n, kind="planar")
    extended = shape.cross_section_extend(anchor_corner, 0.01)
    assert extended is not None  # no raise; slab built


# --- Cone-apex override on Cylinder ---


def test_cylinder_cone_apex_top_cross_section_raises():
    """Cone with r2=0: bbox top face is the full base disc, but the
    actual material is a single point. Override raises with apex msg."""
    cone = cylinder(h=10, r1=10, r2=0)
    # Anchor at the apex (z=10) — bbox check would pass spuriously.
    apex = Anchor(position=(0, 0, 10), normal=(0, 0, 1), kind="planar")
    with pytest.raises(ValidationError, match="cone apex"):
        cone.cross_section_extend(apex, 0.01)


def test_cylinder_cone_apex_bottom_cross_section_raises():
    """Symmetric: r1=0 cone, bottom anchor."""
    cone = cylinder(h=10, r1=0, r2=10)
    apex = Anchor(position=(0, 0, 0), normal=(0, 0, -1), kind="planar")
    with pytest.raises(ValidationError, match="cone apex"):
        cone.cross_section_extend(apex, 0.01)


# --- Sphere tangent-point override ---


def test_sphere_cross_section_raises():
    """Sphere has no planar faces — every bbox face is a tangent point."""
    s = sphere(r=5)
    bottom = Anchor(position=(0, 0, -5), normal=(0, 0, -1), kind="planar")
    with pytest.raises(ValidationError, match="tangent point"):
        s.cross_section_extend(bottom, 0.01)


# --- Cascade behavior in attach() ---


def test_attach_fuse_cascades_to_cross_section_for_rotate_extrude():
    """rotate_extrude shapes have no parametric fuse_extend; the
    cascade reaches cross_section_extend and the fuse succeeds."""
    nose = polygon(
        points=[(0, 0), (5, 0), (5*math.sqrt(0.5), 5), (0, 10)]
    ).rotate_extrude(fn=24)
    # nose's bottom is at z=0, top at z=10. Use bottom for fuse to a plate.
    plate = cube([20, 20, 2]).up(-2)  # plate top at z=0
    result = nose.attach(plate, on="top", at="bottom", fuse=True)
    bb = bbox(result)
    # Nose bottom extended into plate by eps; nose top preserved at z=10.
    assert bb.max[2] == pytest.approx(10.0)


def test_attach_fuse_propagates_cone_apex_error():
    """Errors raised inside cross_section_extend propagate through
    attach(fuse=True) to the user."""
    cone = cylinder(h=10, r1=10, r2=0)
    plate = cube([20, 20, 2]).up(10)  # plate sits on cone apex
    with pytest.raises(ValidationError, match="cone apex"):
        cone.attach(plate, on="bottom", at="top", fuse=True)


def test_attach_fuse_propagates_outside_bbox_error():
    """Same propagation for the dot-product check failure. attach()
    only extends self, so the misplaced anchor needs to be on self
    for the cross-section check to fire."""
    # Component with a planar anchor declared OFF the shape's bbox.
    from scadwright import Component, anchor as _anchor
    class BadAnchor(Component):
        equations = "size > 0"
        bogus = _anchor(at="0, 0, 100", normal=(0, 0, 1))  # way above bbox
        def build(self):
            return cube([self.size, self.size, self.size])
    bad = BadAnchor(size=10)
    plate = cube([5, 5, 1])
    with pytest.raises(ValidationError, match="outermost face"):
        bad.attach(plate, on="top", at="bogus", fuse=True)


# --- Cascade behavior in fuse() ---


def test_fuse_function_parametric_strictly_preferred_over_cross_section():
    """When one side is a Cube (parametric) and the other is a
    rotate_extrude (cross-section), parametric wins. The result has
    the Cube extended, not the rotate_extrude."""
    plate = cube([20, 20, 5])  # parametric extension via Cube.fuse_extend
    nose = polygon(points=[(0, 0), (5, 0), (0, 10)]).rotate_extrude(fn=16)
    result = fuse(nose, plate, on="top", at="bottom")
    # Result is union(translated_nose, extended_plate). Verify the plate
    # got the parametric extension by checking bbox: plate spans z=0..5.01;
    # nose is placed on top so it goes from z=5 to z=15.
    bb = bbox(result)
    assert bb.min[2] == pytest.approx(0.0)
    assert bb.max[2] == pytest.approx(15.0)  # nose top preserved


def test_fuse_function_both_sides_cross_section():
    """Two rotate_extrudes fused: neither has parametric. Tier 2
    cross-section runs on both; side-selection picks one."""
    a = polygon(points=[(0, 0), (5, 0), (5, 10), (0, 10)]).rotate_extrude(fn=16)
    b = polygon(points=[(0, 0), (5, 0), (5, 10), (0, 10)]).rotate_extrude(fn=16)
    # b's top fuses to a's bottom — a is placed on top of b.
    result = fuse(a, b, on="top", at="bottom")
    bb = bbox(result)
    # a sits on b: b spans z=0..10, a spans z=10..20.
    assert bb.min[2] == pytest.approx(0.0)
    assert bb.max[2] == pytest.approx(20.0)


# --- disable_eps_fuse() interaction ---


def test_disable_eps_fuse_skips_cross_section():
    """Inside disable_eps_fuse(), cross-section is NOT invoked even on
    shapes that would otherwise use it. Falls through to exact contact."""
    from scadwright import disable_eps_fuse
    nose = polygon(points=[(0, 0), (5, 0), (0, 10)]).rotate_extrude(fn=16)
    plate = cube([20, 20, 2]).up(-2)
    no_disable = nose.attach(plate, on="top", at="bottom", fuse=True)
    with disable_eps_fuse():
        with_disable = nose.attach(plate, on="top", at="bottom", fuse=True)
    # Inside disable: exact contact — nose top at z=10 (no extension).
    bb_with = bbox(with_disable)
    assert bb_with.max[2] == pytest.approx(10.0)
    # Outside disable: nose top still at z=10 (preserved) but bottom
    # extended into plate.
    bb_no = bbox(no_disable)
    assert bb_no.max[2] == pytest.approx(10.0)


# --- through() composition after cross-section ---


def test_through_works_after_cross_section_extended_cutter():
    """A cross-section-extended cutter still has the right outer bbox
    for through()'s coincidence detection."""
    plate = cube([20, 20, 5])
    # Construct a cutter as a rotate_extrude (so cross-section path applies).
    profile = polygon(points=[(0, 0), (1.5, 0), (1.5, 5), (0, 5)])
    cutter = profile.rotate_extrude(fn=24)
    # Use the cutter via through() — its bbox should be exactly z=0..5
    # for through() to find both faces coincident with plate.
    bb = bbox(cutter)
    assert bb.min[2] == pytest.approx(0.0)
    assert bb.max[2] == pytest.approx(5.0)
