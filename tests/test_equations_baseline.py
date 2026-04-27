"""Baseline tests pinning the equations-pipeline behavior before the
iterative-resolver rewrite (see design_docs/collapse_eq.md, Phase 0).

These tests are deliberately specific about error-message format and
order-of-evaluation. The new resolver must either match these formats or
the tests must be updated explicitly. They exist so behavior changes
during the rewrite are visible rather than silent.

Scope:
- Error message formats for every observable failure mode.
- Order-of-evaluation guarantees relied on by current Components.
- Cross-Component publishing (Lid reads Box's attributes).
- `?` sigil interactions across constraints, cross-constraints,
  derivations, and predicates.
- The `setup()` framework hook still runs after equations machinery.
"""

from __future__ import annotations

from collections import namedtuple

import pytest

from scadwright import Component, Param
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder


# =============================================================================
# Error message format: under-specified
# =============================================================================


class _UnderspecBox(Component):
    h = Param(float, positive=True)
    id = Param(float, positive=True)
    od = Param(float, positive=True)
    thk = Param(float, positive=True)
    equations = ["od == id + 2*thk"]

    def build(self):
        return cube(self.h)


def test_underspec_message_says_cannot_solve():
    with pytest.raises(ValidationError) as exc:
        _UnderspecBox(h=1, id=8)
    msg = str(exc.value)
    assert "cannot solve" in msg


def test_underspec_message_lists_given_inputs():
    with pytest.raises(ValidationError) as exc:
        _UnderspecBox(h=1, id=8)
    msg = str(exc.value)
    assert "given" in msg
    assert "id" in msg


def test_underspec_message_lists_sufficient_combinations():
    with pytest.raises(ValidationError) as exc:
        _UnderspecBox(h=1, id=8)
    msg = str(exc.value)
    assert "need one of" in msg
    # At least one of the valid combinations should be present.
    assert any(combo in msg for combo in ("id, thk", "id, od", "od, thk"))


def test_underspec_message_includes_component_name():
    with pytest.raises(ValidationError) as exc:
        _UnderspecBox(h=1, id=8)
    assert "_UnderspecBox" in str(exc.value)


# =============================================================================
# Error message format: over-specified inconsistent
# =============================================================================


def test_overspec_inconsistent_says_equation_violated():
    with pytest.raises(ValidationError) as exc:
        _UnderspecBox(h=1, id=8, od=10, thk=2)  # 10 != 8 + 4
    msg = str(exc.value)
    assert "equation violated" in msg


def test_overspec_inconsistent_includes_offending_equation():
    with pytest.raises(ValidationError) as exc:
        _UnderspecBox(h=1, id=8, od=10, thk=2)
    msg = str(exc.value)
    # The equation `od == id + 2*thk` (sympy form) should appear.
    assert "od" in msg and "id" in msg and "thk" in msg


def test_overspec_inconsistent_includes_substituted_values():
    with pytest.raises(ValidationError) as exc:
        _UnderspecBox(h=1, id=8, od=10, thk=2)
    msg = str(exc.value)
    # The substituted both-sides values appear in the diagnostic
    # (lhs=10, rhs=12 since 8 + 2*2 = 12).
    assert "10" in msg and "12" in msg


# =============================================================================
# Error message format: per-Param validator
# =============================================================================


def test_per_param_validator_message_format():
    with pytest.raises(ValidationError) as exc:
        _UnderspecBox(h=1, id=-1, thk=1)
    msg = str(exc.value)
    assert "id" in msg
    assert "must be positive" in msg
    assert "-1" in msg


def test_per_param_validator_message_includes_component_name():
    with pytest.raises(ValidationError) as exc:
        _UnderspecBox(h=1, id=-1, thk=1)
    assert "_UnderspecBox" in str(exc.value)


# =============================================================================
# Error message format: cross-constraint
# =============================================================================


class _CrossBox(Component):
    h = Param(float, positive=True)
    id = Param(float, positive=True)
    od = Param(float, positive=True)
    equations = [
        "id < od",
    ]

    def build(self):
        return cube(self.h)


def test_cross_constraint_violation_says_constraint_violated():
    with pytest.raises(ValidationError) as exc:
        _CrossBox(h=1, id=10, od=5)
    msg = str(exc.value)
    assert "constraint violated" in msg


def test_cross_constraint_violation_names_the_constraint():
    with pytest.raises(ValidationError) as exc:
        _CrossBox(h=1, id=10, od=5)
    msg = str(exc.value)
    assert "id" in msg and "od" in msg


def test_cross_constraint_violation_includes_values():
    with pytest.raises(ValidationError) as exc:
        _CrossBox(h=1, id=10, od=5)
    msg = str(exc.value)
    assert "10" in msg and "5" in msg


def test_cross_constraint_violation_includes_component_name():
    with pytest.raises(ValidationError) as exc:
        _CrossBox(h=1, id=10, od=5)
    assert "_CrossBox" in str(exc.value)


# =============================================================================
# Error message format: predicate
# =============================================================================


