"""Tests for mechanical subpackage: bearings, pulleys, shafts, clamps, grommets."""

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import (
    Bearing,
    BearingSpec,
    DShaft,
    GT2Pulley,
    Grommet,
    HTDPulley,
    KeyedShaft,
    TubeClamp,
)


# --- Bearing ---


def test_bearing_608():
    b = Bearing.of("608")
    bb = bbox(b)
    assert bb.size[0] == pytest.approx(22.0, abs=0.5)  # od
    assert bb.size[2] == pytest.approx(7.0, abs=0.1)   # width


def test_bearing_custom_dims():
    b = Bearing(spec=BearingSpec(id=10, od=30, width=9))
    bb = bbox(b)
    assert bb.size[0] == pytest.approx(30.0, abs=0.5)


def test_bearing_custom_dims_publishes_all_attrs():
    """Custom-spec Bearings expose id/od/width as instance attrs."""
    b = Bearing(spec=BearingSpec(id=10, od=30, width=9))
    assert b.id == 10
    assert b.od == 30
    assert b.width == 9
    bb = bbox(b)
    assert bb.size[2] == pytest.approx(9.0, abs=0.1)


def test_bearing_unknown_series_raises():
    with pytest.raises(ValidationError, match="unknown bearing series"):
        Bearing.of("9999")


def test_bearing_publishes_dims():
    b = Bearing.of("625")
    assert b.id == 5
    assert b.od == 16
    assert b.width == 5


# --- GT2Pulley ---


def test_gt2_pulley_builds():
    p = GT2Pulley(teeth=20, bore_d=5, belt_width=6)
    scad = emit_str(p)
    assert "cylinder" in scad


def test_gt2_pulley_publishes_pitch_d():
    p = GT2Pulley(teeth=20, bore_d=5, belt_width=6)
    assert p.pitch_d > 0


def test_gt2_too_few_teeth_raises():
    with pytest.raises(ValidationError, match="teeth: must be >= 10"):
        GT2Pulley(teeth=5, bore_d=3, belt_width=6)


# --- HTDPulley ---


def test_htd_pulley_builds():
    p = HTDPulley(teeth=20, bore_d=8, belt_width=15, pitch=5)
    scad = emit_str(p)
    assert "cylinder" in scad


# --- DShaft ---


def test_dshaft_builds():
    s = DShaft(d=5, flat_depth=0.5)
    scad = emit_str(s)
    assert "difference" in scad


def test_dshaft_bbox():
    s = DShaft(d=10, flat_depth=1)
    bb = bbox(s)
    # Y extent is the full diameter (flat is on x-side only).
    assert bb.size[1] == pytest.approx(10.0, abs=0.1)
    # X extent is still the full circle AABB (flat doesn't reduce the
    # bounding box since the opposite side of the circle still reaches).
    assert bb.size[0] == pytest.approx(10.0, abs=0.1)


# --- KeyedShaft ---


def test_keyed_shaft_builds():
    s = KeyedShaft(d=10, key_w=3, key_h=1.5)
    scad = emit_str(s)
    assert "difference" in scad


# --- TubeClamp ---


def test_tube_clamp_round_saddle_default():
    c = TubeClamp(tube_d=12, clamp_length=20, wall_thk=3, bolt_offset=5)
    bb = bbox(c)
    # body height = wall_thk + tube_d = 15
    assert bb.size[2] == pytest.approx(15.0, abs=0.5)
    # length along tube axis
    assert bb.size[0] == pytest.approx(20.0, abs=0.5)
    # base sits at z=0
    assert bb.min[2] == pytest.approx(0.0)


def test_tube_clamp_rectangular_square_shorthand():
    """tube_w alone defaults tube_h to tube_w (square)."""
    c = TubeClamp(tube_w=10, clamp_length=20, wall_thk=3, bolt_offset=5)
    assert c.tube_h == pytest.approx(10.0)
    bb = bbox(c)
    # body height = wall_thk + tube_h = 13
    assert bb.size[2] == pytest.approx(13.0, abs=0.5)


def test_tube_clamp_rectangular_explicit_h():
    c = TubeClamp(tube_w=10, tube_h=15, clamp_length=20, wall_thk=3, bolt_offset=5)
    assert c.tube_h == pytest.approx(15.0)
    bb = bbox(c)
    # body height = wall_thk + tube_h = 18
    assert bb.size[2] == pytest.approx(18.0, abs=0.5)


def test_tube_clamp_requires_one_cross_section():
    with pytest.raises(ValidationError):
        TubeClamp(clamp_length=20, wall_thk=3, bolt_offset=5)  # neither


def test_tube_clamp_rejects_both_cross_sections():
    with pytest.raises(ValidationError):
        TubeClamp(tube_d=10, tube_w=10, clamp_length=20, wall_thk=3, bolt_offset=5)


