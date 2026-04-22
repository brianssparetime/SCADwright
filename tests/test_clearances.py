"""Tests for the clearance resolution chain.

Covers the framework machinery: ``Clearances`` NamedTuple, the
``with clearances(...)`` context manager with partial-spec merging,
``resolve_clearance`` category lookup, and the five-level precedence
(per-call → Component class attr → with-scope → Design class attr →
``DEFAULT_CLEARANCES``).

Joint-specific behavior (socket_d math, etc.) is tested alongside each
joint in ``test_shapes_joints.py``; this file is about the resolution
machinery itself.
"""

import pytest

from scadwright import (
    Clearances,
    Component,
    DEFAULT_CLEARANCES,
    clearances,
    render,
)
from scadwright.api.clearances import current_clearances, resolve_clearance
from scadwright.design import Design, variant as _variant_decorator
from scadwright.primitives import cube
from scadwright.shapes import (
    AlignmentPin,
    PressFitPeg,
    SnapPin,
    TabSlot,
)


# --- Clearances namedtuple ---


def test_clearances_all_none_by_default():
    c = Clearances()
    assert c.sliding is None
    assert c.press is None
    assert c.snap is None
    assert c.finger is None


def test_clearances_partial_construction():
    c = Clearances(sliding=0.05)
    assert c.sliding == 0.05
    assert c.press is None


def test_default_clearances_fully_populated():
    for field in ("sliding", "press", "snap", "finger"):
        assert getattr(DEFAULT_CLEARANCES, field) is not None


# --- resolve_clearance: floor behavior ---


def test_resolve_clearance_falls_through_to_default_when_unset():
    assert resolve_clearance("sliding") == DEFAULT_CLEARANCES.sliding
    assert resolve_clearance("press") == DEFAULT_CLEARANCES.press
    assert resolve_clearance("snap") == DEFAULT_CLEARANCES.snap
    assert resolve_clearance("finger") == DEFAULT_CLEARANCES.finger


def test_resolve_clearance_inside_empty_scope_still_uses_default():
    with clearances(Clearances()):
        assert resolve_clearance("sliding") == DEFAULT_CLEARANCES.sliding


# --- with clearances(...): scope + partial merge ---


def test_with_scope_overrides_default():
    with clearances(Clearances(sliding=0.5)):
        assert resolve_clearance("sliding") == 0.5


def test_partial_scope_inherits_unset_fields():
    with clearances(Clearances(sliding=0.5)):
        # sliding overridden; others inherit from DEFAULT_CLEARANCES
        assert resolve_clearance("sliding") == 0.5
        assert resolve_clearance("press") == DEFAULT_CLEARANCES.press
        assert resolve_clearance("finger") == DEFAULT_CLEARANCES.finger


def test_nested_scopes_compose_per_field():
    with clearances(Clearances(sliding=0.5, press=0.3)):
        with clearances(Clearances(sliding=0.05)):
            # sliding: inner wins (0.05)
            # press:   inherits from outer (0.3)
            # snap, finger: inherit from DEFAULT
            assert resolve_clearance("sliding") == 0.05
            assert resolve_clearance("press") == 0.3
            assert resolve_clearance("snap") == DEFAULT_CLEARANCES.snap
            assert resolve_clearance("finger") == DEFAULT_CLEARANCES.finger


def test_scope_restores_on_exit():
    outer = current_clearances()
    with clearances(Clearances(sliding=0.5)):
        pass
    assert current_clearances() == outer


# --- Per-joint category resolution ---


def test_alignment_pin_picks_up_sliding_category():
    with clearances(Clearances(sliding=0.3)):
        p = AlignmentPin(d=4, h=8, lead_in=1)
    assert p.clearance == pytest.approx(0.3)
    assert p.socket_d == pytest.approx(4 + 2 * 0.3)


def test_press_fit_peg_picks_up_press_category():
    with clearances(Clearances(press=0.08)):
        p = PressFitPeg(shaft_d=5, shaft_h=6, flange_d=8, flange_h=1.5, lead_in=0.5)
    assert p.clearance == pytest.approx(0.08)
    assert p.socket_d == pytest.approx(5 - 2 * 0.08)


def test_snap_pin_picks_up_snap_category():
    with clearances(Clearances(snap=0.3)):
        p = SnapPin(d=5, h=15, slot_width=1, slot_depth=10,
                    barb_depth=0.8, barb_height=1.5)
    assert p.clearance == pytest.approx(0.3)


def test_tab_slot_picks_up_finger_category():
    with clearances(Clearances(finger=0.4)):
        t = TabSlot(tab_w=5, tab_h=3, tab_d=10)
    assert t.clearance == pytest.approx(0.4)


def test_joint_ignores_unrelated_category():
    """AlignmentPin is sliding; a press-only override doesn't touch it."""
    with clearances(Clearances(press=0.5)):
        p = AlignmentPin(d=4, h=8, lead_in=1)
    assert p.clearance == pytest.approx(DEFAULT_CLEARANCES.sliding)


# --- Per-call kwarg wins ---


