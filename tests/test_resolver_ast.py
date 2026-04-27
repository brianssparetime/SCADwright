"""Tests for src/scadwright/component/resolver_ast.py.

Pure-utility tests for the AST helpers used by the iterative resolver
(see design_docs/collapse_eq.md, Phase 1). No integration with the
Component pipeline; these exercise the functions in isolation.
"""

from __future__ import annotations

import ast
from collections import namedtuple

import pytest

from scadwright.component.resolver_ast import (
    find_unknowns,
    is_fully_algebraic,
    substitute_knowns,
)


def _expr(src: str) -> ast.AST:
    """Parse ``src`` as a Python expression and return its AST node."""
    return ast.parse(src, mode="eval").body


# =============================================================================
# find_unknowns
# =============================================================================


def test_find_unknowns_simple_arithmetic():
    node = _expr("a + b")
    assert find_unknowns(node, {"a": 1}) == {"b"}


def test_find_unknowns_all_known():
    node = _expr("a + b")
    assert find_unknowns(node, {"a": 1, "b": 2}) == set()


def test_find_unknowns_none_known():
    node = _expr("a + b * c")
    assert find_unknowns(node, {}) == {"a", "b", "c"}


def test_find_unknowns_accepts_dict_or_set():
    node = _expr("a + b")
    assert find_unknowns(node, {"a", "b"}) == set()
    assert find_unknowns(node, frozenset({"a"})) == {"b"}


def test_find_unknowns_constant_only():
    node = _expr("1 + 2 * 3")
    assert find_unknowns(node, {}) == set()


def test_find_unknowns_excludes_comprehension_target():
    # Loop variable `i` is bound inside the genexp, not free.
    node = _expr("tuple(i * x for i in range(n))")
    knowns = {"tuple": tuple, "range": range, "x": 1, "n": 5}
    assert find_unknowns(node, knowns) == set()


def test_find_unknowns_includes_genexp_iter_free_vars():
    node = _expr("tuple(i * x for i in range(n))")
    # `n` and `x` are free; `i` is bound.
    assert find_unknowns(node, {"tuple": tuple, "range": range}) == {"n", "x"}


def test_find_unknowns_attribute_access_only_tracks_root():
    node = _expr("spec.d + offset")
    # `spec.d` references `spec`, not `d`.
    assert find_unknowns(node, {"spec": object()}) == {"offset"}


def test_find_unknowns_subscript():
    node = _expr("arr[0] + arr[1]")
    assert find_unknowns(node, {"arr": (1, 2)}) == set()


def test_find_unknowns_conditional():
    node = _expr("a if cond else b")
    assert find_unknowns(node, {"cond": True}) == {"a", "b"}


def test_find_unknowns_function_call():
    node = _expr("max(a, b)")
    assert find_unknowns(node, {"max": max}) == {"a", "b"}


def test_find_unknowns_curated_namespace_via_knowns():
    # When the curated namespace is folded into knowns, `len` and `range`
    # don't show up as unknown.
    node = _expr("len(range(n))")
    knowns = {"len": len, "range": range, "n": 5}
    assert find_unknowns(node, knowns) == set()


def test_find_unknowns_lambda_args_are_bound():
    node = _expr("(lambda y: y + x)(z)")
    # `y` is bound by the lambda; `x` and `z` are free.
    assert find_unknowns(node, {}) == {"x", "z"}


def test_find_unknowns_nested_comprehension():
    node = _expr("tuple((i, j) for i in range(n) for j in range(m))")
    # `i`, `j` are bound; `n`, `m`, `range`, `tuple` are referenced.
    knowns = {"tuple": tuple, "range": range}
    assert find_unknowns(node, knowns) == {"n", "m"}


# =============================================================================
# substitute_knowns
# =============================================================================


def test_substitute_collapses_constant_arithmetic():
    node = _expr("a + b * 2")
    new = substitute_knowns(node, {"a": 3, "b": 4})
    assert isinstance(new, ast.Constant)
    assert new.value == 11


def test_substitute_partial_replaces_known_names_only():
    node = _expr("a + b + c")
    new = substitute_knowns(node, {"a": 5})
    # The whole thing isn't computable, but `a` should be replaced.
    # Resulting structure: BinOp(BinOp(Constant(5), +, Name(b)), +, Name(c))
    assert isinstance(new, ast.BinOp)
    # Walk to confirm `a` is gone but `b` and `c` are still Names.
    names = {n.id for n in ast.walk(new) if isinstance(n, ast.Name)}
    assert names == {"b", "c"}
    # And there's a Constant(5) somewhere.
    constants = [
        n.value for n in ast.walk(new) if isinstance(n, ast.Constant)
    ]
    assert 5 in constants


def test_substitute_handles_attribute_access():
    Spec = namedtuple("Spec", "d length")
    s = Spec(d=14.5, length=50.5)
    node = _expr("spec.d + offset")
    new = substitute_knowns(node, {"spec": s, "offset": 1.5})
    assert isinstance(new, ast.Constant)
    assert new.value == pytest.approx(16.0)


def test_substitute_partial_with_attribute():
    Spec = namedtuple("Spec", "d")
    s = Spec(d=10)
    node = _expr("spec.d + unknown")
    new = substitute_knowns(node, {"spec": s})
    # `spec.d` collapses to 10; `unknown` stays.
    assert isinstance(new, ast.BinOp)
    constants = [
        n.value for n in ast.walk(new) if isinstance(n, ast.Constant)
    ]
    assert 10 in constants
    names = {n.id for n in ast.walk(new) if isinstance(n, ast.Name)}
    assert "unknown" in names


