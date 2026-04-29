"""Tests for custom anchors on Components."""

import pytest

from scadwright import Component, Param, anchor, bbox
from scadwright.errors import ValidationError
from scadwright.primitives import cube
from scadwright.shapes import UShapeChannel


# --- class-scope anchor declarations ---


class Bracket(Component):
    w = Param(float, default=20)
    h = Param(float, default=10)
    thk = Param(float, default=3)

    mount_face = anchor(at="w/2, w/2, thk", normal=(0, 0, 1))

    def build(self):
        return cube([self.w, self.w, self.h])


def test_custom_anchor_available_via_get_anchors():
    b = Bracket()
    anchors = b.get_anchors()
    assert "mount_face" in anchors
    assert anchors["mount_face"].position == pytest.approx((10.0, 10.0, 3.0))
    assert anchors["mount_face"].normal == (0.0, 0.0, 1.0)


def test_standard_face_anchors_also_present():
    b = Bracket()
    anchors = b.get_anchors()
    for name in ("top", "bottom", "front", "back", "lside", "rside",
                 "+z", "-z", "+y", "-y", "+x", "-x"):
        assert name in anchors


def test_class_scope_anchor_with_tuple_position():
    """anchor(at=(...)) with a literal tuple works."""

    class FixedAnchor(Component):
        h = Param(float, default=10)

        origin_top = anchor(at=(0, 0, 10), normal=(0, 0, 1))

        def build(self):
            return cube([5, 5, self.h])

    c = FixedAnchor()
    anchors = c.get_anchors()
    assert anchors["origin_top"].position == pytest.approx((0.0, 0.0, 10.0))


def test_class_scope_anchor_expression_uses_param_values():
    """anchor(at=...) expressions resolve against actual param values."""
    b = Bracket(w=40, thk=5)
    anchors = b.get_anchors()
    assert anchors["mount_face"].position == pytest.approx((20.0, 20.0, 5.0))


def test_class_scope_anchor_overrides_bbox_face():
    """A class-scope anchor with a standard face name overrides the bbox default."""

    class OverrideTop(Component):
        s = Param(float, default=10)

        top = anchor(at="s/2, s/2, 3", normal=(0, 0, 1))

        def build(self):
            return cube([self.s, self.s, self.s])

    c = OverrideTop()
    anchors = c.get_anchors()
    # Custom "top" at z=3, not bbox top at z=10.
    assert anchors["top"].position == pytest.approx((5.0, 5.0, 3.0))


def test_class_scope_anchor_no_params():
    """Anchor defs work on Components without any Params."""

    class Simple(Component):
        tip = anchor(at=(5, 5, 10), normal=(0, 0, 1))

        def build(self):
            return cube([10, 10, 10])

    c = Simple()
    anchors = c.get_anchors()
    assert "tip" in anchors
    assert anchors["tip"].position == pytest.approx((5.0, 5.0, 10.0))


def test_setup_anchor_overrides_class_scope():
    """self.anchor() in setup() overrides a class-scope anchor of the same name."""

    class Both(Component):
        h = Param(float, default=10)

        mount = anchor(at=(0, 0, 5), normal=(0, 0, 1))

        def setup(self):
            self.anchor("mount", position=(0, 0, self.h), normal=(0, 0, 1))

        def build(self):
            return cube([10, 10, self.h])

    c = Both()
    anchors = c.get_anchors()
    # setup() runs after class-scope defs, so it wins.
    assert anchors["mount"].position == pytest.approx((0.0, 0.0, 10.0))


# --- attach with custom anchors ---


def test_attach_uses_custom_anchor():
    b = Bracket()
    peg = cube([4, 4, 6]).attach(b, on="mount_face")
    bb = bbox(peg)
    # mount_face is at z=3; peg's bottom (at=bottom) aligns there.
    assert bb.min[2] == pytest.approx(3.0)
    assert bb.max[2] == pytest.approx(9.0)


# --- error cases ---


def test_custom_anchor_on_primitive_raises():
    with pytest.raises(ValidationError, match="custom anchor.*only available on Components"):
        cube(5).attach(cube(10), on="mount_face")


def test_unknown_custom_anchor_on_component_raises():
    b = Bracket()
    with pytest.raises(ValidationError, match="no anchor.*nonexistent"):
        cube(5).attach(b, on="nonexistent")


def test_anchor_bad_expression_raises():
    class Bad(Component):
        x = Param(float, default=1)
        oops = anchor(at="x, undefined_var, 0", normal=(0, 0, 1))

        def build(self):
            return cube(1)

    with pytest.raises(ValidationError, match="cannot evaluate"):
        Bad()


# --- string-expression normal= ---


def test_anchor_normal_as_literal_tuple():
    """The classic literal-tuple form keeps working."""
    class C(Component):
        equations = ["w > 0"]
        face = anchor(at="w/2, 0, 0", normal=(1, 0, 0))
        def build(self): return cube([1, 1, 1])

    c = C(w=4)
    a = c.get_anchors()["face"]
    assert a.normal == (1.0, 0.0, 0.0)


def test_anchor_normal_as_string_expression():
    """A bare string normal evaluates against instance attrs."""
    class C(Component):
        equations = ["w > 0"]
        face = anchor(at="w/2, 0, 0", normal="1, 0, 0")
        def build(self): return cube([1, 1, 1])

    c = C(w=4)
    a = c.get_anchors()["face"]
    assert a.normal == (1.0, 0.0, 0.0)


def test_anchor_normal_string_with_conditional():
    """String normal with a Param-driven conditional in one component flips."""
    class C(Component):
        flip = Param(bool, default=False)
        equations = ["w > 0"]
        face = anchor(at="0, 0, 0", normal="0, 0, -1 if flip else 1")
        def build(self): return cube([1, 1, 1])

    up = C(w=2)
    down = C(w=2, flip=True)
    assert up.get_anchors()["face"].normal == (0.0, 0.0, 1.0)
    assert down.get_anchors()["face"].normal == (0.0, 0.0, -1.0)


def test_anchor_normal_string_wrong_arity_raises():
    class C(Component):
        equations = ["w > 0"]
        oops = anchor(at="0, 0, 0", normal="1, 0")  # only 2
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError, match="normal= string must have 3"):
        C(w=2)


def test_anchor_normal_string_undefined_name_raises():
    class C(Component):
        equations = ["w > 0"]
        oops = anchor(at="0, 0, 0", normal="0, 0, missing_param")
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError, match="cannot evaluate normal="):
        C(w=2)


# --- shape library anchors ---


def test_ushape_channel_has_channel_opening_anchor():
    u = UShapeChannel(wall_thk=2, channel_width=6, channel_height=8, channel_length=20)
    anchors = u.get_anchors()
    assert "channel_opening" in anchors
    a = anchors["channel_opening"]
    # Opening is on top for default (non-n_shape).
    assert a.normal == (0.0, 0.0, 1.0)
    assert a.position[2] == pytest.approx(u.outer_height)


def test_ushape_channel_n_shape_opening_on_bottom():
    u = UShapeChannel(wall_thk=2, channel_width=6, channel_height=8,
                      channel_length=20, n_shape=True)
    anchors = u.get_anchors()
    a = anchors["channel_opening"]
    assert a.normal == (0.0, 0.0, -1.0)
    assert a.position[2] == pytest.approx(0.0)
