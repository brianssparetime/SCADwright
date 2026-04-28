"""Tests for rim metadata and disk-rim arc text (text_curvature)."""

import logging
import math

import pytest

from scadwright.anchor import get_node_anchors
from scadwright.emit import emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder
from scadwright.shapes import Funnel, Tube


# --- Rim metadata exposed by hosts ---


def test_cylinder_top_has_rim_radius():
    a = get_node_anchors(cylinder(h=10, r=5))["top"]
    assert a.kind == "planar"
    assert a.surface_param("rim_radius") == 5.0
    # axis matches face normal so rim_radius scales correctly.
    assert a.surface_param("axis") == (0.0, 0.0, 1.0)


def test_cylinder_bottom_has_rim_radius():
    a = get_node_anchors(cylinder(h=10, r=5))["bottom"]
    assert a.surface_param("rim_radius") == 5.0
    assert a.surface_param("axis") == (0.0, 0.0, -1.0)


def test_cone_top_uses_r2_and_bottom_uses_r1():
    """Tapered cylinder: rim radii differ between top and bottom."""
    c = cylinder(h=10, r1=8, r2=3)
    assert get_node_anchors(c)["top"].surface_param("rim_radius") == 3.0
    assert get_node_anchors(c)["bottom"].surface_param("rim_radius") == 8.0


def test_tube_rim_radii():
    t = Tube(h=10, od=12, thk=2)
    assert get_node_anchors(t)["top"].surface_param("rim_radius") == pytest.approx(6.0)
    assert get_node_anchors(t)["bottom"].surface_param("rim_radius") == pytest.approx(6.0)


def test_funnel_rim_radii_differ():
    f = Funnel(h=20, bot_od=20, top_od=10, thk=2)
    assert get_node_anchors(f)["top"].surface_param("rim_radius") == pytest.approx(5.0)
    assert get_node_anchors(f)["bottom"].surface_param("rim_radius") == pytest.approx(10.0)


def test_cube_top_has_no_rim_radius():
    """Plain cubes don't get rim metadata — default text on top stays flat."""
    a = get_node_anchors(cube([10, 10, 10]))["top"]
    assert a.surface_param("rim_radius") is None


def test_rim_radius_scales_under_uniform_scale():
    a = get_node_anchors(cylinder(h=10, r=5).scale(2))["top"]
    assert a.surface_param("rim_radius") == pytest.approx(10.0)


def test_rim_axis_rotates_with_host():
    a = get_node_anchors(cylinder(h=10, r=5).rotate([90, 0, 0]))["top"]
    ax = a.surface_param("axis")
    # Top face normal originally +Z; after rotating 90° around +X → -Y.
    assert ax[0] == pytest.approx(0.0, abs=1e-9)
    assert ax[1] == pytest.approx(-1.0, abs=1e-9)


# --- text_curvature dispatch ---


def test_text_curvature_default_on_cylinder_is_arc():
    """Default behavior on a rim anchor wraps text around the rim."""
    p = cylinder(h=10, r=10).add_text(
        label="ABC", relief=0.4, on="top", font_size=2,
    )
    scad = emit_str(p)
    # Per-glyph: separate text() calls for each character.
    assert scad.count('text("A"') == 1
    assert scad.count('text("B"') == 1
    assert scad.count('text("C"') == 1


def test_text_curvature_default_on_cube_is_flat():
    """Cube top has no rim metadata; default is single straight text()."""
    p = cube([20, 20, 5]).add_text(
        label="ABC", relief=0.4, on="top", font_size=4,
    )
    scad = emit_str(p)
    assert scad.count('text("ABC"') == 1


def test_text_curvature_flat_forces_straight_on_rim():
    p = cylinder(h=10, r=10).add_text(
        label="ABC", relief=0.4, on="top", font_size=4, text_curvature="flat",
    )
    scad = emit_str(p)
    assert 'text("ABC"' in scad


def test_text_curvature_arc_on_non_rim_rejected():
    with pytest.raises(ValidationError, match="rim_radius"):
        emit_str(cube([10, 10, 10]).add_text(
            label="X", relief=0.4, on="top", font_size=4, text_curvature="arc",
        ))


