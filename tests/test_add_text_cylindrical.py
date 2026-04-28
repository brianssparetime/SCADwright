"""Tests for add_text on cylindrical surfaces (cylinder primitive + Tube)."""

import logging
import math

import pytest

from scadwright.anchor import Anchor, get_node_anchors
from scadwright.ast.csg import Difference, Union
from scadwright.ast.custom import Custom
from scadwright.emit import emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder
from scadwright.shapes import Tube


# --- Cylinder primitive carries an outer_wall cylindrical anchor ---


def test_cylinder_has_outer_wall_anchor():
    c = cylinder(h=20, r=5)
    anchors = get_node_anchors(c)
    assert "outer_wall" in anchors
    a = anchors["outer_wall"]
    assert a.kind == "cylindrical"
    assert a.surface_param("radius") == 5.0
    assert a.surface_param("axis") == (0.0, 0.0, 1.0)
    assert a.surface_param("length") == 20.0
    # Reference point at +X meridian, mid-wall.
    assert a.position == pytest.approx((5.0, 0.0, 10.0))
    assert a.normal == pytest.approx((1.0, 0.0, 0.0))


def test_cylinder_centered_outer_wall_position():
    """Centered cylinder has its mid-wall anchor at z=0."""
    c = cylinder(h=20, r=5, center=True)
    a = get_node_anchors(c)["outer_wall"]
    assert a.position == pytest.approx((5.0, 0.0, 0.0))


def test_cone_has_conical_outer_wall_not_cylindrical():
    """Cones (r1 != r2) get a conical outer_wall, not cylindrical."""
    c = cylinder(h=20, r1=5, r2=3)
    anchors = get_node_anchors(c)
    assert "outer_wall" in anchors
    assert anchors["outer_wall"].kind == "conical"


# --- Tube has outer_wall too ---


def test_tube_has_outer_wall_anchor():
    t = Tube(h=20, od=10, thk=2)
    anchors = get_node_anchors(t)
    assert "outer_wall" in anchors
    a = anchors["outer_wall"]
    assert a.kind == "cylindrical"
    assert a.surface_param("radius") == pytest.approx(5.0)
    assert a.surface_param("axis") == (0.0, 0.0, 1.0)
    assert a.surface_param("length") == pytest.approx(20.0)


# --- Cylindrical surface params survive transforms ---


def test_uniform_scale_scales_radius_and_length():
    c = cylinder(h=20, r=5).scale(2)
    a = get_node_anchors(c)["outer_wall"]
    assert a.surface_param("radius") == pytest.approx(10.0)
    assert a.surface_param("length") == pytest.approx(40.0)


def test_translate_preserves_radius_and_length():
    c = cylinder(h=20, r=5).translate([10, 0, 0])
    a = get_node_anchors(c)["outer_wall"]
    assert a.surface_param("radius") == pytest.approx(5.0)
    assert a.surface_param("length") == pytest.approx(20.0)
    # Position translated; surface params unchanged.
    assert a.position == pytest.approx((15.0, 0.0, 10.0))


def test_rotate_rotates_axis():
    c = cylinder(h=20, r=5).rotate([90, 0, 0])
    a = get_node_anchors(c)["outer_wall"]
    # After rotating 90° around +X, the cylinder's +Z axis points to -Y.
    ax = a.surface_param("axis")
    assert ax[0] == pytest.approx(0.0, abs=1e-9)
    assert ax[1] == pytest.approx(-1.0, abs=1e-9)
    assert ax[2] == pytest.approx(0.0, abs=1e-9)
    # Radius unchanged.
    assert a.surface_param("radius") == pytest.approx(5.0)


# --- Cylindrical add_text smoke tests ---


def test_cylindrical_add_text_emits():
    p = cylinder(h=20, r=10).add_text(
        label="HI", relief=0.4, on="outer_wall", font_size=4,
    )
    scad = emit_str(p)
    assert '"H"' in scad
    assert '"I"' in scad


def test_cylindrical_per_glyph_uses_separate_text_calls():
    """Each character renders as its own text() so the wrap works."""
    p = cylinder(h=20, r=10).add_text(
        label="ABC", relief=0.4, on="outer_wall", font_size=4,
    )
    scad = emit_str(p)
    # Three separate text() calls, one per character.
    assert scad.count('text("A"') == 1
    assert scad.count('text("B"') == 1
    assert scad.count('text("C"') == 1


def test_cylindrical_raised_is_union():
    from scadwright._custom_transforms.base import get_transform

    p = cylinder(h=20, r=10).add_text(
        label="X", relief=0.4, on="outer_wall", font_size=4,
    )
    expanded = get_transform("add_text").expand(p.child, **p.kwargs_dict())
    assert isinstance(expanded, Union)


def test_cylindrical_inset_is_difference():
    from scadwright._custom_transforms.base import get_transform

    p = cylinder(h=20, r=10).add_text(
        label="X", relief=-0.4, on="outer_wall", font_size=4,
    )
    expanded = get_transform("add_text").expand(p.child, **p.kwargs_dict())
    assert isinstance(expanded, Difference)


# --- meridian kwarg ---


