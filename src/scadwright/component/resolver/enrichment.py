"""Best-effort enrichment of a failed-constraint AST into a message.

When a constraint fires, the bare ``constraint violated: <expr>``
message often isn't enough — we want ``left=N, right=M`` for a top-level
``Compare``, and ``failed at index I with var=value`` for an
``all(... for ... in ...)`` shape. The enrichers here run after a
constraint fails and graft those details onto the diagnostic.
"""

from __future__ import annotations

import ast
from typing import Any


def _enrich_constraint_failure(node: ast.AST, namespace: dict) -> str | None:
    """Best-effort: turn a failed constraint AST into a message naming
    the offending values.

    Top-level ``Compare``: show ``left=`` and ``right=``.
    ``all(<genexp>)``: locate the first item that fails; show its index
    and the offending element's value.
    Other shapes: return ``None`` and the caller uses a raw-only
    message.
    """
    try:
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            lhs_val = _compile_and_eval(node.left, namespace)
            rhs_val = _compile_and_eval(node.comparators[0], namespace)
            return f"left={lhs_val!r}, right={rhs_val!r}"

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "all"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.GeneratorExp)
        ):
            return _enrich_all_genexp(node.args[0], namespace)

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in (
                "exactly_one", "at_least_one", "at_most_one", "all_or_none",
            )
        ):
            parts = []
            for arg in node.args:
                name = ast.unparse(arg)
                val = _compile_and_eval(arg, namespace)
                parts.append(f"{name}={val!r}")
            return ", ".join(parts)
    except Exception:
        return None
    return None


def _enrich_all_genexp(genexp: ast.GeneratorExp, namespace: dict) -> str | None:
    """For ``all(elt for var in iter if ...)``, find the first item that
    makes ``elt`` false and report its index and value.
    """
    if len(genexp.generators) != 1:
        return None
    c = genexp.generators[0]
    if not isinstance(c.target, ast.Name):
        return None

    var_name = c.target.id
    try:
        seq = _compile_and_eval(c.iter, namespace)
    except Exception:
        return None

    elt_code = _compile_eval_code(genexp.elt)
    filter_codes = [_compile_eval_code(f) for f in c.ifs]

    for i, item in enumerate(seq):
        local_ns = dict(namespace)
        local_ns[var_name] = item
        try:
            if not all(bool(eval(fc, local_ns)) for fc in filter_codes):
                continue
        except Exception:
            continue
        try:
            elt_result = eval(elt_code, local_ns)
        except Exception:
            return f"failed at index {i} with {var_name}={item!r}"
        if bool(elt_result):
            continue
        if isinstance(genexp.elt, ast.Compare) and len(genexp.elt.ops) == 1:
            try:
                left = _compile_and_eval(genexp.elt.left, local_ns)
                right = _compile_and_eval(genexp.elt.comparators[0], local_ns)
                return (
                    f"failed at index {i} with {var_name}={item!r}: "
                    f"left={left!r}, right={right!r}"
                )
            except Exception:
                pass
        return f"failed at index {i} with {var_name}={item!r}"
    return None


def _compile_and_eval(node: ast.AST, namespace: dict) -> Any:
    code = _compile_eval_code(node)
    return eval(code, namespace)


def _compile_eval_code(node: ast.AST):
    expr = ast.Expression(body=node)
    ast.fix_missing_locations(expr)
    return compile(expr, "<enrich>", "eval")
