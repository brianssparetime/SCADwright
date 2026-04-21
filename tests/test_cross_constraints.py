"""Cross-constraint (var-vs-var inequality) tests."""

from __future__ import annotations

import pytest

from scadwright import Component
from scadwright.errors import ValidationError
from scadwright.primitives import cube


class _IdLessThanOd(Component):
    equations = [
        "id, od > 0",
        "id < od",
    ]

    def build(self):
        return cube([self.od, self.od, 1])


class _CommaLhsForm(Component):
    """`a, b < c` expands to `a < c` AND `b < c`."""

    equations = [
        "a, b, c > 0",
        "a, b < c",
    ]

    def build(self):
        return cube([self.c, self.c, 1])


class _ExpressionRhs(Component):
    """RHS may be an expression: `cap_height < 2 * sphere_r`."""

    equations = [
        "cap_height, sphere_r > 0",
        "cap_height < 2 * sphere_r",
    ]

    def build(self):
        return cube([self.sphere_r, self.sphere_r, self.cap_height])


def test_cross_constraint_passes_when_satisfied():
    obj = _IdLessThanOd(id=4, od=10)
    assert obj.id == 4
    assert obj.od == 10


def test_cross_constraint_fails_with_clear_message():
    with pytest.raises(ValidationError, match=r"id < od"):
        _IdLessThanOd(id=10, od=4)


def test_cross_constraint_includes_offending_values_in_error():
    with pytest.raises(ValidationError, match=r"id=10\.0.*od=4\.0|od=4\.0.*id=10\.0"):
        _IdLessThanOd(id=10, od=4)


def test_cross_constraint_equality_boundary_strict():
    """`id < od` rejects equality (strict less-than)."""
    with pytest.raises(ValidationError, match=r"id < od"):
        _IdLessThanOd(id=5, od=5)


def test_cross_constraint_comma_lhs_expansion():
    obj = _CommaLhsForm(a=1, b=2, c=10)
    assert obj.a == 1


def test_cross_constraint_comma_lhs_fails_for_either_violator():
    # b violates: 5 not < 5
    with pytest.raises(ValidationError, match=r"b < c"):
        _CommaLhsForm(a=1, b=5, c=5)
    # a violates: 7 not < 5
    with pytest.raises(ValidationError, match=r"a < c"):
        _CommaLhsForm(a=7, b=1, c=5)


def test_cross_constraint_expression_rhs_passes():
    obj = _ExpressionRhs(cap_height=5, sphere_r=10)  # 5 < 20
    assert obj.cap_height == 5


def test_cross_constraint_expression_rhs_fails():
    # 25 not < 2*10 = 20
    with pytest.raises(ValidationError, match=r"cap_height < 2\*sphere_r"):
        _ExpressionRhs(cap_height=25, sphere_r=10)
