"""Tests for mechanical subpackage: bearings, pulleys, shafts."""

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import Bearing, BearingSpec, DShaft, GT2Pulley, HTDPulley, KeyedShaft


# --- Bearing ---


def test_bearing_608():
    b = Bearing(series="608")
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
    with pytest.raises(ValidationError, match="unknown series"):
        Bearing(series="9999")


def test_bearing_publishes_dims():
    b = Bearing(series="625")
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
