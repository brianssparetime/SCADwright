"""Tests for orient=True rotation-aware attachment."""

import pytest

from scadwright import bbox
from scadwright.primitives import cube


def test_orient_top_to_top_flips_peg():
    """Attaching top-to-top with orient rotates peg upside-down."""
    plate = cube([40, 40, 2])
    peg = cube([10, 10, 5]).attach(plate, face="top", at="top", orient=True)
    bb = bbox(peg)
    # Peg's top was pointing +z; after orient, it points -z (opposing plate's
    # top normal). Peg is flipped and placed so its (now-bottom) top face
    # touches plate's top at z=2.
    assert bb.max[2] == pytest.approx(2.0)
    assert bb.min[2] == pytest.approx(-3.0)


def test_orient_bottom_to_bottom_flips_peg():
    """Attaching bottom-to-bottom with orient rotates peg upside-down."""
    plate = cube([40, 40, 2])
    peg = cube([10, 10, 5]).attach(plate, face="bottom", at="bottom", orient=True)
    bb = bbox(peg)
    # Peg flips so its bottom faces up (opposing plate's bottom normal).
    assert bb.min[2] == pytest.approx(0.0)
    assert bb.max[2] == pytest.approx(5.0)


def test_orient_bottom_to_top_no_rotation_needed():
    """bottom-to-top with orient: normals already oppose, same as non-orient."""
    plate = cube([40, 40, 2])
    peg_orient = cube([10, 10, 5]).attach(plate, face="top", at="bottom", orient=True)
    peg_plain = cube([10, 10, 5]).attach(plate, face="top", at="bottom")
    bb_o = bbox(peg_orient)
    bb_p = bbox(peg_plain)
    assert bb_o.min == pytest.approx(bb_p.min)
    assert bb_o.max == pytest.approx(bb_p.max)


def test_orient_rside_to_bottom():
    """Attaching rside-to-bottom with orient rotates peg sideways."""
    plate = cube([40, 40, 2])
    # Peg is 10x10x5 (x, y, z). orient rotates peg so its bottom normal
    # (-z) opposes plate's rside normal (+x), i.e. bottom faces -x.
    # After rotation, the 10x10x5 cube becomes 5x10x10 (x swaps with z).
    # The rotated bbox's "bottom" (-z face) is re-derived and positioned
    # at the face center of the plate's rside.
    peg = cube([10, 10, 5]).attach(plate, face="rside", at="bottom", orient=True)
    bb = bbox(peg)
    # Rotated peg size: x=5, y=10, z=10.
    assert bb.size[0] == pytest.approx(5.0)
    assert bb.size[2] == pytest.approx(10.0)


def test_orient_preserves_centering():
    """With orient, perpendicular axes should still be centered on face."""
    plate = cube([40, 40, 2])
    peg = cube([10, 10, 5]).attach(plate, face="top", at="bottom", orient=True)
    bb = bbox(peg)
    # Should be centered on plate in X and Y.
    assert bb.center[0] == pytest.approx(20.0)
    assert bb.center[1] == pytest.approx(20.0)


@pytest.mark.parametrize(
    "face, at",
    [
        ("top", "bottom"),
        ("bottom", "top"),
        ("front", "back"),
        ("back", "front"),
        ("lside", "rside"),
        ("rside", "lside"),
    ],
    ids=lambda x: x,
)
def test_orient_opposing_faces_matches_non_orient(face, at):
    """When at and face normals already oppose, orient should match non-orient."""
    plate = cube([40, 40, 2])
    peg_orient = cube([10, 10, 5]).attach(plate, face=face, at=at, orient=True)
    peg_plain = cube([10, 10, 5]).attach(plate, face=face, at=at)
    bb_o = bbox(peg_orient)
    bb_p = bbox(peg_plain)
    assert bb_o.min == pytest.approx(bb_p.min, abs=0.01)
    assert bb_o.max == pytest.approx(bb_p.max, abs=0.01)
