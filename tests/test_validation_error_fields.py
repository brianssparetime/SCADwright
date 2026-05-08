"""Tests for the equations-side fields on ``ValidationError``.

Programmatic consumers read ``equations_source_index`` (and where
available ``equations_node``) directly off raised
``ValidationError`` objects to compute diagnostic ranges, rather
than parsing the formatted message. Each raise path that
originates from an equations block must populate at least the
source index. Paths that have an offending AST sub-node in scope
must also populate the node so the diagnostic can highlight just
the problem token.

Tests group by raise location: parsing.py first, then checks.py.
Each test triggers the specific raise with a minimal equations
input and asserts the structured fields.
"""

from __future__ import annotations

import ast

import pytest

from scadwright.component.resolver import parse_equations_unified
from scadwright.errors import ValidationError


def _expect_eq_error(eqs, *, class_name: str = "T"):
    with pytest.raises(ValidationError) as excinfo:
        parse_equations_unified(eqs, class_name=class_name)
    return excinfo.value


# =============================================================================
# parsing.py raise sites
# =============================================================================


def test_chained_equals_carries_source_index() -> None:
    err = _expect_eq_error(["x = y = 5"])
    assert err.equations_source_index == 0
    assert err.equations_node is None  # no specific node


def test_chained_equals_on_second_line_carries_correct_index() -> None:
    err = _expect_eq_error(["x = 1", "y = z = 2"])
    assert err.equations_source_index == 1


def test_empty_side_of_equation_carries_source_index() -> None:
    err = _expect_eq_error(["= 5"])
    assert err.equations_source_index == 0


def test_unknown_type_tag_carries_source_index() -> None:
    err = _expect_eq_error(["?x:floot = 5"])
    assert err.equations_source_index == 0
    assert "unknown" in str(err).lower()


def test_type_disagreement_carries_source_index_of_second_site() -> None:
    err = _expect_eq_error(["?x:int = 5", "?x:str = 'a'"])
    # The error fires when the second site is processed.
    assert err.equations_source_index == 1


def test_parse_failure_syntax_error_carries_source_index() -> None:
    err = _expect_eq_error(["x = 5 +"])
    assert err.equations_source_index == 0


def test_walrus_carries_source_index_and_node() -> None:
    err = _expect_eq_error(["x = (y := 5)"])
    assert err.equations_source_index == 0
    assert isinstance(err.equations_node, ast.NamedExpr)


def test_comma_broadcast_literal_tuple_rhs_carries_node() -> None:
    err = _expect_eq_error(["x, y = 1, 2"])
    assert err.equations_source_index == 0
    assert isinstance(err.equations_node, ast.Tuple)


def test_empty_adjustment_lhs_carries_source_index() -> None:
    err = _expect_eq_error([" += 1"])
    assert err.equations_source_index == 0


def test_empty_adjustment_rhs_carries_source_index() -> None:
    err = _expect_eq_error(["x += "])
    assert err.equations_source_index == 0


def test_bad_adjustment_lhs_carries_node() -> None:
    err = _expect_eq_error(["x[0] += 1"])
    assert err.equations_source_index == 0
    # The offending LHS expression is captured.
    assert err.equations_node is not None
    assert isinstance(err.equations_node, ast.Subscript)


def test_adjusted_keyword_arg_carries_node() -> None:
    err = _expect_eq_error(["x > 0", "adjusted(name=x) > 0"])
    assert err.equations_source_index == 1
    assert isinstance(err.equations_node, ast.Call)


def test_adjusted_wrong_arg_count_carries_node() -> None:
    err = _expect_eq_error(["x > 0", "adjusted(x, y) > 0"])
    assert err.equations_source_index == 1
    assert isinstance(err.equations_node, ast.Call)


def test_adjusted_non_name_arg_carries_node() -> None:
    err = _expect_eq_error(["x > 0", "adjusted(x + 1) > 0"])
    assert err.equations_source_index == 1
    # The offending argument is a BinOp.
    assert isinstance(err.equations_node, ast.BinOp)


def test_not_a_boolean_rule_carries_node() -> None:
    err = _expect_eq_error(["5"])
    assert err.equations_source_index == 0
    # The constraint expression itself is the offender.
    assert err.equations_node is not None


# =============================================================================
# checks.py raise sites
# =============================================================================


def test_bool_in_arithmetic_carries_node() -> None:
    # Line 0 declares ``direction`` with a bool tag via a no-op predicate.
    err = _expect_eq_error([
        "?direction:bool or True",
        "y = direction * 2",
    ])
    assert err.equations_source_index == 1
    assert isinstance(err.equations_node, ast.Name)
    assert err.equations_node.id == "direction"


