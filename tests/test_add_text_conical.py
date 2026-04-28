"""Tests for add_text on conical surfaces (cone primitive + Funnel)."""

import logging
import math

import pytest

from scadwright.anchor import get_node_anchors
from scadwright.ast.csg import Difference, Union
from scadwright.emit import emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import cylinder
from scadwright.shapes import Funnel


# --- Cone primitive carries a conical outer_wall anchor ---


def test_cone_has_conical_outer_wall():
    """A cylinder() with r1 != r2 is a cone — outer_wall is conical."""
    c = cylinder(h=20, r1=10, r2=5)
    a = get_node_anchors(c)["outer_wall"]
    assert a.kind == "conical"
    assert a.surface_param("r1") == 10.0
    assert a.surface_param("r2") == 5.0
    assert a.surface_param("length") == 20.0
    assert a.surface_param("axis") == (0.0, 0.0, 1.0)
    # Reference position is at mid-wall, mid-radius.
    assert a.position == pytest.approx((7.5, 0.0, 10.0))


def test_funnel_has_conical_outer_wall():
    f = Funnel(h=20, bot_od=20, top_od=10, thk=2)
    a = get_node_anchors(f)["outer_wall"]
    assert a.kind == "conical"
    assert a.surface_param("r1") == pytest.approx(10.0)
    assert a.surface_param("r2") == pytest.approx(5.0)
    assert a.surface_param("length") == pytest.approx(20.0)


# --- Conical surface params survive transforms ---


def test_uniform_scale_scales_cone_radii_and_length():
    f = Funnel(h=20, bot_od=20, top_od=10, thk=2).scale(2)
    a = get_node_anchors(f)["outer_wall"]
    assert a.surface_param("r1") == pytest.approx(20.0)
    assert a.surface_param("r2") == pytest.approx(10.0)
    assert a.surface_param("length") == pytest.approx(40.0)


def test_rotate_rotates_cone_axis():
    c = cylinder(h=20, r1=10, r2=5).rotate([90, 0, 0])
    a = get_node_anchors(c)["outer_wall"]
    ax = a.surface_param("axis")
    assert ax[0] == pytest.approx(0.0, abs=1e-9)
    assert ax[1] == pytest.approx(-1.0, abs=1e-9)
    assert ax[2] == pytest.approx(0.0, abs=1e-9)
    # Radii preserved.
    assert a.surface_param("r1") == pytest.approx(10.0)
    assert a.surface_param("r2") == pytest.approx(5.0)


# --- Conical add_text smoke ---


def test_conical_add_text_emits_axial():
    p = cylinder(h=20, r1=10, r2=5).add_text(
        label="AB", relief=0.4, on="outer_wall", font_size=4,
    )
    scad = emit_str(p)
    assert '"A"' in scad
    assert '"B"' in scad


def test_conical_default_orient_is_axial():
    """Without text_orient, glyphs are axial-aligned (up = axis)."""
    p = cylinder(h=20, r1=10, r2=5).add_text(
        label="X", relief=0.4, on="outer_wall", font_size=4,
    )
    scad_axial_default = emit_str(p)
    p2 = cylinder(h=20, r1=10, r2=5).add_text(
        label="X", relief=0.4, on="outer_wall", font_size=4, text_orient="axial",
    )
    scad_axial_explicit = emit_str(p2)
    assert scad_axial_default == scad_axial_explicit


def test_conical_slant_differs_from_axial():
    """text_orient='slant' produces a different transform than axial."""
    axial = emit_str(cylinder(h=20, r1=10, r2=5).add_text(
        label="X", relief=0.4, on="outer_wall", font_size=4, text_orient="axial",
    ))
    slant = emit_str(cylinder(h=20, r1=10, r2=5).add_text(
        label="X", relief=0.4, on="outer_wall", font_size=4, text_orient="slant",
    ))
    assert axial != slant


def test_text_orient_invalid_rejected():
    with pytest.raises(ValidationError, match="text_orient"):
        emit_str(cylinder(h=20, r1=10, r2=5).add_text(
            label="X", relief=0.4, on="outer_wall", font_size=4,
            text_orient="bogus",
        ))


# --- Funnel + add_text + Pathway B ---


def test_funnel_add_text_emits():
    p = Funnel(h=20, bot_od=20, top_od=10, thk=2).add_text(
        label="LOT", relief=0.4, on="outer_wall", font_size=3,
    )
    scad = emit_str(p)
    assert '"L"' in scad
    assert '"O"' in scad
    assert '"T"' in scad
    # Funnel itself is a difference; add_text raised wraps it in a union.
    assert "difference" in scad
    assert "union" in scad


def test_chain_conical_then_planar():
    """add_text on outer_wall (conical), then on top — anchors must survive."""
    p = (
        Funnel(h=20, bot_od=20, top_od=10, thk=2)
        .add_text(label="A", relief=0.4, on="outer_wall", font_size=3)
        .add_text(label="B", relief=0.4, on="top", font_size=3)
    )
    scad = emit_str(p)
    assert '"A"' in scad
    assert '"B"' in scad


# --- Cone-tip degeneracy ---


def test_at_z_beyond_cone_tip_rejected():
    """An at_z that puts the local radius past zero is an error."""
    # Cone r1=10 at z_min, r2=2 at z_max=20. Slope = -0.4 mm/mm. Mid radius = 6.
    # at_z = +15 → local radius = 6 + 15 * -0.4 = 0 (cone tip). +20 → -2 (past tip).
    with pytest.raises(ValidationError, match="cone tip"):
        emit_str(cylinder(h=20, r1=10, r2=2).add_text(
            label="X", relief=0.4, on="outer_wall", font_size=2, at_z=20,
        ))


def test_small_local_radius_warns(caplog):
    """A glyph placed where the cone is very narrow logs a warning."""
    with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
        # Mid-radius = 6; at_z=12 → local radius = 6 - 4.8 = 1.2 mm, font_size=4
        # → 1.2 < 0.5*4 = 2 mm. Should warn.
        emit_str(cylinder(h=20, r1=10, r2=2).add_text(
            label="X", relief=0.4, on="outer_wall", font_size=4, at_z=12,
        ))
    assert any("small relative to font_size" in r.message for r in caplog.records)


# --- Local radius interpolation ---


def test_at_z_uses_local_radius():
    """Different at_z should produce different glyph positions because the
    local radius varies along the cone."""
    # Mid-wall: r = 7.5, glyph at world (~7.5, 0, 10)
    p_mid = cylinder(h=20, r1=10, r2=5).add_text(
        label="X", relief=0.4, on="outer_wall", font_size=2,
    )
    # at_z = +5: local r = 7.5 - 5*0.25 = 6.25; world position (~6.25, 0, 15)
    p_high = cylinder(h=20, r1=10, r2=5).add_text(
        label="X", relief=0.4, on="outer_wall", font_size=2, at_z=5,
    )
    scad_mid = emit_str(p_mid)
    scad_high = emit_str(p_high)
    # The translate values differ between mid and high.
    assert scad_mid != scad_high
