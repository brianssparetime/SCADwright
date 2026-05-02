"""AST → sympy conversion plus the sufficient-input-subset enumerator.

All sympy access is funnelled through this module: the algebraic-function
table is built lazily on first use, and the rest of the subpackage hands
ASTs in and gets sympy expressions out.
"""

from __future__ import annotations

import ast
from typing import Any

from scadwright.component.resolver.types import ParsedEquation
from scadwright.component.resolver_ast import is_fully_algebraic


_ALGEBRAIC_FUNCTIONS = None  # populated lazily; needs sympy


def _ensure_algebraic_functions() -> dict:
    """Lazy import of sympy to build the algebraic function table.

    Trig wrappers fold the degree↔radian conversion into the symbolic
    tree itself (`sp.sin(x * sp.pi / 180)` and friends). This keeps the
    DSL aligned with `scadwright.math` (degrees in, degrees out) while
    still giving sympy a fully-symbolic expression to solve, simplify,
    and substitute through.
    """
    global _ALGEBRAIC_FUNCTIONS
    if _ALGEBRAIC_FUNCTIONS is None:
        import sympy as sp
        _ALGEBRAIC_FUNCTIONS = {
            "sin": lambda x: sp.sin(x * sp.pi / 180),
            "cos": lambda x: sp.cos(x * sp.pi / 180),
            "tan": lambda x: sp.tan(x * sp.pi / 180),
            "asin": lambda x: sp.asin(x) * 180 / sp.pi,
            "acos": lambda x: sp.acos(x) * 180 / sp.pi,
            "atan": lambda x: sp.atan(x) * 180 / sp.pi,
            "atan2": lambda y, x: sp.atan2(y, x) * 180 / sp.pi,
            "degrees": lambda x: x * 180 / sp.pi,
            "radians": lambda x: x * sp.pi / 180,
            "sqrt": sp.sqrt, "log": sp.log, "exp": sp.exp,
            "abs": sp.Abs, "ceil": sp.ceiling, "floor": sp.floor,
            "min": sp.Min, "max": sp.Max,
            "Min": sp.Min, "Max": sp.Max,
        }
    return _ALGEBRAIC_FUNCTIONS


def ast_to_sympy(
    node: ast.AST,
    symbols: dict[str, Any],
    knowns: dict[str, Any] | None = None,
):
    """Convert a fully-algebraic AST to a sympy expression.

    ``symbols`` maps unknown name → sympy Symbol. ``knowns`` (optional)
    maps a concrete-valued name → its numeric value, which is sympified
    inline. A Name not in either raises ValueError.
    """
    import sympy as sp

    knowns = knowns or {}
    funcs = _ensure_algebraic_functions()

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise ValueError("bool constants not supported")
        return sp.sympify(node.value)
    if isinstance(node, ast.Name):
        if node.id in symbols:
            return symbols[node.id]
        if node.id in knowns:
            return sp.sympify(knowns[node.id])
        raise ValueError(f"undefined name {node.id!r}")
    if isinstance(node, ast.UnaryOp):
        operand = ast_to_sympy(node.operand, symbols, knowns)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError(f"unsupported unary op {type(node.op).__name__}")
    if isinstance(node, ast.BinOp):
        left = ast_to_sympy(node.left, symbols, knowns)
        right = ast_to_sympy(node.right, symbols, knowns)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            return left ** right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        raise ValueError(f"unsupported binary op {type(node.op).__name__}")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.keywords:
            raise ValueError("keyword arguments not supported in algebraic calls")
        sympy_func = funcs.get(node.func.id)
        if sympy_func is None:
            raise ValueError(f"non-algebraic call {node.func.id!r}")
        args = [ast_to_sympy(a, symbols, knowns) for a in node.args]
        return sympy_func(*args)
    raise ValueError(f"unsupported AST node {type(node).__name__}")


# =============================================================================
# Sufficient-input enumeration for "need one of" error messages
# =============================================================================


def _sufficient_subsets(
    equations: list[ParsedEquation], existing_knowns: set[str]
) -> list[frozenset[str]]:
    """Enumerate minimal subsets of equation variables which, if supplied,
    would let the system resolve. Used to populate "need one of: {a},
    {b, c}, ..." in insufficient-input error messages.
    """
    import sympy as sp
    from itertools import combinations

    algebraic = [
        eq for eq in equations
        if is_fully_algebraic(eq.lhs) and is_fully_algebraic(eq.rhs)
    ]
    if not algebraic:
        return []

    # All eq vars across the algebraic equations.
    eq_vars: set[str] = set()
    for eq in algebraic:
        eq_vars |= eq.referenced_names
    eq_vars -= existing_knowns - eq_vars  # only consider eq-relevant
    eq_vars_list = sorted(eq_vars)
    n_vars = len(eq_vars_list)
    n_eqs = len(algebraic)
    min_given = max(0, n_vars - n_eqs)

    symbols = {n: sp.Symbol(n) for n in eq_vars_list}
    sympy_eqs = []
    try:
        for eq in algebraic:
            le = ast_to_sympy(eq.lhs, symbols)
            re = ast_to_sympy(eq.rhs, symbols)
            sympy_eqs.append(sp.Eq(le, re))
    except Exception:
        return []

    sufficient: list[frozenset[str]] = []
    # Cap subset enumeration at a reasonable size to avoid blowup.
    max_size = min(n_vars, min_given + 3)
    for size in range(min_given, max_size + 1):
        for combo in combinations(eq_vars_list, size):
            combo_set = frozenset(combo)
            # Substitute dummy values for the combo and try to solve the
            # remaining unknowns.
            subs = {symbols[v]: sp.sympify(1.0) for v in combo}
            unknowns = [
                symbols[v] for v in eq_vars_list if v not in combo_set
            ]
            if not unknowns:
                sufficient.append(combo_set)
                continue
            try:
                substituted = []
                for eq in sympy_eqs:
                    s = eq.subs(subs)
                    if s is sp.true:
                        continue
                    if s is sp.false:
                        # Inconsistent with dummy values; combo might
                        # still be sufficient with real values, so accept.
                        substituted = None
                        break
                    substituted.append(s)
            except Exception:
                continue
            if substituted is None:
                sufficient.append(combo_set)
                continue
            if not substituted:
                sufficient.append(combo_set)
                continue
            try:
                res = sp.solve(substituted, unknowns, dict=True)
            except (NotImplementedError, Exception):
                continue
            if res:
                sufficient.append(combo_set)

    # Drop strict supersets (keep only minimal combinations).
    sufficient.sort(key=len)
    minimal: list[frozenset[str]] = []
    for s in sufficient:
        if not any(m < s for m in minimal):
            minimal.append(s)
    return minimal
