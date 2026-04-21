"""Tests for joint Components (finger, snap, locator)."""

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import (
    AlignmentPin,
    GripTab,
    PressFitPeg,
    SnapHook,
    SnapPin,
    TabSlot,
)


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


# --- AlignmentPin ---


def test_alignment_pin_socket_d_solved():
    p = AlignmentPin(d=4, h=8, lead_in=1, clearance=0.1)
    assert p.socket_d == pytest.approx(4.2)


def test_alignment_pin_socket_d_with_larger_clearance():
    p = AlignmentPin(d=4, h=8, lead_in=1, clearance=0.3)
    assert p.socket_d == pytest.approx(4.6)


def test_alignment_pin_bbox():
    p = AlignmentPin(d=4, h=8, lead_in=1, clearance=0.1, fn=64)
    bb = bbox(p)
    assert bb.size[0] == pytest.approx(4.0, abs=0.1)
    assert bb.size[2] == pytest.approx(8.0, abs=0.1)


def test_alignment_pin_socket_property_bbox():
    p = AlignmentPin(d=4, h=8, lead_in=1, clearance=0.2, fn=64)
    bb = bbox(p.socket)
    assert bb.size[0] == pytest.approx(p.socket_d, abs=0.1)   # 4.4
    assert bb.size[2] == pytest.approx(p.h, abs=0.1)


def test_alignment_pin_lead_in_too_large_raises():
    with pytest.raises(ValidationError, match="lead_in"):
        AlignmentPin(d=4, h=1, lead_in=2, clearance=0.1)


def test_alignment_pin_lead_in_exceeds_radius_raises():
    with pytest.raises(ValidationError, match="lead_in"):
        AlignmentPin(d=4, h=10, lead_in=3, clearance=0.1)  # 3 > d/2=2


def test_alignment_pin_tip_anchor_at_top():
    p = AlignmentPin(d=4, h=8, lead_in=1, clearance=0.1)
    anchors = p.get_anchors()
    # Anchor position resolves against instance attributes (h=8).
    assert anchors["tip"].position[2] == pytest.approx(8.0)


def test_alignment_pin_clearance_required():
    with pytest.raises(ValidationError):
        AlignmentPin(d=4, h=8, lead_in=1)


# --- PressFitPeg ---


def test_press_fit_peg_socket_d_smaller_than_shaft():
    # Interference must shrink the socket vs. shaft.
    p = PressFitPeg(shaft_d=5, shaft_h=6, flange_d=8, flange_h=1.5, lead_in=0.5,
                    interference=0.1)
    assert p.socket_d == pytest.approx(4.8)   # 5 - 2*0.1
    assert p.socket_d < p.shaft_d


def test_press_fit_peg_bbox_includes_flange():
    p = PressFitPeg(shaft_d=3, shaft_h=6, flange_d=6, flange_h=1.5, lead_in=0.5,
                    interference=0.1, fn=64)
    bb = bbox(p)
    # Widest dimension is the flange diameter.
    assert bb.size[0] == pytest.approx(6.0, abs=0.1)
    # Total height = flange + shaft.
    assert bb.size[2] == pytest.approx(7.5, abs=0.1)


def test_press_fit_peg_socket_matches_shaft_height():
    p = PressFitPeg(shaft_d=3, shaft_h=6, flange_d=6, flange_h=1.5, lead_in=0.5,
                    interference=0.1, fn=64)
    bb = bbox(p.socket)
    assert bb.size[2] == pytest.approx(p.shaft_h, abs=0.1)
    assert bb.size[0] == pytest.approx(p.socket_d, abs=0.1)


def test_press_fit_peg_flange_must_overhang_shaft():
    with pytest.raises(ValidationError, match="flange_d"):
        PressFitPeg(shaft_d=5, shaft_h=4, flange_d=4, flange_h=1, lead_in=0.5,
                    interference=0.1)


def test_press_fit_peg_lead_in_exceeds_radius_raises():
    with pytest.raises(ValidationError, match="lead_in"):
        PressFitPeg(shaft_d=4, shaft_h=6, flange_d=7, flange_h=1, lead_in=3,
                    interference=0.1)


def test_press_fit_peg_interference_required():
    with pytest.raises(ValidationError):
        PressFitPeg(shaft_d=3, shaft_h=6, flange_d=6, flange_h=1.5, lead_in=0.5)


# --- SnapPin ---


def test_snap_pin_builds():
    p = SnapPin(d=5, h=15, slot_width=1, slot_depth=10, barb_depth=0.8, barb_height=1.5,
                clearance=0.2)
    scad = emit_str(p)
    assert "union" in scad
    assert "polyhedron" in scad   # barbs are polyhedra
    assert "difference" in scad   # slot is cut


def test_snap_pin_bbox_includes_barbs():
    # Barbs protrude in ±x by barb_depth — x extent = d + 2*barb_depth.
    p = SnapPin(d=5, h=15, slot_width=1, slot_depth=10, barb_depth=0.8, barb_height=1.5,
                clearance=0.2, fn=64)
    bb = bbox(p)
    assert bb.size[0] == pytest.approx(6.6, abs=0.1)   # 5 + 2*0.8
    assert bb.size[1] == pytest.approx(5.0, abs=0.1)   # just the cylinder diameter
    assert bb.size[2] == pytest.approx(15.0, abs=0.1)


def test_snap_pin_socket_sized_for_nominal_plus_clearance():
    p = SnapPin(d=5, h=15, slot_width=1, slot_depth=10, barb_depth=0.8, barb_height=1.5,
                clearance=0.2)
    assert p.socket_d == pytest.approx(5.4)


def test_snap_pin_slot_deeper_than_pin_raises():
    with pytest.raises(ValidationError, match="slot_depth"):
        SnapPin(d=5, h=5, slot_width=1, slot_depth=10, barb_depth=0.5, barb_height=0.5,
                clearance=0.2)


def test_snap_pin_barb_height_exceeds_slot_depth_raises():
    with pytest.raises(ValidationError, match="barb_height"):
        SnapPin(d=5, h=15, slot_width=1, slot_depth=2, barb_depth=0.5, barb_height=3,
                clearance=0.2)


def test_snap_pin_barb_too_deep_raises():
    with pytest.raises(ValidationError, match="barb_depth"):
        SnapPin(d=4, h=15, slot_width=1, slot_depth=10, barb_depth=3, barb_height=1,
                clearance=0.2)


def test_snap_pin_clearance_required():
    with pytest.raises(ValidationError):
        SnapPin(d=5, h=15, slot_width=1, slot_depth=10, barb_depth=0.8, barb_height=1.5)
