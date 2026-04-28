"""Tests for add_text on inner walls of Tube and Funnel."""

import pytest

from scadwright.anchor import get_node_anchors
from scadwright.ast.csg import Difference, Union
from scadwright.emit import emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import cylinder
from scadwright.shapes import Funnel, Tube


# --- Anchor metadata ---


def test_tube_has_inner_wall():
    t = Tube(h=20, od=20, thk=2)  # id = 16
    a = get_node_anchors(t)["inner_wall"]
    assert a.kind == "cylindrical"
    assert a.surface_param("radius") == pytest.approx(8.0)
    assert a.surface_param("axis") == (0.0, 0.0, 1.0)
    assert a.surface_param("length") == pytest.approx(20.0)
    assert a.surface_param("inner") is True
    # Reference position: +X meridian on inner surface, mid-wall.
    assert a.position == pytest.approx((8.0, 0.0, 10.0))
    # Outward normal points TOWARD the axis (into the hollow).
    assert a.normal == pytest.approx((-1.0, 0.0, 0.0))


def test_funnel_has_conical_inner_wall():
    f = Funnel(h=20, bot_od=20, top_od=10, thk=2)  # bot_id=16, top_id=6
    a = get_node_anchors(f)["inner_wall"]
    assert a.kind == "conical"
    assert a.surface_param("r1") == pytest.approx(8.0)
    assert a.surface_param("r2") == pytest.approx(3.0)
    assert a.surface_param("inner") is True
    # Reference position: mid-wall mid-radius on inner surface.
    assert a.position == pytest.approx((5.5, 0.0, 10.0))


def test_tube_inner_wall_scales_under_uniform_scale():
    t = Tube(h=20, od=20, thk=2).scale(2)
    a = get_node_anchors(t)["inner_wall"]
    assert a.surface_param("radius") == pytest.approx(16.0)
    assert a.surface_param("length") == pytest.approx(40.0)
    assert a.surface_param("inner") is True


def test_tube_inner_wall_axis_rotates_with_host():
    t = Tube(h=20, od=20, thk=2).rotate([90, 0, 0])
    a = get_node_anchors(t)["inner_wall"]
    ax = a.surface_param("axis")
    # +Z axis rotates 90° around +X → -Y.
    assert ax[0] == pytest.approx(0.0, abs=1e-9)
    assert ax[1] == pytest.approx(-1.0, abs=1e-9)
    assert a.surface_param("inner") is True


# --- Geometry: glyph world positions ---


def _first_translate_vec(scad: str) -> tuple[float, float, float]:
    """Parse the first ``translate([x, y, z])`` vector after the host."""
    import re
    # Skip the first translate (sometimes inside the Tube's own difference).
    matches = re.findall(r"translate\(\[([^\]]+)\]\)", scad)
    # The first translate that's part of an add_text glyph appears after
    # the Tube/Funnel construction. Find the translate whose vector has
    # the expected (positive_x, _, _ ) shape — robust enough for our cases.
    for m in matches:
        parts = [float(p.strip()) for p in m.split(",")]
        if len(parts) == 3 and parts[0] > 1.0:  # skip the eps-shifts
            return tuple(parts)
    raise AssertionError(f"no glyph translate found in: {scad}")


def test_tube_inner_raised_at_plus_x_meridian():
    """Glyph base at (id/2 + eps, 0, h/2) for raised on inner +X meridian."""
    p = Tube(h=20, od=20, thk=2).add_text(
        label="X", relief=0.4, on="inner_wall", font_size=4,
    )
    scad = emit_str(p)
    # id/2 = 8, eps = 0.01 → translate at (8.01, 0, 10).
    assert "8.01, 0, 10" in scad


def test_tube_inner_inset_at_plus_x_meridian():
    """Glyph base at (id/2 + relief + eps, 0, h/2) for inset on inner +X."""
    p = Tube(h=20, od=20, thk=2).add_text(
        label="X", relief=-0.3, on="inner_wall", font_size=4,
    )
    scad = emit_str(p)
    # id/2 + relief + eps = 8 + 0.3 + 0.01 = 8.31
    assert "8.31, 0, 10" in scad


