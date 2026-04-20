"""Tests for polyhedra subpackage."""

import math

import pytest

from scadwright import bbox, emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import (
    Dodecahedron,
    Dome,
    Icosahedron,
    SphericalCap,
    Octahedron,
    Prism,
    Pyramid,
    Tetrahedron,
    Torus,
)


# --- Prism ---


def test_prism_hex():
    p = Prism(sides=6, r=10, h=20)
    bb = bbox(p)
    assert bb.size[2] == pytest.approx(20.0)
    assert bb.max[0] == pytest.approx(10.0)


def test_prism_frustum():
    p = Prism(sides=4, r=10, h=15, top_r=5)
    bb = bbox(p)
    assert bb.size[2] == pytest.approx(15.0)


def test_prism_emits_polyhedron():
    assert "polyhedron" in emit_str(Prism(sides=5, r=8, h=10))


def test_prism_too_few_sides_raises():
    with pytest.raises(ValidationError, match="sides must be >= 3"):
        Prism(sides=2, r=5, h=10)


# --- Pyramid ---


def test_pyramid_basic():
    p = Pyramid(sides=4, r=10, h=20)
    bb = bbox(p)
    assert bb.size[2] == pytest.approx(20.0)
    assert bb.max[0] == pytest.approx(10.0)


def test_pyramid_emits_polyhedron():
    assert "polyhedron" in emit_str(Pyramid(sides=6, r=5, h=10))


def test_pyramid_too_few_sides_raises():
    with pytest.raises(ValidationError, match="sides must be >= 3"):
        Pyramid(sides=1, r=5, h=10)


# --- Platonic solids ---


def test_tetrahedron_inscribed_radius():
    t = Tetrahedron(r=10)
    bb = bbox(t)
    # All vertices should be within the circumsphere.
    assert bb.max[2] == pytest.approx(10.0, abs=0.1)


def test_octahedron_vertices_on_axes():
    o = Octahedron(r=10)
    bb = bbox(o)
    assert bb.max[0] == pytest.approx(10.0, abs=0.01)
    assert bb.max[2] == pytest.approx(10.0, abs=0.01)


def test_dodecahedron_builds():
    d = Dodecahedron(r=10)
    scad = emit_str(d)
    assert "polyhedron" in scad


def test_icosahedron_builds():
    i = Icosahedron(r=10)
    scad = emit_str(i)
    assert "polyhedron" in scad


def test_icosahedron_symmetric():
    i = Icosahedron(r=10)
    bb = bbox(i)
    assert bb.size[0] == pytest.approx(bb.size[1], abs=0.1)


# --- Torus ---


def test_torus_full():
    t = Torus(major_r=10, minor_r=3)
    bb = bbox(t)
    # Outer extent: major_r + minor_r = 13 on each side.
    assert bb.max[0] == pytest.approx(13.0, abs=0.5)
    # Height: 2 * minor_r = 6.
    assert bb.size[2] == pytest.approx(6.0, abs=0.5)


def test_torus_partial():
    t = Torus(major_r=10, minor_r=3, angle=180)
    scad = emit_str(t)
    assert "rotate_extrude" in scad


def test_torus_minor_ge_major_raises():
    with pytest.raises(ValidationError, match="minor_r.*must be < major_r"):
        Torus(major_r=5, minor_r=5)


# --- Dome ---


def test_dome_solid():
    d = Dome(r=10)
    bb = bbox(d)
    assert bb.max[2] == pytest.approx(10.0, abs=0.5)
    assert bb.min[2] == pytest.approx(0.0, abs=0.5)


def test_dome_hollow():
    d = Dome(r=10, thk=2)
    scad = emit_str(d)
    assert "difference" in scad


def test_dome_thk_too_large_raises():
    with pytest.raises(ValidationError, match="thk.*must be < r"):
        Dome(r=10, thk=10)


# --- SphericalCap ---


def test_spherical_cap_by_sphere_r_and_cap_height():
    c = SphericalCap(sphere_r=20, cap_height=8)
    bb = bbox(c)
    assert bb.size[2] == pytest.approx(8.0, abs=0.5)
    assert c.sphere_r == 20
    assert c.cap_height == 8


def test_spherical_cap_solves_cap_dia():
    c = SphericalCap(sphere_r=20, cap_height=8)
    assert c.cap_dia > 0
    assert c.cap_r == pytest.approx(c.cap_dia / 2)


def test_spherical_cap_by_cap_dia_and_cap_height():
    c = SphericalCap(cap_dia=30, cap_height=5)
    assert c.cap_r == pytest.approx(15.0)
    assert c.sphere_r > 0


def test_spherical_cap_too_tall_raises():
    with pytest.raises((ValueError, ValidationError)):
        SphericalCap(sphere_r=5, cap_height=11)


def test_spherical_cap_emits():
    scad = emit_str(SphericalCap(sphere_r=10, cap_height=5))
    assert "intersection" in scad
