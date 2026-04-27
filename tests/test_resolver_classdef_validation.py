"""Class-definition-time validation in parse_equations_unified.

Each test here defines a Component (or calls parse_equations_unified
directly) with a malformed or inconsistent equations list and verifies
the framework rejects it at class definition time, not at construction
time.
"""

from __future__ import annotations

import pytest

from scadwright import Component, Param
from scadwright.component.resolver import parse_equations_unified
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# =============================================================================
# Malformed shapes
# =============================================================================


def test_subscript_in_equation_accepted():
    # ``arr[0] = 5`` is a valid equation: the resolver treats the
    # subscript as a read of ``arr[0]`` and consistency-checks that it
    # equals 5 once ``arr`` is supplied. Subscripts never act as outputs;
    # a tuple Param is supplied as a whole, not via element assignment.
    eqs, _, _ = parse_equations_unified(["arr[0] = 5"])
    assert len(eqs) == 1


def test_attribute_in_equation_accepted():
    # ``spec.foo = 5`` is a valid equation: the resolver reads
    # ``spec.foo`` and consistency-checks once ``spec`` is supplied.
    eqs, _, _ = parse_equations_unified(["spec.foo = 5"])
    assert len(eqs) == 1


def test_chained_assignment_rejected():
    with pytest.raises(ValidationError, match="chained assignment"):
        parse_equations_unified(["x = y = 5"])


def test_walrus_rejected():
    with pytest.raises(ValidationError, match="walrus"):
        parse_equations_unified(["(x := y + 1)"])


def test_malformed_parse_error():
    with pytest.raises(ValidationError, match="cannot parse"):
        parse_equations_unified(["1 + + ="])


def test_empty_string_rejected():
    with pytest.raises(ValidationError, match="cannot parse"):
        parse_equations_unified([""])


# =============================================================================
# Self-reference inconsistency
# =============================================================================


def test_self_reference_simple():
    with pytest.raises(ValidationError, match="self-referential"):
        parse_equations_unified(["x = x - 1"])


def test_self_reference_via_equality():
    with pytest.raises(ValidationError, match="self-referential"):
        parse_equations_unified(["x == x + 5"])


def test_self_reference_consistent_is_ok():
    # x == x reduces to 0 == 0, true. Should not raise.
    eqs, _, _ = parse_equations_unified(["x == x"])
    assert len(eqs) == 1


def test_self_reference_via_component():
    with pytest.raises(ValidationError, match="self-referential"):
        class _Bad(Component):
            equations = ["a = a + 1"]
            def build(self):
                return cube(1)


# =============================================================================
# Mutual inconsistency
# =============================================================================


def test_mutual_inconsistency_two_equations():
    with pytest.raises(ValidationError, match="inconsistent"):
        parse_equations_unified(["a + b == 1", "a + b == 5"])


def test_mutual_inconsistency_three_equations():
    # a = b+1, b = a+1 → a = a+2, no solution.
    with pytest.raises(ValidationError, match="inconsistent"):
        parse_equations_unified([
            "a == b + 1",
            "b == a + 1",
        ])


def test_mutual_consistent_solvable_system_ok():
    # a + b == 5, a - b == 1 → a=3, b=2. Has a solution; should NOT raise.
    eqs, _, _ = parse_equations_unified([
        "a + b == 5",
        "a - b == 1",
    ])
    assert len(eqs) == 2


def test_mutual_underdetermined_ok():
    # Just a = b + 1 with no other constraint — underdetermined, not
    # inconsistent. Should NOT raise.
    eqs, _, _ = parse_equations_unified(["a == b + 1"])
    assert len(eqs) == 1


def test_mutual_inconsistency_via_component():
    with pytest.raises(ValidationError, match="inconsistent"):
        class _Bad(Component):
            equations = ["a == b + 1", "b == a + 1"]
            def build(self):
                return cube(1)


# =============================================================================
# Comma-expansion equation rejection of literal-tuple RHS
# =============================================================================


def test_comma_lhs_with_literal_tuple_rhs_rejected():
    # `x, y = (3, 4)` looks like Python tuple unpacking; in equations
    # the comma broadcasts. Reject the matching-length literal tuple to
    # prevent confusion (OQ 8 resolution).
    with pytest.raises(ValidationError, match="broadcasts"):
        parse_equations_unified(["x, y = (3, 4)"])


def test_comma_lhs_with_literal_list_rhs_rejected():
    with pytest.raises(ValidationError, match="broadcasts"):
        parse_equations_unified(["x, y = [3, 4]"])


def test_comma_lhs_with_scalar_rhs_ok():
    # `x, y = 5` is the broadcast form: each name gets 5. Two equations
    # are produced.
    eqs, _, _ = parse_equations_unified(["x, y = 5"])
    assert len(eqs) == 2


def test_comma_lhs_with_arithmetic_rhs_ok():
    eqs, _, _ = parse_equations_unified(["x, y = a + b"])
    assert len(eqs) == 2


def test_comma_lhs_with_mismatched_length_tuple_ok():
    # `x, y = (a, b, c)` — element count differs from target count, so
    # not the Python-unpack confusion case. Each target gets the tuple.
    eqs, _, _ = parse_equations_unified(["x, y = (a, b, c)"])
    assert len(eqs) == 2


# =============================================================================
# Comma-expansion equations parse to multiple ParsedEquation
# =============================================================================
# Full Component integration of comma-expansion equations requires
# restructuring _register_equations (a later phase); the parser-level
# behavior is verified above.