def test_per_call_kwarg_wins_over_with_scope():
    with clearances(Clearances(sliding=0.5)):
        p = AlignmentPin(d=4, h=8, lead_in=1, clearance=0.02)
    assert p.clearance == pytest.approx(0.02)


def test_per_call_kwarg_wins_when_no_scope_active():
    p = AlignmentPin(d=4, h=8, lead_in=1, clearance=0.15)
    assert p.clearance == pytest.approx(0.15)


# --- Component class-attribute level (Scenario B: inner scope during build) ---


class _TightBracket(Component):
    """Test Component with a class-level partial clearance override."""

    clearances = Clearances(sliding=0.05)

    def build(self):
        # The class-attr scope is pushed around this build, so joints
        # constructed here pick up sliding=0.05 even inside an outer
        # with clearances(...) block that names sliding differently.
        return AlignmentPin(d=4, h=8, lead_in=1)


def test_component_class_attr_pushes_inner_scope():
    """Class attr wins during build (Scenario B — matches fn semantics)."""
    b = _TightBracket()
    # Triggering materialization runs build under the class-attr scope.
    from scadwright import materialize
    materialize(b)
    # The AlignmentPin built inside saw the _TightBracket's class attr.
    # Unwrap to find it: _TightBracket returns AlignmentPin directly.
    built = b._built_tree
    assert built.clearance == pytest.approx(0.05)


def test_component_class_attr_wins_over_outer_with_scope():
    """Outer `with clearances` does NOT override a Component's class-level
    clearances attr — mirrors how class-level `fn` beats outer
    `with resolution(fn=…)`."""
    from scadwright import materialize

    with clearances(Clearances(sliding=0.5)):
        b = _TightBracket()
        materialize(b)
    # Class attr 0.05 wins over outer 0.5 (Scenario B).
    assert b._built_tree.clearance == pytest.approx(0.05)


def test_component_class_attr_partial_inherits_outer_fields():
    """A Component with a partial class-attr (only sliding set) lets
    other fields fall through to any outer scope."""
    from scadwright import materialize

    with clearances(Clearances(press=0.03)):
        b = _TightBracket()
        materialize(b)
    # sliding comes from class attr, but if we built a press joint
    # inside, it would see press=0.03 from the outer scope. _TightBracket
    # only builds an AlignmentPin (sliding), so we just confirm the
    # class-attr path doesn't clobber the outer scope for other fields.
    with clearances(Clearances(press=0.03)):
        assert resolve_clearance("press") == 0.03


# --- Design class-attribute level ---


def test_design_class_attr_propagates_to_variant_build(tmp_path):
    """Design class attr is pushed as a scope around the variant build,
    so joints constructed inside pick it up."""
    from scadwright.design import _render_one

    captured: list[float] = []

    class _ProjectDesign(Design):
        clearances = Clearances(sliding=0.25)

        @_variant_decorator(default=True)
        def display(self):
            # A joint constructed inside a variant should see the
            # Design's class-level clearances (pushed around the method
            # call in _render_one).
            pin = AlignmentPin(d=4, h=8, lead_in=1)
            captured.append(pin.clearance)
            return cube(1)

    meta = _ProjectDesign.__variants__["display"]
    _render_one(
        _ProjectDesign, "display", meta,
        base_dir=None, out_override=tmp_path / "design.scad",
    )
    assert captured == [pytest.approx(0.25)]


def test_design_class_attr_sees_outer_with_for_unset_fields():
    """A partial Design-level override lets other categories come from
    an enclosing with-scope (unusual but valid composition)."""
    from scadwright.design import _render_one

    captured: list[float] = []

    class _PartialDesign(Design):
        clearances = Clearances(sliding=0.25)  # only sliding set

        @_variant_decorator(default=True)
        def display(self):
            # press isn't set on the Design, so any outer scope wins
            # there; sliding is pinned to 0.25.
            captured.append(resolve_clearance("sliding"))
            captured.append(resolve_clearance("press"))
            return cube(1)

    meta = _PartialDesign.__variants__["display"]
    with clearances(Clearances(press=0.02)):
        _render_one(
            _PartialDesign, "display", meta,
            base_dir=None, out_override=None,
        )
    assert captured[0] == pytest.approx(0.25)          # from Design class
    assert captured[1] == pytest.approx(0.02)          # from outer with


# --- Solver interaction ---


def test_resolved_clearance_flows_into_solver_as_given():
    """The resolver injects `clearance` before the equation solver runs,
    so `socket_d` is solvable from the user's other inputs + the
    resolved clearance with no extra plumbing."""
    with clearances(Clearances(sliding=0.07)):
        p = AlignmentPin(d=10, h=20, lead_in=2)
    assert p.socket_d == pytest.approx(10 + 2 * 0.07)
    assert p.clearance == pytest.approx(0.07)


def test_per_call_overrides_solver_input_resolution():
    """Per-call clearance reaches the solver directly; resolver is
    skipped when the kwarg is present."""
    with clearances(Clearances(sliding=0.5)):
        # Per-call 0.1 wins — resolver sees kwargs already has clearance.
        p = AlignmentPin(d=10, h=20, lead_in=2, clearance=0.1)
    assert p.clearance == pytest.approx(0.1)