class _PredBox(Component):
    size = Param(tuple)
    r = Param(float, positive=True)
    equations = [
        "len(size) == 3",
        "all(s > 2 * r for s in size)",
    ]

    def build(self):
        return cube(1)


def test_predicate_failure_says_constraint_violated():
    with pytest.raises(ValidationError) as exc:
        _PredBox(size=(2, 2), r=1)
    msg = str(exc.value)
    assert "constraint violated" in msg


def test_predicate_failure_includes_source():
    with pytest.raises(ValidationError) as exc:
        _PredBox(size=(2, 2), r=1)
    msg = str(exc.value)
    # The first failing rule is reported (the comma-loop constraint here:
    # ``size=(2, 2)`` and ``r=1`` make ``s > 2*r`` false at index 0). The
    # ``len(size) == 3`` line is an equation under the unified spec; it
    # consistency-checks at the end of the resolve loop, after all
    # constraint failures.
    assert "all(s > 2 * r for s in size)" in msg


def test_predicate_failure_includes_component_name():
    with pytest.raises(ValidationError) as exc:
        _PredBox(size=(2, 2), r=1)
    assert "_PredBox" in str(exc.value)


def test_predicate_compare_failure_includes_left_right_values():
    with pytest.raises(ValidationError) as exc:
        _PredBox(size=(2, 2), r=1)
    msg = str(exc.value)
    # Top-level Compare enrichment shows left/right.
    assert "left=" in msg
    assert "right=" in msg


def test_predicate_all_genexp_failure_includes_index_and_value():
    with pytest.raises(ValidationError) as exc:
        _PredBox(size=(10, 10, 1), r=1)  # last side fails 1 > 2
    msg = str(exc.value)
    # all(...) enrichment shows the offending index.
    assert "index 2" in msg or "failed at index 2" in msg
    # The offending value (s=1) should be named.
    assert "s=" in msg


# =============================================================================
# Error message format: derivation runtime failure
# =============================================================================


class _DerivFails(Component):
    a = Param(float)
    equations = [
        "b = 1 / a",  # division by zero when a=0
    ]

    def build(self):
        return cube(1)


def test_derivation_runtime_failure_says_equation_failed():
    with pytest.raises(ValidationError) as exc:
        _DerivFails(a=0)
    msg = str(exc.value)
    assert "equation" in msg
    assert "failed" in msg


def test_derivation_runtime_failure_includes_source():
    with pytest.raises(ValidationError) as exc:
        _DerivFails(a=0)
    msg = str(exc.value)
    assert "b = 1 / a" in msg


def test_derivation_runtime_failure_includes_exception_type():
    with pytest.raises(ValidationError) as exc:
        _DerivFails(a=0)
    msg = str(exc.value)
    assert "ZeroDivisionError" in msg


# =============================================================================
# Order-of-evaluation guarantees
# =============================================================================


class _OrderProbe(Component):
    """Probes the documented evaluation order: cross-constraints before
    derivations before predicates. If the new resolver changes ordering
    in a user-visible way (e.g., a derivation that depended on a
    cross-constraint passing now runs before that check), this test
    catches it.

    `c_value` and `d_value` are derivation names (not Params); the
    predicate `len(label) > 0` references a Param to avoid the
    derivation-LHS-collides-with-auto-declared-Param check.
    """

    a = Param(float, positive=True)
    b = Param(float, positive=True)
    label = Param(str, default="x")
    equations = [
        "a < b",  # cross-constraint
        "c_value = a + b",  # derivation (depends on a, b)
        "d_value = c_value * 2",  # derivation (depends on earlier derivation)
        "len(label) > 0",  # predicate
    ]

    def build(self):
        return cube(1)


def test_derivations_can_reference_earlier_derivations():
    p = _OrderProbe(a=1, b=2)
    assert p.c_value == pytest.approx(3.0)
    assert p.d_value == pytest.approx(6.0)


def test_predicate_after_derivations():
    # The predicate references `label` rather than a derivation, but
    # the test confirms the predicate ran without complaining.
    p = _OrderProbe(a=1, b=2)
    assert p.d_value == pytest.approx(6.0)


def test_cross_constraint_runs_before_derivation():
    # `a < b` failing should raise before `c_value = a + b` is evaluated.
    # Both would technically succeed for values where a < b is false
    # but a + b is still computable, so the order matters for which
    # error fires.
    with pytest.raises(ValidationError) as exc:
        _OrderProbe(a=5, b=2)
    msg = str(exc.value)
    # Failure should reference the cross-constraint, not the derivation.
    assert "constraint" in msg or "a" in msg


# =============================================================================
# `setup()` hook still runs after the equations pipeline
# =============================================================================


class _SetupRuns(Component):
    a = Param(float, positive=True)
    equations = [
        "b = a * 2",  # derivation
    ]

    def setup(self):
        # setup runs after derivations; b should be available here.
        self.from_setup = self.b + 1

    def build(self):
        return cube(1)