def test_text_curvature_on_side_wall_rejected():
    """Side walls always wrap; text_curvature has no meaning there."""
    with pytest.raises(ValidationError, match="side walls"):
        emit_str(cylinder(h=20, r=10).add_text(
            label="X", relief=0.4, on="outer_wall", font_size=4,
            text_curvature="arc",
        ))


def test_text_curvature_invalid_value():
    with pytest.raises(ValidationError, match="text_curvature must be"):
        emit_str(cylinder(h=10, r=10).add_text(
            label="X", relief=0.4, on="top", font_size=2,
            text_curvature="bogus",
        ))


# --- at_radial kwarg ---


def test_at_radial_overrides_default_path_radius():
    """at_radial moves the text path closer to or further from rim center."""
    default_path = emit_str(cylinder(h=10, r=10).add_text(
        label="X", relief=0.4, on="top", font_size=2,
    ))
    custom_path = emit_str(cylinder(h=10, r=10).add_text(
        label="X", relief=0.4, on="top", font_size=2, at_radial=3,
    ))
    assert default_path != custom_path


def test_at_radial_on_flat_path_rejected():
    """at_radial only applies to arc dispatch."""
    with pytest.raises(ValidationError, match="at_radial"):
        emit_str(cylinder(h=10, r=10).add_text(
            label="X", relief=0.4, on="top", font_size=2,
            text_curvature="flat", at_radial=5,
        ))


def test_at_radial_negative_rejected():
    with pytest.raises(ValidationError, match="at_radial must be positive"):
        emit_str(cylinder(h=10, r=10).add_text(
            label="X", relief=0.4, on="top", font_size=2, at_radial=-1,
        ))


def test_at_radial_outside_rim_warns(caplog):
    """Path radius beyond the rim's outer edge logs a warning."""
    with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
        emit_str(cylinder(h=10, r=5).add_text(
            label="X", relief=0.4, on="top", font_size=1, at_radial=10,
        ))
    assert any("exceeds rim_radius" in r.message for r in caplog.records)


def test_at_radial_on_cylindrical_wall_rejected():
    """at_radial is for rim arc; cylindrical walls use at_z."""
    with pytest.raises(ValidationError, match="at_radial"):
        emit_str(cylinder(h=10, r=10).add_text(
            label="X", relief=0.4, on="outer_wall", font_size=2, at_radial=5,
        ))


# --- Inset on rim ---


def test_inset_rim_arc_is_difference():
    p = cylinder(h=10, r=10).add_text(
        label="X", relief=-0.3, on="top", font_size=2,
    )
    scad = emit_str(p)
    assert "difference" in scad


# --- Funnel rim with smaller top radius ---


def test_funnel_top_uses_top_od():
    """Funnel's top rim_radius equals top_od/2, not bot_od/2."""
    p = Funnel(h=20, bot_od=20, top_od=8, thk=1).add_text(
        label="O", relief=0.3, on="top", font_size=1,
    )
    scad = emit_str(p)
    # top_od/2 = 4; default at_radial = max(4 - 1, 0.5) = 3. Glyph at
    # radial direction +X (default meridian "+x"): translate near (3, 0, h).
    assert '"O"' in scad


# --- meridian on rim ---


def test_meridian_rotates_rim_label():
    """Two different meridians produce different placements."""
    a = emit_str(cylinder(h=10, r=10).add_text(
        label="X", relief=0.4, on="top", font_size=2, meridian="+x",
    ))
    b = emit_str(cylinder(h=10, r=10).add_text(
        label="X", relief=0.4, on="top", font_size=2, meridian="+y",
    ))
    assert a != b


# --- Pathway B with rim arc ---


def test_chain_rim_arc_then_outer_wall():
    """Rim arc text doesn't strip the host's other anchors."""
    p = (
        cylinder(h=20, r=10)
        .add_text(label="A", relief=0.4, on="top", font_size=2)
        .add_text(label="B", relief=0.4, on="outer_wall", font_size=4)
    )
    scad = emit_str(p)
    assert '"A"' in scad
    assert '"B"' in scad


# --- Wrap warning on tiny rim ---


def test_long_label_wraps_past_360_warns_on_rim(caplog):
    with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
        # Tiny radius, many chars → wraps past 360°.
        emit_str(cylinder(h=10, r=2).add_text(
            label="A" * 30, relief=0.2, on="top", font_size=1,
        ))
    assert any(
        "wraps" in r.message and "rim circle" in r.message
        for r in caplog.records
    )