def test_tube_clamp_4_bolts_places_at_corners():
    """4 mounting bolts go at the corners (±bolt_x, ±bolt_y), not at
    the center. Walk the AST and accumulate translates (and mirror
    flips) to find the cylinder cutter centers; verify four distinct
    corners are produced."""
    from scadwright.ast.primitives import Cylinder
    from scadwright.ast.transforms import Mirror, Translate

    clamp = TubeClamp(
        tube_d=12, clamp_length=30, wall_thk=3, bolt_offset=5, n_bolts=4,
    )
    expected_x = 30 / 2 - clamp.bolt_axial_inset  # 15 - 5 = 10
    expected_y = 12 / 2 + 5                        # 11

    centers = []

    def walk(node, depth=20, dx=0.0, dy=0.0, fx=1.0, fy=1.0):
        if depth == 0:
            return
        if isinstance(node, Translate):
            walk(node.child, depth - 1, dx + fx * node.v[0],
                 dy + fy * node.v[1], fx, fy)
            return
        if isinstance(node, Mirror):
            nfx, nfy = fx, fy
            if abs(node.normal[0]) > 0.5:
                nfx = -fx
            if abs(node.normal[1]) > 0.5:
                nfy = -fy
            walk(node.child, depth - 1, dx, dy, nfx, nfy)
            return
        if isinstance(node, Cylinder):
            centers.append((dx, dy))
            return
        for attr in ("child", "children"):
            v = getattr(node, attr, None)
            if v is None:
                continue
            if isinstance(v, tuple):
                for c in v:
                    walk(c, depth - 1, dx, dy, fx, fy)
            else:
                walk(v, depth - 1, dx, dy, fx, fy)

    walk(clamp.build())
    # Filter to nonzero (x, y) offsets to skip the tube cradle cylinder
    # (centered on the body's xy axis).
    corner_centers = {
        (round(x, 2), round(y, 2))
        for x, y in centers
        if abs(x) > 0.01 and abs(y) > 0.01
    }
    expected = {
        (expected_x, expected_y), (-expected_x, expected_y),
        (expected_x, -expected_y), (-expected_x, -expected_y),
    }
    assert corner_centers == expected, (
        f"Expected four mounting bolts at corners {expected}, got "
        f"{corner_centers}"
    )


def test_tube_clamp_split_full_enclosure():
    """split style fully wraps the tube; body height is tube_d + 2*wall_thk."""
    c = TubeClamp(tube_d=12, clamp_length=20, wall_thk=3, bolt_offset=5, style="split")
    bb = bbox(c)
    assert bb.size[2] == pytest.approx(12 + 2 * 3, abs=0.5)


def test_tube_clamp_split_pinch_bolt_inside_body():
    """The pinch bolt cutter must actually cross the body (not be
    positioned outside it where the difference would no-op). Walk the
    AST to find a horizontal cylinder cutter and verify its position
    is within the body's bbox in the y direction.
    """
    from scadwright.ast.csg import Difference
    from scadwright.ast.primitives import Cylinder
    from scadwright.ast.transforms import Rotate, Translate
    c = TubeClamp(
        tube_d=12, clamp_length=20, wall_thk=3, bolt_offset=5, style="split",
    )
    body_y_half = bbox(c).size[1] / 2  # ±14

    # The pinch is the only horizontally-rotated clearance-hole cylinder
    # in the split tree. Walk and find it.
    def find_pinch(node, depth=20):
        if depth == 0:
            return None
        if isinstance(node, Translate):
            child = node.child
            # Look for Translate → Rotate(angles=(90,0,0)) → Cylinder.
            if isinstance(child, Rotate) and isinstance(child.child, Cylinder):
                angles = child.angles
                if angles is not None and abs(angles[0] - 90) < 1e-6 \
                        and abs(angles[1]) < 1e-6 and abs(angles[2]) < 1e-6:
                    return node
            return find_pinch(child, depth - 1)
        for attr in ("child", "children"):
            v = getattr(node, attr, None)
            if v is None:
                continue
            if isinstance(v, tuple):
                for ch in v:
                    found = find_pinch(ch, depth - 1)
                    if found is not None:
                        return found
            else:
                found = find_pinch(v, depth - 1)
                if found is not None:
                    return found
        return None

    pinch = find_pinch(c.build())
    assert pinch is not None, "Pinch bolt cutter not found in split-clamp AST"
    # Pinch is a Translate wrapping a Rotate wrapping a Cylinder. The
    # Translate's y component should put the cutter's base at
    # y = -(body_y_half + 1) so the cutter spans the full body width.
    cyl = pinch.child.child
    assert pinch.v[1] == pytest.approx(-(body_y_half + 1), abs=0.01), (
        f"Pinch bolt base y={pinch.v[1]} should be at "
        f"-(body_y_half + 1) = {-(body_y_half + 1)}"
    )
    # Cylinder height should span the whole body plus 2mm overpenetration.
    expected_h = 2 * body_y_half + 2
    assert cyl.h == pytest.approx(expected_h, abs=0.01)


