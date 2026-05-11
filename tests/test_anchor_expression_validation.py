"""Tests for class-load anchor expression validation.

Anchor declarations with string expressions (``at=``, ``normal=``,
``surface_params={"X": "expr"}``) are AST-checked at Component
class-definition time. Every Load-context Name must resolve to a
declared Param or an equation-derived symbol — i.e., be present in the
class's ``_spec_value_names`` set.

The runtime ``eval`` is unchanged; this just moves typo detection
forward so authors find the error when their module imports rather
than when a downstream user instantiates the Component.
"""

import pytest

from scadwright import Component, Param, anchor
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# --- valid declarations pass ---


def test_simple_at_with_param():
    class C(Component):
        w = Param(float, default=10)
        face = anchor(at="w/2, w/2, 0", normal=(0, 0, 1))
        def build(self): return cube(self.w)
    c = C()
    assert c.get_anchors()["face"].position == pytest.approx((5.0, 5.0, 0.0))


def test_at_with_equation_derived_name():
    """A name introduced by the equations block is in _spec_value_names."""
    class C(Component):
        equations = "w = 2 * h"
        h = Param(float, default=5)
        face = anchor(at="w/2, 0, 0", normal=(0, 0, 1))  # w from equations
        def build(self): return cube(10)
    c = C()
    assert c.get_anchors()["face"].position == pytest.approx((5.0, 0.0, 0.0))


def test_at_with_conditional_uses_param():
    class C(Component):
        flip = Param(bool, default=False)
        equations = ["w > 0"]
        face = anchor(at="0, 0, 0", normal="0, 0, -1 if flip else 1")
        def build(self): return cube(self.w)
    assert C(w=2).get_anchors()["face"].normal == (0.0, 0.0, 1.0)
    assert C(w=2, flip=True).get_anchors()["face"].normal == (0.0, 0.0, -1.0)


def test_at_with_constants_only():
    class C(Component):
        equations = "w > 0"
        face = anchor(at="0, 0, 10", normal=(0, 0, 1))
        def build(self): return cube(self.w)
    assert C(w=5).get_anchors()["face"].position == pytest.approx((0.0, 0.0, 10.0))


def test_surface_params_string_value_with_param():
    class C(Component):
        equations = "h, r > 0"
        wall = anchor(
            at="r, 0, h/2",
            normal=(1, 0, 0),
            kind="cylindrical",
            surface_params={"axis": (0, 0, 1), "radius": "r", "length": "h"},
        )
        def build(self):
            from scadwright.primitives import cylinder
            return cylinder(h=self.h, r=self.r)
    c = C(h=20, r=5)
    a = c.get_anchors()["wall"]
    assert a.radius == 5
    assert a.length == 20


# --- typos raise at class-definition time, not at instantiation ---


def test_typo_in_at_raises_at_class_definition():
    """The class statement itself raises — the user doesn't have to
    instantiate the Component to discover the typo."""
    with pytest.raises(ValidationError, match="undefined_name"):
        class C(Component):  # noqa: F841
            w = Param(float, default=10)
            face = anchor(at="undefined_name, 0, 0", normal=(0, 0, 1))
            def build(self): return cube(1)


def test_typo_in_normal_string_raises_at_class_definition():
    with pytest.raises(ValidationError, match="bad_name"):
        class C(Component):  # noqa: F841
            equations = "w > 0"
            face = anchor(at="0, 0, 0", normal="0, 0, bad_name")
            def build(self): return cube(self.w)


def test_typo_in_surface_params_value_raises_at_class_definition():
    with pytest.raises(ValidationError, match="missing_radius"):
        class C(Component):  # noqa: F841
            equations = "h > 0"
            wall = anchor(
                at="0, 0, h/2",
                normal=(1, 0, 0),
                kind="cylindrical",
                surface_params={
                    "axis": (0, 0, 1),
                    "radius": "missing_radius",  # typo
                    "length": "h",
                },
            )
            def build(self):
                from scadwright.primitives import cylinder
                return cylinder(h=self.h, r=1)


def test_error_message_names_anchor_role_and_expression():
    with pytest.raises(ValidationError) as exc_info:
        class C(Component):  # noqa: F841
            w = Param(float, default=1)
            mount = anchor(at="w, w, missing", normal=(0, 0, 1))
            def build(self): return cube(1)
    msg = str(exc_info.value)
    assert "mount" in msg
    assert "at=" in msg
    assert "missing" in msg
    assert "w, w, missing" in msg


def test_error_message_lists_available_names():
    with pytest.raises(ValidationError) as exc_info:
        class C(Component):  # noqa: F841
            w = Param(float, default=1)
            h = Param(float, default=2)
            face = anchor(at="oops, 0, 0", normal=(0, 0, 1))
            def build(self): return cube(1)
    msg = str(exc_info.value)
    # Both declared params should appear in the "Available" list.
    assert "'h'" in msg
    assert "'w'" in msg


# --- syntax errors caught too ---


def test_syntax_error_in_expression():
    with pytest.raises(ValidationError, match="syntax error"):
        class C(Component):  # noqa: F841
            w = Param(float, default=1)
            face = anchor(at="w +, 0, 0", normal=(0, 0, 1))  # syntax error
            def build(self): return cube(1)


# --- function calls referencing undeclared names also fail ---


def test_function_call_with_undeclared_name_raises():
    """abs(x), min(...), etc. require the function name to be in
    valid_names. Since the runtime eval has __builtins__: {} they'd
    fail at runtime anyway; the class-load check is consistent."""
    with pytest.raises(ValidationError, match="abs"):
        class C(Component):  # noqa: F841
            w = Param(float, default=1)
            face = anchor(at="abs(w), 0, 0", normal=(0, 0, 1))
            def build(self): return cube(1)


# --- inherited Components see parent's anchors validated against child's names ---


def test_subclass_anchors_revalidated():
    """A subclass's __init_subclass__ re-runs the validation, so
    parent-class anchors are checked against the (combined) child-class
    name set. A subclass that removes a Param the parent's anchor
    references would fail at the subclass definition."""
    class Base(Component):
        equations = "w > 0"
        face = anchor(at="w, 0, 0", normal=(0, 0, 1))
        def build(self): return cube(self.w)

    # Subclass adding a Param: anchors still resolve.
    class Child(Base):
        equations = "w, h > 0"
        def build(self): return cube([self.w, self.w, self.h])

    c = Child(w=5, h=10)
    assert c.get_anchors()["face"].position == pytest.approx((5.0, 0.0, 0.0))