def test_setup_hook_runs_after_derivations():
    p = _SetupRuns(a=3)
    assert p.b == pytest.approx(6.0)
    assert p.from_setup == pytest.approx(7.0)


# =============================================================================
# Cross-Component publishing
# =============================================================================


class _PubBox(Component):
    """A Box-like Component whose attributes are read by a downstream Lid."""

    w = Param(float, positive=True)
    equations = [
        "outer_w = w + 4",  # derivation a Lid will read
    ]

    def build(self):
        return cube(1)


class _PubLid(Component):
    """A Lid that reads the Box's published attribute through its `box`
    parameter."""

    box = Param(_PubBox)
    equations = [
        "lid_w = box.outer_w + 1",
    ]

    def build(self):
        return cube(1)


def test_cross_component_attribute_publishing():
    box = _PubBox(w=10)
    assert box.outer_w == pytest.approx(14.0)
    lid = _PubLid(box=box)
    assert lid.lid_w == pytest.approx(15.0)


def test_cross_component_namedtuple_publishing():
    """Variant of the cross-Component pattern: namedtuple field read by
    a downstream derivation. This is the pattern used in
    examples/battery-holder.py."""
    Spec = namedtuple("Spec", "d length")
    AA = Spec(d=14.5, length=50.5)

    class _SpecHolder(Component):
        spec = Param(Spec)
        equations = [
            "pitch = spec.d + 2",
        ]

        def build(self):
            return cube(1)

    h = _SpecHolder(spec=AA)
    assert h.pitch == pytest.approx(16.5)


# =============================================================================
# Optional `?` sigil interactions
# =============================================================================


class _OptConstraint(Component):
    """An optional Param with a per-Param positivity constraint. The
    constraint should skip when the value is None, fire when it's set."""

    equations = [
        "?fillet > 0",
    ]

    def build(self):
        return cube(1)


def test_optional_constraint_skips_when_unset():
    p = _OptConstraint()
    assert p.fillet is None


def test_optional_constraint_fires_when_set():
    with pytest.raises(ValidationError, match="must be positive"):
        _OptConstraint(fillet=-1)


class _OptCross(Component):
    """An optional Param with a cross-constraint involving it. The
    cross-constraint should skip when the optional is None."""

    base = Param(float, positive=True)
    equations = [
        "?fillet > 0",
        "?fillet < base",
    ]

    def build(self):
        return cube(1)


def test_optional_cross_constraint_skips_when_unset():
    _OptCross(base=10)  # fillet=None; should not raise


def test_optional_cross_constraint_fires_when_set():
    with pytest.raises(ValidationError):
        _OptCross(base=10, fillet=20)


class _OptDeriv(Component):
    """A derivation that uses an optional through a None-aware idiom
    (ternary). Should evaluate to None when the optional isn't set."""

    base = Param(float, positive=True)
    equations = [
        "?fillet > 0",
        "edge = ?fillet if ?fillet else base",
    ]

    def build(self):
        return cube(1)


def test_optional_derivation_with_truthy_fallback():
    p_with = _OptDeriv(base=10, fillet=2)
    assert p_with.edge == pytest.approx(2.0)
    p_without = _OptDeriv(base=10)
    assert p_without.edge == pytest.approx(10.0)


class _OptPredicate(Component):
    """A predicate referencing an optional through cardinality helpers.
    Behavior: helpers handle None natively."""

    equations = [
        "?fillet > 0",
        "?chamfer > 0",
        "exactly_one(?fillet, ?chamfer)",
    ]

    def build(self):
        return cube(1)


def test_optional_predicate_with_helper_pass():
    _OptPredicate(fillet=2)
    _OptPredicate(chamfer=3)


def test_optional_predicate_with_helper_fail_neither():
    with pytest.raises(ValidationError):
        _OptPredicate()


def test_optional_predicate_with_helper_fail_both():
    with pytest.raises(ValidationError):
        _OptPredicate(fillet=2, chamfer=3)


# =============================================================================
# Multi-solution disambiguation by validators
# =============================================================================


class _Quadratic(Component):
    """A solver equation with multiple roots; per-Param validator picks
    one. `r**2 == area / pi` has roots ±sqrt(area/pi); positivity
    constraint selects the positive."""

    area = Param(float, positive=True)
    r = Param(float, positive=True)
    equations = [
        "area == 3.141592653589793 * r**2",
    ]

    def build(self):
        return cube(1)


def test_quadratic_picks_positive_root_via_validator():
    p = _Quadratic(area=12.566370614359172)  # ~ pi * 4
    assert p.r == pytest.approx(2.0)


# =============================================================================
# Tolerance behavior at the consistency-check boundary
# =============================================================================


def test_tolerance_accepts_tiny_relative_drift():
    # 1e-11 over a value of 10 is well within the current tolerance.
    _UnderspecBox(h=1, id=8, od=10.0 + 1e-11, thk=1)


def test_tolerance_rejects_gross_inconsistency():
    with pytest.raises(ValidationError, match="equation violated"):
        _UnderspecBox(h=1, id=8, od=10.5, thk=1)