def test_tube_clamp_emits():
    c = TubeClamp(tube_d=12, clamp_length=20, wall_thk=3, bolt_offset=5)
    scad = emit_str(c)
    assert "difference" in scad


def test_tube_clamp_invalid_style_raises():
    with pytest.raises(ValidationError, match="style"):
        TubeClamp(
            tube_d=12, clamp_length=20, wall_thk=3, bolt_offset=5, style="bogus",
        )


# --- Grommet ---


def test_grommet_plain():
    """Without a groove, the silhouette is three stacked cylinders."""
    g = Grommet(plate_thk=1.6, plate_hole_d=4, flange_d=6)
    assert g.total_h == pytest.approx(1.6 + 2 * 0.6)
    assert g.barrel_d == pytest.approx(4 - 2 * 0.1)
    bb = bbox(g)
    # bbox width: flange_d = 6, centered on origin
    assert bb.size[0] == pytest.approx(6.0, abs=0.1)
    assert bb.size[1] == pytest.approx(6.0, abs=0.1)
    # bbox height: total_h = 2.8
    assert bb.size[2] == pytest.approx(2.8, abs=0.1)


def test_grommet_with_groove():
    """A nonzero groove_depth produces an extra inward indent in the
    silhouette polygon. Walk the build tree to find the polygon and
    verify it includes points at the groove radius."""
    from scadwright.ast.primitives import Polygon
    plain = Grommet(plate_thk=1.6, plate_hole_d=4, flange_d=6)
    grooved = Grommet(
        plate_thk=1.6, plate_hole_d=4, flange_d=6,
        groove_depth=0.3, groove_width=0.8,
    )
    # Outer dimensions unchanged by groove (it's an inward cut).
    bb = bbox(grooved)
    assert bb.size[0] == pytest.approx(6.0, abs=0.1)
    assert bb.size[2] == pytest.approx(2.8, abs=0.1)

    def find_polygon(node, depth=20):
        if depth == 0:
            return None
        if isinstance(node, Polygon):
            return node
        for attr in ("child", "children"):
            v = getattr(node, attr, None)
            if v is None:
                continue
            if isinstance(v, tuple):
                for c in v:
                    found = find_polygon(c, depth - 1)
                    if found is not None:
                        return found
            else:
                found = find_polygon(v, depth - 1)
                if found is not None:
                    return found
        return None

    plain_pts = find_polygon(plain.build()).points
    grooved_pts = find_polygon(grooved.build()).points
    # The groove adds four extra points to the silhouette (entering and
    # exiting the indent on each side of the equator).
    assert len(grooved_pts) == len(plain_pts) + 4
    # The grooved silhouette must include points at the groove radius
    # (barrel_r - groove_depth = 1.9 - 0.3 = 1.6).
    radii = {round(p[0], 4) for p in grooved_pts}
    assert 1.6 in radii, f"Expected groove radius 1.6 in polygon, got {radii}"


def test_grommet_screw_default():
    """Default screw is M3."""
    g = Grommet(plate_thk=2, plate_hole_d=4, flange_d=6)
    assert g.screw == "M3"


def test_grommet_flange_smaller_than_hole_raises():
    with pytest.raises(ValidationError, match="flange_d"):
        Grommet(plate_thk=1.6, plate_hole_d=4, flange_d=3)


def test_grommet_groove_too_wide_raises():
    """groove_width >= plate_thk would consume the whole barrel."""
    with pytest.raises(ValidationError, match="groove_width"):
        Grommet(
            plate_thk=1.6, plate_hole_d=4, flange_d=6,
            groove_depth=0.3, groove_width=2.0,
        )


def test_grommet_groove_too_deep_raises():
    """2 * groove_depth >= barrel_d would meet or cross the axis."""
    with pytest.raises(ValidationError, match="groove_depth"):
        Grommet(
            plate_thk=1.6, plate_hole_d=4, flange_d=6,
            groove_depth=2.0, groove_width=0.4,
        )


def test_grommet_emits():
    g = Grommet(plate_thk=1.6, plate_hole_d=4, flange_d=6)
    scad = emit_str(g)
    assert "rotate_extrude" in scad
    assert "difference" in scad


def test_grommet_anchors_have_rim_radius():
    """top/bottom anchors carry rim_radius for arc-on-rim attach/text."""
    from scadwright.anchor import get_node_anchors
    g = Grommet(plate_thk=1.6, plate_hole_d=4, flange_d=6)
    anchors = get_node_anchors(g)
    assert anchors["top"].rim_radius == pytest.approx(3.0)
    assert anchors["bottom"].rim_radius == pytest.approx(3.0)
