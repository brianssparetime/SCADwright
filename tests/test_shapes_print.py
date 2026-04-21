"""Tests for print-oriented shapes."""

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import (
    EmbossedLabel,
    GridPanel,
    GripTab,
    HoneycombPanel,
    SnapHook,
    TabSlot,
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


# --- TabSlot ---


def test_tab_slot_builds():
    t = TabSlot(tab_w=5, tab_h=3, tab_d=10, clearance=0.2)
    scad = emit_str(t)
    assert "cube" in scad


def test_tab_slot_publishes_slot_dims():
    t = TabSlot(tab_w=5, tab_h=3, tab_d=10, clearance=0.2)
    assert t.slot_w == pytest.approx(5.4)
    assert t.slot_d == pytest.approx(10.4)


def test_tab_slot_slot_property_returns_cutter_with_correct_size():
    t = TabSlot(tab_w=5, tab_h=3, tab_d=10, clearance=0.2)
    bb = bbox(t.slot)
    assert bb.size[0] == pytest.approx(t.slot_w)  # 5.4
    assert bb.size[1] == pytest.approx(t.slot_d)  # 10.4
    assert bb.size[2] == pytest.approx(t.slot_h)  # 3.2


# --- SnapHook ---


def test_snap_hook_builds():
    h = SnapHook(arm_length=10, hook_depth=2, hook_height=2, thk=1.5, width=5)
    scad = emit_str(h)
    assert "union" in scad
    assert "polyhedron" in scad  # barb is a polyhedron


def test_snap_hook_geometry():
    """Barb protrudes in +Y beyond the arm's thk; Z extent is arm_length."""
    s = SnapHook(arm_length=10, hook_depth=2, hook_height=2, thk=1.5, width=5)
    bb = bbox(s)
    assert bb.size[0] == pytest.approx(5.0, abs=0.01)    # width
    assert bb.max[1] == pytest.approx(3.5, abs=0.02)     # thk + hook_depth
    assert bb.min[1] == pytest.approx(0.0, abs=0.01)     # arm back face
    assert bb.size[2] == pytest.approx(10.0, abs=0.01)   # arm_length


def test_snap_hook_hook_height_cannot_exceed_arm_length():
    with pytest.raises(ValidationError, match="hook_height"):
        SnapHook(arm_length=5, hook_depth=2, hook_height=10, thk=1.5, width=5)


# --- GripTab ---


def test_grip_tab_builds():
    g = GripTab(tab_w=6, tab_h=4, tab_d=8, taper=0.5)
    scad = emit_str(g)
    assert "linear_extrude" in scad


def test_grip_tab_no_taper():
    g = GripTab(tab_w=6, tab_h=4, tab_d=8, taper=0)
    bb = bbox(g)
    assert bb.size[0] == pytest.approx(6.0, abs=0.01)
    assert bb.size[1] == pytest.approx(8.0, abs=0.01)
    assert bb.size[2] == pytest.approx(4.0, abs=0.01)
