"""Tests for anchor dataclass and face-name utilities."""

import pytest

from scadwright.anchor import Anchor, FACE_NAMES, anchors_from_bbox, resolve_face_name
from scadwright.bbox import BBox
from scadwright.errors import ValidationError


# --- Anchor dataclass ---


def test_anchor_creation():
    a = Anchor(position=(1.0, 2.0, 3.0), normal=(0.0, 0.0, 1.0))
    assert a.position == (1.0, 2.0, 3.0)
    assert a.normal == (0.0, 0.0, 1.0)


def test_anchor_is_frozen():
    a = Anchor(position=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0))
    with pytest.raises(AttributeError):
        a.position = (1.0, 0.0, 0.0)


# --- resolve_face_name ---


@pytest.mark.parametrize(
    "name, expected",
    [
        ("top", (2, 1)),
        ("bottom", (2, -1)),
        ("front", (1, -1)),
        ("back", (1, 1)),
        ("lside", (0, -1)),
        ("rside", (0, 1)),
        ("+z", (2, 1)),
        ("-z", (2, -1)),
        ("+y", (1, 1)),
        ("-y", (1, -1)),
        ("+x", (0, 1)),
        ("-x", (0, -1)),
    ],
    ids=lambda x: str(x),
)
def test_resolve_face_name(name, expected):
    assert resolve_face_name(name) == expected


def test_resolve_face_name_unknown_raises():
    with pytest.raises(ValidationError, match="Unknown face name"):
        resolve_face_name("diagonal")


# --- anchors_from_bbox ---


def test_anchors_from_bbox_has_12_keys():
    bb = BBox(min=(0.0, 0.0, 0.0), max=(10.0, 20.0, 30.0))
    anchors = anchors_from_bbox(bb)
    assert len(anchors) == 12


def test_anchors_from_bbox_top():
    bb = BBox(min=(0.0, 0.0, 0.0), max=(10.0, 20.0, 30.0))
    anchors = anchors_from_bbox(bb)
    top = anchors["top"]
    assert top.position == pytest.approx((5.0, 10.0, 30.0))
    assert top.normal == (0.0, 0.0, 1.0)


def test_anchors_from_bbox_bottom():
    bb = BBox(min=(0.0, 0.0, 0.0), max=(10.0, 20.0, 30.0))
    anchors = anchors_from_bbox(bb)
    bottom = anchors["bottom"]
    assert bottom.position == pytest.approx((5.0, 10.0, 0.0))
    assert bottom.normal == (0.0, 0.0, -1.0)


def test_anchors_from_bbox_rside():
    bb = BBox(min=(0.0, 0.0, 0.0), max=(10.0, 20.0, 30.0))
    anchors = anchors_from_bbox(bb)
    rside = anchors["rside"]
    assert rside.position == pytest.approx((10.0, 10.0, 15.0))
    assert rside.normal == (1.0, 0.0, 0.0)


def test_anchors_from_bbox_lside():
    bb = BBox(min=(0.0, 0.0, 0.0), max=(10.0, 20.0, 30.0))
    anchors = anchors_from_bbox(bb)
    lside = anchors["lside"]
    assert lside.position == pytest.approx((0.0, 10.0, 15.0))
    assert lside.normal == (-1.0, 0.0, 0.0)


def test_anchors_from_bbox_friendly_and_axis_sign_share_values():
    bb = BBox(min=(0.0, 0.0, 0.0), max=(10.0, 20.0, 30.0))
    anchors = anchors_from_bbox(bb)
    # top and +z should produce the same anchor values.
    assert anchors["top"].position == anchors["+z"].position
    assert anchors["top"].normal == anchors["+z"].normal
    # front and -y should produce the same anchor values.
    assert anchors["front"].position == anchors["-y"].position
    assert anchors["front"].normal == anchors["-y"].normal


def test_anchors_from_bbox_offset_origin():
    bb = BBox(min=(10.0, 20.0, 30.0), max=(20.0, 40.0, 60.0))
    anchors = anchors_from_bbox(bb)
    top = anchors["top"]
    assert top.position == pytest.approx((15.0, 30.0, 60.0))
    bottom = anchors["bottom"]
    assert bottom.position == pytest.approx((15.0, 30.0, 30.0))