def test_tube_inner_at_plus_y_meridian():
    """Glyph at +Y meridian: position (0, id/2 + eps, h/2)."""
    p = Tube(h=20, od=20, thk=2).add_text(
        label="X", relief=0.4, on="inner_wall", font_size=4, meridian="+y",
    )
    scad = emit_str(p)
    # Some near-zero floats may format as 6.x e-16 but the y component is 8.01.
    assert ", 8.01, 10" in scad


def test_funnel_inner_at_mid_wall():
    """Mid-wall radius on Funnel inner = (bot_id + top_id) / 4."""
    f = Funnel(h=20, bot_od=20, top_od=10, thk=2)  # bot_id=16, top_id=6
    p = f.add_text(label="X", relief=0.4, on="inner_wall", font_size=2)
    scad = emit_str(p)
    # mid_radius = (8 + 3)/2 = 5.5; +eps = 5.51
    assert "5.51, 0, 10" in scad


# --- Smoke ---


def test_inner_per_glyph():
    p = Tube(h=20, od=20, thk=2).add_text(
        label="ABC", relief=0.4, on="inner_wall", font_size=4,
    )
    scad = emit_str(p)
    assert scad.count('text("A"') == 1
    assert scad.count('text("B"') == 1
    assert scad.count('text("C"') == 1


def test_inner_raised_is_union():
    from scadwright._custom_transforms.base import get_transform

    p = Tube(h=20, od=20, thk=2).add_text(
        label="X", relief=0.4, on="inner_wall", font_size=4,
    )
    expanded = get_transform("add_text").expand(p.child, **p.kwargs_dict())
    assert isinstance(expanded, Union)


def test_inner_inset_is_difference():
    from scadwright._custom_transforms.base import get_transform

    p = Tube(h=20, od=20, thk=2).add_text(
        label="X", relief=-0.4, on="inner_wall", font_size=4,
    )
    expanded = get_transform("add_text").expand(p.child, **p.kwargs_dict())
    assert isinstance(expanded, Difference)


def test_funnel_inner_axial_vs_slant_differs():
    f = Funnel(h=20, bot_od=20, top_od=10, thk=2)
    axial = emit_str(f.add_text(
        label="X", relief=0.4, on="inner_wall", font_size=2,
        text_orient="axial",
    ))
    slant = emit_str(f.add_text(
        label="X", relief=0.4, on="inner_wall", font_size=2,
        text_orient="slant",
    ))
    assert axial != slant


# --- Pathway B ---


def test_chain_inner_wall_then_outer_wall():
    p = (
        Tube(h=20, od=20, thk=2)
        .add_text(label="A", relief=0.4, on="inner_wall", font_size=3)
        .add_text(label="B", relief=0.4, on="outer_wall", font_size=4)
    )
    scad = emit_str(p)
    assert '"A"' in scad
    assert '"B"' in scad


def test_chain_inner_wall_then_top_rim():
    """Inner wall decoration preserves the host's other anchors, including
    rim metadata on top/bottom."""
    p = (
        Tube(h=20, od=20, thk=2)
        .add_text(label="I", relief=0.4, on="inner_wall", font_size=3)
        .add_text(label="T", relief=0.4, on="top", font_size=2)  # rim arc default
    )
    scad = emit_str(p)
    assert '"I"' in scad
    assert '"T"' in scad


# --- Errors ---


def test_text_curvature_on_inner_wall_rejected():
    with pytest.raises(ValidationError, match="side walls"):
        emit_str(Tube(h=20, od=20, thk=2).add_text(
            label="X", relief=0.4, on="inner_wall", font_size=4,
            text_curvature="arc",
        ))


def test_at_radial_on_inner_wall_rejected():
    with pytest.raises(ValidationError, match="at_radial"):
        emit_str(Tube(h=20, od=20, thk=2).add_text(
            label="X", relief=0.4, on="inner_wall", font_size=4,
            at_radial=5,
        ))
