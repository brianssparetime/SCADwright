"""Tests for print-oriented shapes (infill, text, vents, print aids)."""

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import (
    EmbossedLabel,
    GridPanel,
    HoneycombPanel,
    PolyHole,
    TextPlate,
    TriGridPanel,
    VentSlots,
)


# --- HoneycombPanel ---


def test_honeycomb_builds():
    p = HoneycombPanel(size=(50, 50, 3), cell_size=8, wall_thk=1)
    scad = emit_str(p)
    assert "difference" in scad


def test_honeycomb_bbox():
    p = HoneycombPanel(size=(50, 50, 3), cell_size=8, wall_thk=1)
    bb = bbox(p)
    assert bb.size[0] == pytest.approx(50.0, abs=0.5)
    assert bb.size[2] == pytest.approx(3.0, abs=0.1)


# --- GridPanel ---


def test_grid_panel_builds():
    p = GridPanel(size=(40, 40, 2), cell_size=5, wall_thk=1)
    scad = emit_str(p)
    assert "difference" in scad


# --- TriGridPanel ---


def test_tri_grid_builds():
    p = TriGridPanel(size=(40, 40, 2), cell_size=6, wall_thk=1)
    scad = emit_str(p)
    assert "difference" in scad


# --- TextPlate ---


def test_text_plate_builds():
    p = TextPlate(label="HELLO", plate_w=40, plate_h=15, plate_thk=2,
                  depth=0.5, font_size=8)
    scad = emit_str(p)
    assert "text" in scad


def test_text_plate_emit_contains_literal_label():
    """The emitted SCAD must contain the actual label text, not just `text(`."""
    p = TextPlate(label="SCADwright", plate_w=60, plate_h=15, plate_thk=2,
                  depth=0.5, font_size=8)
    scad = emit_str(p)
    assert '"SCADwright"' in scad


def test_text_plate_uses_specified_font():
    p = TextPlate(label="X", plate_w=20, plate_h=10, plate_thk=1,
                  depth=0.3, font_size=5, font="DejaVu Sans")
    scad = emit_str(p)
    assert "DejaVu Sans" in scad


# --- EmbossedLabel ---


def test_embossed_label_builds():
    p = EmbossedLabel(label="v1.0", plate_w=30, plate_h=10, plate_thk=2,
                      depth=0.3, font_size=6)
    scad = emit_str(p)
    assert "text" in scad


# --- VentSlots ---


def test_vent_slots_builds():
    v = VentSlots(width=30, height=20, thk=2, slot_width=20,
                  slot_height=1.5, slot_count=5)
    scad = emit_str(v)
    assert "difference" in scad


def test_vent_slots_too_few_raises():
    with pytest.raises(ValidationError, match="slot_count: must be >= 1"):
        VentSlots(width=30, height=20, thk=2, slot_width=20,
                  slot_height=1.5, slot_count=0)


# --- PolyHole ---


def test_poly_hole_circumradius_compensated():
    """The polygon's inscribed diameter must equal the nominal d."""
    import math
    p = PolyHole(d=6, h=10)
    assert p.sides == 8  # default
    inscribed_d = 2 * p.circumradius * math.cos(math.pi / p.sides)
    assert inscribed_d == pytest.approx(6.0, abs=1e-9)


def test_poly_hole_circumradius_scales_with_sides():
    # More sides -> less compensation needed -> smaller circumradius.
    p8 = PolyHole(d=6, h=10, sides=8)
    p32 = PolyHole(d=6, h=10, sides=32)
    assert p8.circumradius > p32.circumradius
    assert p32.circumradius > 3.0  # still strictly larger than d/2


def test_poly_hole_emits_fn_override():
    scad = emit_str(PolyHole(d=6, h=10, sides=6))
    # Every PolyHole bakes its polygon count into the cylinder's $fn.
    assert "$fn = 6" in scad or "$fn=6" in scad
    assert "cylinder" in scad


def test_poly_hole_bad_sides_raises():
    with pytest.raises(ValidationError, match="sides"):
        PolyHole(d=6, h=10, sides=1)


def test_poly_hole_bad_d_raises():
    with pytest.raises(ValidationError, match="d"):
        PolyHole(d=-1, h=10)