def test_bool_in_numeric_call_carries_node() -> None:
    err = _expect_eq_error([
        "?direction:bool or True",
        "y = sin(direction)",
    ])
    assert err.equations_source_index == 1
    assert isinstance(err.equations_node, ast.Name)
    assert err.equations_node.id == "direction"


def test_override_unsafe_carries_source_index_and_rhs_node() -> None:
    # ?x with a None default and an RHS that fails on None: pure arithmetic
    # without a None-safe shape raises TypeError when x=None.
    err = _expect_eq_error(["?x = x + 1"])
    assert err.equations_source_index == 0
    assert err.equations_node is not None  # the eq.rhs expr


def test_non_float_solver_target_carries_source_index_and_target_node() -> None:
    # ?count:int as a derived bare-Name target with no override pattern.
    err = _expect_eq_error(["?count:int = a + b"])
    assert err.equations_source_index == 0
    assert isinstance(err.equations_node, ast.Name)
    assert err.equations_node.id == "count"


def test_double_equals_outside_if_carries_compare_node() -> None:
    err = _expect_eq_error(["x == 5"])
    assert err.equations_source_index == 0
    assert isinstance(err.equations_node, ast.Compare)


def test_unknown_function_call_carries_func_node() -> None:
    err = _expect_eq_error(["y = snh(x)"])
    assert err.equations_source_index == 0
    # The offending Name (the callee) is captured.
    assert isinstance(err.equations_node, ast.Name)
    assert err.equations_node.id == "snh"


def test_self_referential_equation_carries_source_index() -> None:
    err = _expect_eq_error(["x = x - 1"])
    assert err.equations_source_index == 0


def test_adjusted_outside_rule_carries_call_node() -> None:
    # adjusted() inside an equation's RHS — invalid context.
    err = _expect_eq_error(["y = adjusted(x) + 1", "x += 1  # comment"])
    assert err.equations_source_index == 0
    assert isinstance(err.equations_node, ast.Call)


def test_adjustment_uniformity_carries_source_index() -> None:
    err = _expect_eq_error([
        "x += 1  # bump",
        "x *= 2  # scale",
    ])
    # The mismatch fires on the second line.
    assert err.equations_source_index == 1


def test_adjustment_rhs_references_adjusted_carries_node() -> None:
    err = _expect_eq_error([
        "a += 1  # bumpA",
        "b += a  # bumpB",
    ])
    assert err.equations_source_index == 1
    # The offending RHS expression — a Name.
    assert err.equations_node is not None


def test_mutual_inconsistency_carries_primary_index() -> None:
    err = _expect_eq_error([
        "x = 1",
        "x = 2",
    ])
    # Multi-line error; primary index is the lowest-indexed offender.
    assert err.equations_source_index == 0


# =============================================================================
# Negative test: non-equations raise paths leave the fields as None
# =============================================================================


def test_non_equation_validation_error_leaves_fields_none() -> None:
    err = ValidationError("just a factory error")
    assert err.equations_source_index is None
    assert err.equations_node is None


def test_explicit_keyword_passes_through() -> None:
    node = ast.Name(id="x", ctx=ast.Load())
    err = ValidationError(
        "msg", equations_source_index=3, equations_node=node,
    )
    assert err.equations_source_index == 3
    assert err.equations_node is node


# =============================================================================
# equations_colmap is attached by parse_equations_unified
# =============================================================================


def test_colmap_attached_for_per_line_error() -> None:
    # Error fires inside the per-line loop (unknown type tag).
    err = _expect_eq_error(["?x:floot = 5"])
    assert err.equations_source_index == 0
    # The colmap covers the cleaned line "x = 5" — 5 chars.
    assert err.equations_colmap is not None
    assert len(err.equations_colmap) == len("x = 5")


def test_colmap_attached_for_post_loop_check_error() -> None:
    # Error fires from a _check_* pass (after the per-line loop).
    err = _expect_eq_error(["y = snh(x)"])
    assert err.equations_source_index == 0
    # Cleaned line has no annotations; colmap is the identity over its
    # length.
    assert err.equations_colmap == tuple(range(len("y = snh(x)")))


def test_colmap_for_line_with_question_sigil() -> None:
    err = _expect_eq_error([
        "?direction:bool or True",
        "y = direction * 2",
    ])
    assert err.equations_source_index == 1
    # Line 1 cleaned is "y = direction * 2" — no annotations, identity.
    assert err.equations_colmap == tuple(range(len("y = direction * 2")))


def test_colmap_default_none_for_non_equations_error() -> None:
    err = ValidationError("just a factory error")
    assert err.equations_colmap is None
