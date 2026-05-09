"""Tests for polar / azimuth placement on spherical anchors."""

import math

import pytest

from scadwright.anchor import get_node_anchors
from scadwright.ast.placement import _apply_attach_polar
from scadwright.ast.transforms import Translate
from scadwright.errors import ValidationError
from scadwright.primitives import cube, sphere


# --- sphere publishes the surface_params we need ---


def test_sphere_anchors_carry_full_surface_params():
    s = sphere(r=10)
    anchors = get_node_anchors(s)
    a = anchors["top"]
    assert a.kind == "spherical"
    assert a.surface_param("radius") == 10.0
    assert a.surface_param("axis") == (0.0, 0.0, 1.0)
    assert a.surface_param("axis_origin") == pytest.approx((0.0, 0.0, 0.0))
    assert a.surface_param("meridian_zero") == (1.0, 0.0, 0.0)


def test_sphere_publishes_surface_anchor():
    s = sphere(r=10)
    anchors = get_node_anchors(s)
    assert "surface" in anchors
    assert anchors["surface"].kind == "spherical"


def test_sphere_translated_axis_origin_tracks():
    s = sphere(r=5).translate([10, 0, 0])
    anchors = get_node_anchors(s)
    assert anchors["surface"].surface_param("axis_origin") == pytest.approx(
        (10.0, 0.0, 0.0)
    )


# --- _apply_attach_polar math ---


def test_polar_zero_is_north_pole():
    s = sphere(r=10)
    a = get_node_anchors(s)["surface"]
    new = _apply_attach_polar(a, polar=0, azimuth=0, loc=None)
    # polar=0 along +Z axis: at (0, 0, R).
    assert new.position == pytest.approx((0.0, 0.0, 10.0))
    # Outward normal at the north pole = +Z.
    assert new.normal == pytest.approx((0.0, 0.0, 1.0))


def test_polar_180_is_south_pole():
    s = sphere(r=10)
    a = get_node_anchors(s)["surface"]
    new = _apply_attach_polar(a, polar=180, azimuth=0, loc=None)
    assert new.position[2] == pytest.approx(-10.0, abs=1e-9)
    assert new.normal[2] == pytest.approx(-1.0, abs=1e-9)


def test_polar_90_azimuth_0_is_plus_x():
    s = sphere(r=10)
    a = get_node_anchors(s)["surface"]
    new = _apply_attach_polar(a, polar=90, azimuth=0, loc=None)
    assert new.position == pytest.approx((10.0, 0.0, 0.0), abs=1e-9)
    assert new.normal == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)


def test_polar_90_azimuth_90_is_plus_y():
    s = sphere(r=10)
    a = get_node_anchors(s)["surface"]
    new = _apply_attach_polar(a, polar=90, azimuth=90, loc=None)
    assert new.position == pytest.approx((0.0, 10.0, 0.0), abs=1e-9)


def test_polar_45_azimuth_0():
    s = sphere(r=10)
    a = get_node_anchors(s)["surface"]
    new = _apply_attach_polar(a, polar=45, azimuth=0, loc=None)
    expected_xy = 10.0 * math.sin(math.radians(45))
    expected_z = 10.0 * math.cos(math.radians(45))
    assert new.position == pytest.approx((expected_xy, 0.0, expected_z), abs=1e-9)


def test_polar_on_translated_sphere_uses_center():
    s = sphere(r=5).translate([10, 20, 30])
    a = get_node_anchors(s)["surface"]
    new = _apply_attach_polar(a, polar=90, azimuth=0, loc=None)
    # +X meridian at radius 5, sphere center at (10, 20, 30): (15, 20, 30).
    assert new.position == pytest.approx((15.0, 20.0, 30.0), abs=1e-9)


# --- attach() integration ---


def test_attach_with_polar_kwarg():
    ball = sphere(r=10)
    peg = cube([2, 2, 5])
    placed = peg.attach(ball, on="surface", polar=90, angle=0)
    # peg's "bottom" goes to ball's surface point (R, 0, 0). peg "bottom"
    # is at (1, 1, 0) by default; shift = (10 - 1, 0 - 1, 0 - 0) = (9, -1, 0).
    assert isinstance(placed, Translate)
    assert placed.v == pytest.approx((9.0, -1.0, 0.0), abs=1e-9)


def test_attach_angle_alone_on_sphere_defaults_polar_to_90():
    ball = sphere(r=10)
    peg = cube([2, 2, 5])
    placed_a = peg.attach(ball, on="surface", angle=0)
    placed_b = peg.attach(ball, on="surface", polar=90, angle=0)
    assert placed_a.v == pytest.approx(placed_b.v, abs=1e-9)


def test_attach_polar_zero_lands_on_north_pole():
    ball = sphere(r=10)
    peg = cube([2, 2, 5])
    placed = peg.attach(ball, on="surface", polar=0)
    # peg's "bottom" at (1, 1, 0); ball's polar=0 point at (0, 0, 10).
    assert placed.v == pytest.approx((-1.0, -1.0, 10.0), abs=1e-9)


def test_attach_polar_works_with_orient():
    ball = sphere(r=10)
    peg = cube([2, 2, 5])
    placed = peg.attach(
        ball, on="surface", polar=90, angle=0, orient=True
    )
    # Just confirm it doesn't error and produces something.
    assert placed is not None


# --- error paths ---


def test_polar_on_non_spherical_raises():
    plate = cube([10, 10, 1])
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="spherical"):
        peg.attach(plate, on="top", polar=30)


def test_polar_out_of_range_raises():
    ball = sphere(r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match=r"polar.*\[0, 180\]"):
        peg.attach(ball, on="surface", polar=200)


def test_polar_negative_raises():
    ball = sphere(r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match=r"polar.*\[0, 180\]"):
        peg.attach(ball, on="surface", polar=-10)


def test_at_z_on_sphere_raises():
    ball = sphere(r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="at_z="):
        peg.attach(ball, on="surface", polar=30, at_z=5)


def test_radius_on_sphere_with_polar_raises():
    ball = sphere(r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="radius="):
        peg.attach(ball, on="surface", polar=30, angle=0, radius=5)


# --- existing six bbox-tangent anchors still work ---


def test_existing_top_anchor_still_works():
    ball = sphere(r=10)
    peg = cube([2, 2, 5])
    placed = peg.attach(ball, on="top")
    # top anchor at (0, 0, 10) — peg's bottom at (1, 1, 0); shift (-1, -1, 10).
    assert placed.v == pytest.approx((-1.0, -1.0, 10.0), abs=1e-9)


# --- propagation through transforms ---


def test_polar_works_after_sphere_rotated():
    # Rotate the sphere 90° around y so its +Z axis now points along +X.
    # polar=0 should land at the new north pole (which is at +X * R).
    ball = sphere(r=10).rotate([0, 90, 0])
    peg = cube([2, 2, 5])
    placed = peg.attach(ball, on="surface", polar=0)
    # peg "bottom" at (1, 1, 0); rotated north pole at (10, 0, 0).
    assert placed.v == pytest.approx((9.0, -1.0, 0.0), abs=1e-9)