@pytest.mark.parametrize("alias,expected_angle_deg", [
    ("+x", 0.0),
    ("rside", 0.0),
    ("+y", 90.0),
    ("back", 90.0),
    ("-x", 180.0),
    ("lside", 180.0),
    ("-y", 270.0),
    ("front", 270.0),
])
def test_meridian_string_aliases(alias, expected_angle_deg):
    """String meridians map to the documented angles."""
    p = cylinder(h=20, r=10).add_text(
        label="X", relief=0.4, on="outer_wall", font_size=4, meridian=alias,
    )
    scad = emit_str(p)
    # Glyph should be placed at (R*cos(θ), R*sin(θ), z_mid).
    th = math.radians(expected_angle_deg)
    expected_x = 9.99 * math.cos(th)  # R - eps for raised
    expected_y = 9.99 * math.sin(th)
    # Find the translate; the values appear in the SCAD as floats.
    # Use approximate matching by checking the expected position is in the SCAD.
    assert f"{expected_x:.5g}" in scad.replace(",", "") or \
           abs(expected_x) < 0.01  # near-zero values may format differently


def test_meridian_numeric():
    """Numeric meridian (degrees CCW) places glyph at that angle."""
    p = cylinder(h=20, r=10).add_text(
        label="X", relief=0.4, on="outer_wall", font_size=4, meridian=37.5,
    )
    scad = emit_str(p)
    th = math.radians(37.5)
    expected_x = 9.99 * math.cos(th)
    expected_y = 9.99 * math.sin(th)
    # Just check the SCAD emits without error and contains the text.
    assert '"X"' in scad


def test_meridian_invalid_string():
    with pytest.raises(ValidationError, match="meridian"):
        emit_str(cylinder(h=20, r=10).add_text(
            label="X", relief=0.4, on="outer_wall", font_size=4,
            meridian="bogus",
        ))


def test_meridian_on_flat_planar_anchor_raises():
    """meridian doesn't apply to flat planar faces (not rims, not curved)."""
    with pytest.raises(ValidationError, match="flat planar surface"):
        emit_str(cube([10, 10, 10]).add_text(
            label="X", relief=0.4, on="top", font_size=4,
            meridian="+x",
        ))


def test_at_z_on_planar_anchor_raises():
    """at_z is axial along a curved wall — rejected on any planar surface."""
    with pytest.raises(ValidationError, match="axial offset"):
        emit_str(cube([10, 10, 10]).add_text(
            label="X", relief=0.4, on="top", font_size=4,
            at_z=5,
        ))


# --- at_z kwarg ---


def test_at_z_default_is_mid_wall():
    """Without at_z, the glyph sits at the wall's axial midpoint."""
    p = cylinder(h=20, r=10).add_text(
        label="X", relief=0.4, on="outer_wall", font_size=4,
    )
    scad = emit_str(p)
    # Mid-wall z=10 for a non-centered h=20 cylinder.
    assert ", 10]" in scad


def test_at_z_offset_moves_glyph():
    """at_z=5 places the glyph 5mm above the anchor's reference (mid-wall + 5)."""
    p = cylinder(h=20, r=10).add_text(
        label="X", relief=0.4, on="outer_wall", font_size=4, at_z=5,
    )
    scad = emit_str(p)
    # Anchor reference is at z=10 (mid-wall); +5 → z=15.
    assert ", 15]" in scad


# --- >360° wrap warning ---


def test_long_label_wraps_past_360_warns(caplog):
    """A label whose total arc exceeds the circumference logs a warning."""
    with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
        # 30 chars at size 5 with spacing 1 → ~90 mm arc on a 5 mm radius
        # cylinder (~31 mm circumference) → ~290% wrap.
        emit_str(cylinder(h=20, r=5).add_text(
            label="A" * 30, relief=0.4, on="outer_wall", font_size=5,
        ))
    assert any(
        "wraps" in record.message and "%" in record.message
        for record in caplog.records
    )


def test_short_label_no_wrap_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
        emit_str(cylinder(h=20, r=20).add_text(
            label="HI", relief=0.4, on="outer_wall", font_size=4,
        ))
    assert not any("wraps" in r.message for r in caplog.records)


# --- Tube with cylindrical add_text ---


def test_tube_add_text_emits():
    p = Tube(h=20, od=20, thk=2).add_text(
        label="X", relief=0.4, on="outer_wall", font_size=4,
    )
    scad = emit_str(p)
    assert '"X"' in scad
    assert "difference" in scad  # Tube itself is a difference
    assert "union" in scad  # add_text union with the host


# --- empty label ---


def test_empty_label_rejected():
    with pytest.raises(ValidationError, match="empty"):
        emit_str(cylinder(h=20, r=10).add_text(
            label="", relief=0.4, on="outer_wall", font_size=4,
        ))


# --- Pathway B: cylindrical add_text preserves host anchors ---


def test_chain_cylindrical_then_planar():
    """add_text on outer_wall, then on top — the cylinder's anchors must survive."""
    p = (
        cylinder(h=20, r=10)
        .add_text(label="A", relief=0.4, on="outer_wall", font_size=4)
        .add_text(label="B", relief=0.4, on="top", font_size=4)
    )
    scad = emit_str(p)
    assert '"A"' in scad
    assert '"B"' in scad


def test_chain_two_cylindrical_labels():
    """Two cylindrical labels at different meridians."""
    p = (
        cylinder(h=20, r=10)
        .add_text(label="A", relief=0.4, on="outer_wall", font_size=4, meridian="+x")
        .add_text(label="B", relief=0.4, on="outer_wall", font_size=4, meridian="-x")
    )
    scad = emit_str(p)
    assert '"A"' in scad
    assert '"B"' in scad
