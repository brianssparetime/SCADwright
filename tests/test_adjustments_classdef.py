"""Class-definition-time validation of adjustment syntax.

Each test triggers a check that fires while the class body is being
processed (or, for parser-level checks, while ``parse_equations_unified``
runs). The failure mode is always a ``ValidationError`` with a message
naming the offending line and explaining the rule.
"""

from __future__ import annotations

import pytest

from scadwright import Component, Param
from scadwright.component.resolver import parse_equations_unified
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# =============================================================================
# Per-name op-class uniformity
# =============================================================================


def test_mixing_additive_and_multiplicative_rejected():
    with pytest.raises(ValidationError, match="must be the same class"):
        parse_equations_unified([
            "x = 10",
            "x += 0.3",
            "x *= 1.05",
        ])


def test_additive_only_is_fine():
    # +=, -= mixing is allowed (both additive class).
    eqs, cons, _, _, adjs = parse_equations_unified([
        "x = 10",
        "x += 0.3",
        "x -= 0.1",
    ])
    assert len(adjs) == 2


def test_multiplicative_only_is_fine():
    eqs, cons, _, _, adjs = parse_equations_unified([
        "x = 10",
        "x *= 1.05",
        "x /= 1.02",
    ])
    assert len(adjs) == 2


def test_uniformity_is_per_name():
    """Different names can use different op classes."""
    _, _, _, _, adjs = parse_equations_unified([
        "a = 10",
        "b = 10",
        "a += 0.3",
        "b *= 1.05",
    ])
    assert len(adjs) == 2


# =============================================================================
# RHS no-reference-to-adjusted-names
# =============================================================================


def test_rhs_references_other_adjusted_name_rejected():
    # `b += a` with `a` itself adjusted: the RHS refers to an adjusted
    # name. Error names `a` (the offender), not `b`.
    with pytest.raises(
        ValidationError, match="references `a`"
    ):
        parse_equations_unified([
            "a = 1",
            "b = 2",
            "a += 0.1",
            "b += a",
        ])


def test_rhs_references_self_rejected():
    """A name referencing its own adjusted value is the same problem."""
    with pytest.raises(
        ValidationError, match="references `x`"
    ):
        parse_equations_unified([
            "x = 1",
            "x += x",
        ])


def test_rhs_can_reference_unadjusted_name():
    # `slop` is referenced but never itself adjusted — fine.
    _, _, _, _, adjs = parse_equations_unified([
        "x = 1",
        "slop = 0.1",
        "x += slop",
    ])
    assert len(adjs) == 1


# =============================================================================
# Comma-broadcast LHS validation
# =============================================================================


def test_comma_broadcast_with_non_name_rejected():
    """LHS must be a bare Name or a tuple of bare Names."""
    with pytest.raises(ValidationError, match="left-hand side must be a name"):
        parse_equations_unified([
            "a = 1",
            "a + 1 += 0.1",
        ])


def test_subscript_lhs_rejected():
    with pytest.raises(ValidationError, match="left-hand side must be a name"):
        parse_equations_unified([
            "arr = [1, 2, 3]",
            "arr[0] += 1",
        ])


# =============================================================================
# Targets must have a value source (post-auto-declare check)
# =============================================================================


def test_adjusted_name_appears_only_as_lhs_becomes_required_param():
    """A name that appears only as adjustment LHS auto-declares as a
    required Param. The user must supply it; missing-required surfaces
    at construction with the standard message.

    No special "value source" check fires at class-define time —
    auto-declare ensures the name is always a Param, and the runtime
    "missing required parameter(s)" / "cannot solve" errors cover
    the no-actual-value case adequately.
    """

    class C(Component):
        equations = """
            x += 0.3   # x has no equation, no default — required from caller
        """

        def build(self):
            return cube(self.x)

    # No kwarg → missing-required.
    with pytest.raises(ValidationError, match="missing required parameter"):
        C()
    # Supply x and the adjustment fires.
    assert C(x=10.0).x == pytest.approx(10.3)


def test_adjusted_name_with_param_declaration_accepted():
    """An explicit Param declaration counts as a value source."""

    class C(Component):
        x = Param(float, default=10.0)
        equations = """
            x += 0.3  # declared via Param
        """

        def build(self):
            return cube(self.x)

    assert C().x == pytest.approx(10.3)


def test_adjusted_name_with_required_param_accepted():
    """Even a required Param (no default) is a value source — the user
    will supply the value via kwargs."""

    class C(Component):
        x = Param(float)
        equations = """
            x += 0.3
        """

        def build(self):
            return cube(self.x)

    assert C(x=10.0).x == pytest.approx(10.3)


# =============================================================================
# Operator coverage / parse-level edge cases
# =============================================================================


def test_double_star_equals_not_an_adjustment():
    """``**=`` is not in the adjustment set; it should fall through to
    constraint/equation parsing and error there."""
    with pytest.raises(ValidationError):
        parse_equations_unified([
            "x = 1",
            "x **= 2",
        ])


def test_floor_div_equals_not_an_adjustment():
    """``//=`` (Python's floor-divide-equals) is not in the adjustment
    set."""
    with pytest.raises(ValidationError):
        parse_equations_unified([
            "x = 1",
            "x //= 2",
        ])


def test_empty_lhs_rejected():
    with pytest.raises(ValidationError):
        parse_equations_unified([
            "+= 1",
        ])


def test_empty_rhs_rejected():
    with pytest.raises(ValidationError):
        parse_equations_unified([
            "x = 1",
            "x +=",
        ])
