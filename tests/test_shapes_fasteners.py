"""Tests for fasteners subpackage."""

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import (
    Bolt,
    CaptiveNutPocket,
    HeatSetPocket,
    HexNut,
    SquareNut,
    Standoff,
    clearance_hole,
    tap_hole,
)
from scadwright.shapes.fasteners.data import get_screw_spec, get_nut_spec, get_insert_spec


# --- data tables ---


def test_screw_spec_m3():
    s = get_screw_spec("M3")
    assert s.d == 3.0
    assert s.pitch == 0.5


def test_screw_spec_button():
    s = get_screw_spec("M3", head="button")
    assert s.d == 3.0
    assert s.head_h < get_screw_spec("M3", head="socket").head_h


def test_screw_spec_unknown_raises():
    with pytest.raises(ValidationError, match="Unknown screw size"):
        get_screw_spec("M99")


def test_nut_spec_m5():
    n = get_nut_spec("M5")
    assert n.af == 8.0


def test_insert_spec_m3():
    i = get_insert_spec("M3")
    assert i.hole_d > i.d


# --- Bolt ---


def test_bolt_builds():
    b = Bolt(size="M3", length=10)
    scad = emit_str(b)
    assert "cylinder" in scad


def test_bolt_bbox():
    b = Bolt(size="M3", length=10)
    bb = bbox(b)
    # Height: shaft (10) + head (~3)
    assert bb.size[2] == pytest.approx(13.0, abs=0.5)


def test_bolt_button_head():
    b = Bolt(size="M5", length=15, head="button")
    scad = emit_str(b)
    assert "cylinder" in scad


def test_bolt_socket_vs_button_head_distinct_height():
    """Socket and button heads have different head_h, so total height differs."""
    socket = Bolt(size="M5", length=15, head="socket")  # M5 socket head_h=5.0
    button = Bolt(size="M5", length=15, head="button")  # M5 button head_h=2.8
    assert bbox(socket).size[2] == pytest.approx(20.0, abs=0.1)
    assert bbox(button).size[2] == pytest.approx(17.8, abs=0.1)


def test_bolt_attributes():
    b = Bolt(size="M3", length=10)
    assert b.length == 10
    assert b.size == "M3"


# --- clearance_hole / tap_hole ---


def test_clearance_hole_m3():
    h = clearance_hole("M3", depth=10)
    bb = bbox(h)
    assert bb.size[0] == pytest.approx(3.4, abs=0.1)  # clearance_d


def test_tap_hole_m3():
    h = tap_hole("M3", depth=10)
    bb = bbox(h)
    assert bb.size[0] == pytest.approx(2.5, abs=0.1)  # tap_d


# --- HexNut ---


def test_hex_nut_builds():
    n = HexNut.of("M3")
    scad = emit_str(n)
    assert "polygon" in scad or "circle" in scad  # from regular_polygon


def test_hex_nut_publishes_af():
    n = HexNut.of("M5")
    assert n.af == 8.0
    assert n.h == 4.7


def test_hex_nut_custom_spec():
    """Pass a NutSpec directly for non-standard sizes."""
    from scadwright.shapes import NutSpec
    n = HexNut(spec=NutSpec(d=4, af=7, h=3))
    assert n.af == 7
    assert n.h == 3


# --- SquareNut ---


def test_square_nut_builds():
    n = SquareNut.of("M4")
    scad = emit_str(n)
    assert "cube" in scad


# --- HeatSetPocket ---


def test_heat_set_pocket():
    p = HeatSetPocket.of("M3")
    bb = bbox(p)
    assert bb.size[0] == pytest.approx(3.8, abs=0.2)


def test_heat_set_pocket_publishes_dims():
    p = HeatSetPocket.of("M3")
    assert p.hole_d == 3.8
    assert p.hole_depth == 4.5


# --- CaptiveNutPocket ---


def test_captive_nut_pocket():
    p = CaptiveNutPocket.of("M3", depth=3)
    scad = emit_str(p)
    assert "union" in scad


def test_captive_nut_pocket_y_axis():
    p = CaptiveNutPocket.of("M3", depth=3, channel_axis="y")
    scad = emit_str(p)
    assert "union" in scad


# --- Standoff ---


def test_standoff_builds():
    s = Standoff(od=7, id=3, h=8)
    scad = emit_str(s)
    assert "difference" in scad


def test_standoff_anchor():
    s = Standoff(od=7, id=3, h=8)
    anchors = s.get_anchors()
    assert "mount_top" in anchors
    assert anchors["mount_top"].position[2] == pytest.approx(8.0)
