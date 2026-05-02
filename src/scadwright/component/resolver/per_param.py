"""Per-Param validator extraction from ``name OP numeric_constant`` constraints.

A constraint that compares a Param against a literal numeric bound
(``count > 0``, ``angle <= 180``, etc.) compiles to a per-Param
validator which fires both during normal resolution and on direct
``Param.__set__`` calls. This module is the recognizer.
"""

from __future__ import annotations

import ast

from scadwright.component.resolver.types import ParsedConstraint
from scadwright.errors import ValidationError


def extract_per_param_validator(c: ParsedConstraint):
    """If ``c`` is a ``name OP numeric_constant`` shape, return
    ``(name, validator_callable)``. Otherwise return ``None``.

    The constraint is also evaluated by the resolver at construction
    time; attaching a per-Param validator additionally fail-fast on any
    direct ``Param.__set__`` call (e.g., for user-supplied bad inputs
    that don't trigger an equation in the resolver loop).
    """
    if not isinstance(c.expr, ast.Compare):
        return None
    if len(c.expr.ops) != 1:
        return None
    if not isinstance(c.expr.left, ast.Name):
        return None
    if len(c.expr.comparators) != 1:
        return None

    op = c.expr.ops[0]
    rhs = c.expr.comparators[0]
    bound = _extract_numeric_constant(rhs)
    if bound is None:
        return None

    name = c.expr.left.id

    from scadwright.component.params import (
        _positive_impl, _non_negative_impl,
        _minimum_impl, _maximum_impl,
    )

    if isinstance(op, ast.Gt):
        if bound == 0:
            return (name, _positive_impl)
        return (name, _strict_gt(bound))
    if isinstance(op, ast.GtE):
        if bound == 0:
            return (name, _non_negative_impl)
        return (name, _minimum_impl(bound))
    if isinstance(op, ast.Lt):
        return (name, _strict_lt(bound))
    if isinstance(op, ast.LtE):
        return (name, _maximum_impl(bound))
    return None


def _extract_numeric_constant(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return None
        if isinstance(node.value, (int, float)):
            return float(node.value)
        return None
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, (ast.UAdd, ast.USub))
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
        and not isinstance(node.operand.value, bool)
    ):
        sign = 1.0 if isinstance(node.op, ast.UAdd) else -1.0
        return sign * float(node.operand.value)
    return None


def _strict_gt(bound: float):
    def check(x, _b=bound):
        if not (x > _b):
            raise ValidationError(f"must be > {_b}, got {x}")
    return check


def _strict_lt(bound: float):
    def check(x, _b=bound):
        if not (x < _b):
            raise ValidationError(f"must be < {_b}, got {x}")
    return check