def test_substitute_max_call_fully_known():
    node = _expr("max(a, b, c)")
    namespace = {"max": max}
    new = substitute_knowns(node, {"a": 3, "b": 7, "c": 5}, namespace)
    assert isinstance(new, ast.Constant)
    assert new.value == 7


def test_substitute_max_call_partially_known_doesnt_collapse():
    node = _expr("max(a, b, c)")
    namespace = {"max": max}
    new = substitute_knowns(node, {"a": 3}, namespace)
    # max() has unknowns; can't collapse the call. Names a → Constant(3),
    # but b, c remain as Names.
    assert isinstance(new, ast.Call)
    constants = [
        n.value for n in ast.walk(new) if isinstance(n, ast.Constant)
    ]
    assert 3 in constants
    names = {n.id for n in ast.walk(new) if isinstance(n, ast.Name)}
    assert "b" in names and "c" in names


def test_substitute_comprehension_fully_known():
    node = _expr("tuple(i * x for i in range(n))")
    namespace = {"tuple": tuple, "range": range}
    new = substitute_knowns(node, {"x": 2, "n": 4}, namespace)
    assert isinstance(new, ast.Constant)
    assert new.value == (0, 2, 4, 6)


def test_substitute_does_not_modify_input():
    src = "a + b * c"
    node = _expr(src)
    before = ast.dump(node)
    substitute_knowns(node, {"a": 1, "b": 2, "c": 3})
    after = ast.dump(node)
    assert before == after


def test_substitute_eval_failure_leaves_node():
    # Division by zero should leave the node unsubstituted, not raise.
    node = _expr("a / b")
    new = substitute_knowns(node, {"a": 1, "b": 0})
    # Eval would raise ZeroDivisionError; we keep the structure.
    # The names should still be substituted to Constants but the BinOp
    # itself doesn't collapse.
    assert isinstance(new, ast.BinOp)


def test_substitute_none_propagation_leaves_arithmetic_intact():
    # Substituting None into arithmetic raises TypeError; the function
    # should leave the node alone rather than crash.
    node = _expr("a + b")
    new = substitute_knowns(node, {"a": None, "b": 1})
    assert isinstance(new, ast.BinOp)


def test_substitute_none_propagation_through_is_none():
    # `a is None` evaluates fine even with a=None; should collapse.
    node = _expr("a is None")
    new = substitute_knowns(node, {"a": None})
    assert isinstance(new, ast.Constant)
    assert new.value is True


def test_substitute_conditional_with_known_branches():
    node = _expr("a if cond else b")
    new = substitute_knowns(
        node, {"a": "yes", "b": "no", "cond": True}
    )
    assert isinstance(new, ast.Constant)
    assert new.value == "yes"


def test_substitute_with_curated_namespace():
    # Mimic how the resolver will pass curated builtins.
    namespace = {"len": len, "range": range}
    node = _expr("len(range(n))")
    new = substitute_knowns(node, {"n": 5}, namespace)
    assert isinstance(new, ast.Constant)
    assert new.value == 5


# =============================================================================
# is_fully_algebraic
# =============================================================================


def test_algebraic_arithmetic():
    assert is_fully_algebraic(_expr("a + b"))
    assert is_fully_algebraic(_expr("a * b - c / 2"))
    assert is_fully_algebraic(_expr("-a"))
    assert is_fully_algebraic(_expr("a ** 2"))


def test_algebraic_constants():
    assert is_fully_algebraic(_expr("1"))
    assert is_fully_algebraic(_expr("3.14"))
    assert is_fully_algebraic(_expr("-2.5"))


def test_algebraic_bool_constant_rejected():
    # bool is technically int subclass; explicitly excluded.
    assert not is_fully_algebraic(_expr("True"))


def test_algebraic_with_sympy_function():
    assert is_fully_algebraic(_expr("sin(theta)"))
    assert is_fully_algebraic(_expr("sqrt(x)"))
    assert is_fully_algebraic(_expr("max(a, b)"))
    assert is_fully_algebraic(_expr("min(a, b, c)"))


def test_algebraic_compare():
    assert is_fully_algebraic(_expr("a < b"))
    assert is_fully_algebraic(_expr("a + 1 == b"))


def test_not_algebraic_attribute():
    assert not is_fully_algebraic(_expr("spec.d + a"))


def test_not_algebraic_subscript():
    assert not is_fully_algebraic(_expr("arr[0]"))


def test_not_algebraic_conditional():
    assert not is_fully_algebraic(_expr("a if cond else b"))


def test_not_algebraic_comprehension():
    assert not is_fully_algebraic(_expr("tuple(i for i in range(n))"))


def test_not_algebraic_unknown_function():
    assert not is_fully_algebraic(_expr("foo(x)"))


def test_not_algebraic_call_with_kwargs():
    # Even known functions can't be sympified with keyword arguments.
    assert not is_fully_algebraic(_expr("max(a, default=0)"))


def test_not_algebraic_string_constant():
    assert not is_fully_algebraic(_expr("'hello'"))


def test_not_algebraic_list_literal():
    assert not is_fully_algebraic(_expr("[a, b]"))


def test_algebraic_tuple_of_names():
    # Comma-expanded constraint LHS shape.
    assert is_fully_algebraic(_expr("(a, b, c)"))


def test_not_algebraic_tuple_with_arithmetic():
    # Tuples in algebraic shape must be names only.
    assert not is_fully_algebraic(_expr("(a, b + 1)"))
