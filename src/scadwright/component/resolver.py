"""Iterative resolver for the equations DSL.

Given a parsed list of equations and constraints plus the user's
supplied values, the resolver iteratively fills in unknowns until it
either succeeds or produces an explanatory error (insufficient,
inconsistent, or ambiguous).

Currently gated behind ``_use_iterative_resolver = True`` on a
Component subclass; non-opt-in Components use the legacy bucketed
pipeline. Both paths coexist while the new model is validated.

Three public entities:

- ``ParsedEquation`` and ``ParsedConstraint``: dataclass shapes the
  resolver consumes.
- ``parse_equations_unified``: converts the raw equations list (plus
  per-line optional sets) into the unified representation.
- ``IterativeResolver``: the resolver itself. Construct with the parsed
  data and supplied values, call ``resolve()``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Sequence

from scadwright.component.params import Param
from scadwright.component.resolver_ast import (
    find_unknowns,
    is_fully_algebraic,
    substitute_knowns,
)
from scadwright.component.resolver_ast import _free_names as _free_names_in
from scadwright.errors import ValidationError


# =============================================================================
# Unified representation
# =============================================================================


@dataclass(frozen=True)
class ParsedEquation:
    """A single equation: an assertion that ``lhs`` and ``rhs`` are equal.

    The ``=`` and ``==`` forms produce structurally identical entries.
    Per the spec, both have the same semantics: any bare-Name side is a
    candidate target the resolver can fill or the user can supply, and
    a non-bare side is computed or consistency-checked.

    ``source_line_index`` is the 0-based position of the originating line
    in the user's ``equations`` list. Comma-broadcast siblings share the
    same index. Used to surface the offending line in error messages.
    """
    raw: str
    lhs: ast.AST
    rhs: ast.AST
    referenced_names: frozenset[str]
    line_optionals: frozenset[str]
    source_line_index: int


# =============================================================================
# AST → sympy conversion
# =============================================================================


_ALGEBRAIC_FUNCTIONS = None  # populated lazily; needs sympy


def _ensure_algebraic_functions() -> dict:
    """Lazy import of sympy to build the algebraic function table."""
    global _ALGEBRAIC_FUNCTIONS
    if _ALGEBRAIC_FUNCTIONS is None:
        import sympy as sp
        _ALGEBRAIC_FUNCTIONS = {
            "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
            "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
            "atan2": sp.atan2,
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


@dataclass(frozen=True)
class ParsedConstraint:
    """A single constraint: a boolean expression that must hold.

    ``source_line_index`` is the 0-based position of the originating line
    in the user's ``equations`` list. Comma-broadcast siblings share the
    same index.
    """
    raw: str
    expr: ast.AST
    referenced_names: frozenset[str]
    line_optionals: frozenset[str]
    source_line_index: int


# =============================================================================
# Class-definition-time error prefix helpers
# =============================================================================
#
# Mirror the runtime ``IterativeResolver._loc`` / ``_loc_multi`` shape so the
# user sees a consistent ``ClassName.equations[N]:`` prefix in every error,
# whether it fires at class-define time (parsing/inconsistency checks) or at
# instantiation (resolver). ``class_name`` is empty when ``parse_equations_unified``
# is called without a class context (e.g. from tests); the prefix degrades to
# just ``equations[N]:``.


def _classdef_loc(class_name: str, source_index: int) -> str:
    base = f"equations[{source_index}]"
    return f"{class_name}.{base}" if class_name else base


def _classdef_loc_multi(class_name: str, items) -> str:
    unique = sorted({i.source_line_index for i in items})
    base = f"equations[{', '.join(str(i) for i in unique)}]"
    return f"{class_name}.{base}" if class_name else base


def _split_top_level_equals(
    line: str, class_name: str = "", source_index: int = 0,
) -> tuple[str, str] | None:
    """Find the single top-level ``=`` (or ``==``) and split the line.

    Returns ``(lhs_text, rhs_text)`` if exactly one top-level equality
    operator is found, else ``None`` (the line is a constraint, not an
    equation).

    "Top-level" means: not inside ``(...)``, ``[...]``, ``{...}``, not
    inside a single/double/triple-quoted string, not inside a ``#``
    comment. The scanner treats ``==``, ``<=``, ``>=``, ``!=`` as a
    single non-equation operator: only a lone ``=`` or a lone ``==``
    counts as the equation operator.

    Multiple top-level equality operators raise ``ValidationError``
    (chained assignment / over-specified line). The caller controls the
    error message; this helper raises with a descriptive prefix that
    callers can extend.

    The function returns text fragments rather than ASTs so the caller
    can run ``ast.parse(..., mode='eval')`` on each side independently —
    each side is a Python expression in scadwright's equation syntax,
    not an assignment target.
    """
    n = len(line)
    i = 0
    found: list[tuple[int, int]] = []  # (start, end) positions of the operator
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    while i < n:
        c = line[i]

        # Triple-quoted string: skip through the closing triple.
        if c in ("'", '"') and i + 2 < n and line[i + 1] == c and line[i + 2] == c:
            end = line.find(c * 3, i + 3)
            if end == -1:
                # Unterminated triple-quote; let the parser surface it.
                i = n
                break
            i = end + 3
            continue

        # Single- or double-quoted string: skip through the closing quote,
        # respecting backslash escapes.
        if c in ("'", '"'):
            quote = c
            j = i + 1
            while j < n and line[j] != quote:
                if line[j] == "\\" and j + 1 < n:
                    j += 2
                else:
                    j += 1
            i = min(j + 1, n)
            continue

        # Comment: ignore everything to end of line.
        if c == "#":
            eol = line.find("\n", i)
            i = n if eol == -1 else eol
            continue

        # Brackets, parens, braces — track depth.
        if c == "(":
            paren_depth += 1
        elif c == ")":
            paren_depth -= 1
        elif c == "[":
            bracket_depth += 1
        elif c == "]":
            bracket_depth -= 1
        elif c == "{":
            brace_depth += 1
        elif c == "}":
            brace_depth -= 1

        # Skip operators that contain `=` but aren't equation operators.
        # The order matters: check the two-character forms before `=`.
        if c == "=" and paren_depth == 0 and bracket_depth == 0 and brace_depth == 0:
            # `==` (equation operator, treat the same as `=`).
            if i + 1 < n and line[i + 1] == "=":
                found.append((i, i + 2))
                i += 2
                continue
            # `=` (equation operator).
            found.append((i, i + 1))
            i += 1
            continue
        # `<=`, `>=`, `!=` — comparison operators, not equation.
        if c in ("<", ">", "!") and i + 1 < n and line[i + 1] == "=":
            i += 2
            continue

        i += 1

    if not found:
        return None
    if len(found) > 1:
        raise ValidationError(
            f"{_classdef_loc(class_name, source_index)}: cannot parse equation "
            f"{line!r}: chained assignment not allowed "
            f"(more than one top-level `=` / `==`); write each equation on "
            f"its own line."
        )
    start, end = found[0]
    lhs_text = line[:start].strip()
    rhs_text = line[end:].strip()
    if not lhs_text or not rhs_text:
        raise ValidationError(
            f"{_classdef_loc(class_name, source_index)}: cannot parse equation "
            f"{line!r}: empty expression on one side of the equation operator."
        )
    return lhs_text, rhs_text


def parse_equations_unified(
    eq_strs: Sequence[str],
    *,
    class_name: str = "",
) -> tuple[
    list[ParsedEquation], list[ParsedConstraint],
    frozenset[str],
]:
    """Parse the equations list into the unified representation.

    Returns ``(equations, constraints, all_optionals)``.

    Per-line classification, comma-expansion, malformed-shape rejection,
    self-reference detection, and mutual-inconsistency detection all
    happen here. Anything malformed or inconsistent surfaces as a
    ValidationError. Sympy is required (used for the algebraic checks);
    if it's not importable, ``_require_sympy`` raises a helpful error.

    ``class_name`` (optional) is the owning Component's class name. When
    set, error messages prefix with ``ClassName.equations[N]:``; when
    empty, the prefix is just ``equations[N]:``.
    """
    from scadwright.component.equations import (
        _extract_optional_markers, _require_sympy,
    )

    _require_sympy()

    equations: list[ParsedEquation] = []
    constraints: list[ParsedConstraint] = []
    all_optionals: set[str] = set()

    for source_index, raw in enumerate(eq_strs):
        cleaned, line_opts = _extract_optional_markers(raw)
        all_optionals |= line_opts
        line_opts_frozen = frozenset(line_opts)

        # Step 1: split on a top-level equation operator. If the line
        # has one, it's an equation; otherwise it's a constraint.
        split = _split_top_level_equals(cleaned, class_name, source_index)

        if split is not None:
            lhs_text, rhs_text = split
            _emit_equation(
                lhs_text, rhs_text, cleaned, line_opts_frozen,
                source_index, class_name, equations,
            )
        else:
            _emit_constraint(
                cleaned, line_opts_frozen, source_index, class_name,
                constraints,
            )

    # Class-def-time validation passes.
    _check_unknown_function_calls(equations, constraints, class_name)
    _check_self_reference(equations, class_name)
    _check_mutual_inconsistency(equations, class_name)

    return (
        equations,
        constraints,
        frozenset(all_optionals),
    )


def _check_unknown_function_calls(
    equations: list[ParsedEquation],
    constraints: list[ParsedConstraint],
    class_name: str = "",
) -> None:
    """Reject any bare-name function call whose callee isn't in the
    curated namespace and isn't a comprehension/cardinality helper.
    Catches typos like ``snh(x)`` (vs ``sinh``) at class-definition time.

    A name that's only a Param won't typically appear as a Call (Params
    hold values, not callables). Names appearing as bare-Name targets of
    equations are also added to the allowlist as a forward-compat
    cushion: a future spec change might let class-typed Params be
    constructed inside equations.
    """
    from scadwright.component.equations import (
        _CURATED_BUILTINS, _CURATED_MATH,
    )

    # Names that appear as bare-Name targets of any equation (either
    # side) act like Param-bound names — exempt them from the call check.
    eq_target_names: set[str] = set()
    for eq in equations:
        if isinstance(eq.lhs, ast.Name):
            eq_target_names.add(eq.lhs.id)
        if isinstance(eq.rhs, ast.Name):
            eq_target_names.add(eq.rhs.id)

    allowed = (
        set(_CURATED_BUILTINS)
        | set(_CURATED_MATH)
        | _PREDICATE_CALL_NAMES
        | eq_target_names
    )

    def _check_node(node: ast.AST, record) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                if sub.func.id not in allowed:
                    loc = _classdef_loc(class_name, record.source_line_index)
                    raise ValidationError(
                        f"{loc}: cannot parse equation {record.raw!r}: "
                        f"unknown function {sub.func.id!r} (not a Param, "
                        f"equation target, or curated math/builtin name)"
                    )

    for eq in equations:
        _check_node(eq.lhs, eq)
        _check_node(eq.rhs, eq)
    for c in constraints:
        _check_node(c.expr, c)


# Predicate-shape calls plus cardinality helpers — all are valid bare-
# name call targets in equations text.
_PREDICATE_CALL_NAMES = frozenset({
    "all", "any", "isinstance",
    "exactly_one", "at_least_one", "at_most_one", "all_or_none",
})


def _parse_expr(
    text: str, raw: str, class_name: str = "", source_index: int = 0,
) -> ast.expr:
    """Parse ``text`` as a Python expression.

    Returns the expression AST. Raises ValidationError naming ``raw``
    (the user's full equation line) on parse failure. The parsed tree
    is uniformly Load-context — both sides of an equation are
    expressions in scadwright's language, never assignment targets.
    """
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValidationError(
            f"{_classdef_loc(class_name, source_index)}: cannot parse "
            f"equation {raw!r}: {exc.msg}"
        ) from exc
    expr = tree.body
    # Reject the walrus operator anywhere in the parsed expression.
    for sub in ast.walk(expr):
        if isinstance(sub, ast.NamedExpr):
            raise ValidationError(
                f"{_classdef_loc(class_name, source_index)}: equation "
                f"{raw!r}: walrus operator `:=` not allowed."
            )
    return expr


def _emit_equation(
    lhs_text: str,
    rhs_text: str,
    raw: str,
    line_opts: frozenset[str],
    source_index: int,
    class_name: str,
    out: list[ParsedEquation],
) -> None:
    """Build a ParsedEquation from the two halves of a ``=``/``==`` line.

    Both halves are parsed as Python expressions. Comma-broadcast on
    either side expands into per-name equations sharing the other side.
    Subscript and Attribute expressions are accepted on either side as
    reads — the resolver never drives them as outputs (it only assigns
    bare-Name unknowns).
    """
    lhs = _parse_expr(lhs_text, raw, class_name, source_index)
    rhs = _parse_expr(rhs_text, raw, class_name, source_index)

    # Comma broadcast on the left side: ``x, y = expr`` means each name
    # gets the same value. The right side is the broadcast value, never a
    # comma-list. ``x, y`` parses as ``Tuple([Name(x), Name(y)])``; only
    # an unparenthesized comma list at the top level of the LHS triggers
    # broadcast (parenthesized tuples in the LHS text would have been
    # parsed the same way structurally, so disambiguating textually isn't
    # straightforward — we treat any LHS Tuple of bare Names as a
    # broadcast, which matches the natural user intent).
    lhs_names = _bare_name_tuple(lhs)
    if lhs_names is not None:
        # Reject literal-tuple/list RHS whose element count matches the
        # comma list — looks enough like Python unpacking to warrant a
        # class-def-time error pointing to the broadcast meaning.
        if (
            isinstance(rhs, (ast.Tuple, ast.List))
            and len(rhs.elts) == len(lhs_names)
        ):
            raise ValidationError(
                f"{_classdef_loc(class_name, source_index)}: equation "
                f"{raw!r}: in equations, comma broadcasts (each name gets "
                f"the same value), it does not unpack. If you want "
                f"different values for each name, write them on separate "
                f"lines."
            )
        for name_node in lhs_names:
            refs = frozenset(_free_names_in(name_node) | _free_names_in(rhs))
            out.append(ParsedEquation(
                raw=raw, lhs=name_node, rhs=rhs,
                referenced_names=refs, line_optionals=line_opts,
                source_line_index=source_index,
            ))
        return

    # Reject `?` markers when the marked name is the unique bare-Name
    # target of this equation. The sigil declares the name optional
    # (Param-with-default-None); an equation pinning it to a value would
    # contradict the explicit None.
    bare_target = None
    if isinstance(lhs, ast.Name):
        bare_target = lhs.id
    elif isinstance(rhs, ast.Name):
        bare_target = rhs.id
    if bare_target is not None and bare_target in line_opts:
        raise ValidationError(
            f"{_classdef_loc(class_name, source_index)}: equation "
            f"{raw!r}: target name cannot be marked optional — "
            f"`?{bare_target}` must be a Param, not the target of an "
            f"equation."
        )

    refs = frozenset(_free_names_in(lhs) | _free_names_in(rhs))
    out.append(ParsedEquation(
        raw=raw, lhs=lhs, rhs=rhs,
        referenced_names=refs, line_optionals=line_opts,
        source_line_index=source_index,
    ))


def _emit_constraint(
    raw: str,
    line_opts: frozenset[str],
    source_index: int,
    class_name: str,
    out: list[ParsedConstraint],
) -> None:
    """Build a ParsedConstraint from a non-equation line.

    The line has no top-level ``=``/``==``, so it must be a comparison,
    a boolean expression, or a call returning bool. Comma-broadcast
    constraints (``x, y > 0``) expand into per-name constraints.
    """
    expr = _parse_expr(raw, raw, class_name, source_index)

    names_op_rhs = _comma_expanded_compare(expr)
    if names_op_rhs is not None:
        names, op, rhs_node = names_op_rhs
        for name_node in names:
            new_compare = ast.Compare(
                left=name_node, ops=[op], comparators=[rhs_node]
            )
            ast.copy_location(new_compare, expr)
            refs = frozenset(_free_names_in(new_compare))
            # Use the expanded form as the raw text so error messages
            # name the specific failing component (e.g., "b < c") rather
            # than the original comma-expanded line ("a, b < c").
            try:
                expanded_raw = ast.unparse(new_compare)
            except Exception:
                expanded_raw = raw
            out.append(ParsedConstraint(
                raw=expanded_raw, expr=new_compare,
                referenced_names=refs, line_optionals=line_opts,
                source_line_index=source_index,
            ))
        return

    if not _is_predicate_shape(expr):
        raise ValidationError(
            f"{_classdef_loc(class_name, source_index)}: equation "
            f"`{raw}`: not a boolean rule. "
            f"An equation uses `=` (or `==`); a rule uses a comparison "
            f"(`<`, `>`, `<=`, `>=`, `in`) or a boolean expression "
            f"(`all(...)`, `any(...)`, `not ...`, etc.)."
        )

    refs = frozenset(_free_names_in(expr))
    out.append(ParsedConstraint(
        raw=raw, expr=expr,
        referenced_names=refs, line_optionals=line_opts,
        source_line_index=source_index,
    ))


def _bare_name_tuple(node: ast.expr) -> list[ast.Name] | None:
    """Return the list of Names if ``node`` is a Tuple of bare Names.

    Used to detect comma-broadcast targets. Returns None for any other
    shape, including a Tuple containing non-Name elements.
    """
    if not isinstance(node, ast.Tuple):
        return None
    if not all(isinstance(e, ast.Name) for e in node.elts):
        return None
    return list(node.elts)


def _is_predicate_shape(expr: ast.AST) -> bool:
    """True if ``expr`` is a boolean expression we accept as a constraint."""
    if isinstance(expr, ast.Compare):
        return True
    if isinstance(expr, ast.BoolOp):
        return True
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
        return True
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name):
        if expr.func.id in _PREDICATE_CALL_NAMES:
            return True
    return False


# =============================================================================
# Value coercion
# =============================================================================


def _coerce_for_param(value: Any, param) -> Any:
    """Coerce ``value`` to ``param``'s declared type if possible.

    Mirrors a subset of ``Param._coerce``: returns the value unchanged
    when there's no Param, no declared type, the value is None, or the
    value is already the right type. Otherwise attempts ``param.type(value)``
    and returns the original on failure (downstream validators will
    catch type mismatches with their own error messages).
    """
    if param is None or param.type is None or value is None:
        return value
    if isinstance(value, param.type):
        return value
    if isinstance(value, bool) and param.type is not bool:
        return value
    try:
        return param.type(value)
    except (TypeError, ValueError):
        return value


# =============================================================================
# Per-Param validator extraction from constraints
# =============================================================================


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


# =============================================================================
# Constraint-failure enrichment
# =============================================================================


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


# =============================================================================
# Class-def-time inconsistency detection
# =============================================================================


def _check_self_reference(
    equations: list[ParsedEquation], class_name: str = "",
) -> None:
    """Reject equations that reduce to a contradiction in isolation.

    Example: ``x = x - 1`` reduces to ``0 = -1``, false.
    Only checked for fully-algebraic equations; non-algebraic ones
    (with attribute access, comprehensions, conditionals, etc.) are
    skipped because sympy can't reason about them at class-def time.
    """
    import sympy as sp

    for eq in equations:
        if not (is_fully_algebraic(eq.lhs) and is_fully_algebraic(eq.rhs)):
            continue
        free_names = _free_names_in(eq.lhs) | _free_names_in(eq.rhs)
        try:
            symbols = {n: sp.Symbol(n) for n in free_names}
            lhs_expr = ast_to_sympy(eq.lhs, symbols)
            rhs_expr = ast_to_sympy(eq.rhs, symbols)
        except Exception:
            continue
        try:
            diff = sp.simplify(lhs_expr - rhs_expr)
        except Exception:
            continue
        if diff.is_number and diff != 0:
            raise ValidationError(
                f"{_classdef_loc(class_name, eq.source_line_index)}: "
                f"equation {eq.raw!r}: self-referential and inconsistent "
                f"(reduces to {sp.sstr(sp.Eq(lhs_expr, rhs_expr))})"
            )


def _check_mutual_inconsistency(
    equations: list[ParsedEquation], class_name: str = "",
) -> None:
    """Reject equation systems with no solution.

    Builds sympy ``Eq`` objects for every fully-algebraic equation and
    runs ``sympy.solve`` on the system. If sympy returns an empty
    solution set AND the equations are at least exactly-determined
    (number of equations >= number of unknowns), the system is
    inconsistent.
    """
    import sympy as sp

    algebraic = [
        eq for eq in equations
        if is_fully_algebraic(eq.lhs) and is_fully_algebraic(eq.rhs)
    ]
    if len(algebraic) < 2:
        return  # need at least two equations to be mutually inconsistent

    symbols: dict[str, Any] = {}
    sympy_eqs = []
    try:
        for eq in algebraic:
            for n in _free_names_in(eq.lhs) | _free_names_in(eq.rhs):
                if n not in symbols:
                    symbols[n] = sp.Symbol(n)
            lhs_expr = ast_to_sympy(eq.lhs, symbols)
            rhs_expr = ast_to_sympy(eq.rhs, symbols)
            sympy_eqs.append(sp.Eq(lhs_expr, rhs_expr))
    except Exception:
        return  # not all algebraic equations could be translated; skip

    try:
        solutions = sp.solve(sympy_eqs, list(symbols.values()), dict=True)
    except (NotImplementedError, Exception):
        return

    if solutions:
        return  # at least one solution exists

    if len(sympy_eqs) >= len(symbols):
        eqs_str = "; ".join(f"`{eq.raw}`" for eq in algebraic)
        raise ValidationError(
            f"{_classdef_loc_multi(class_name, algebraic)}: equations are "
            f"inconsistent: no solution to the system {eqs_str}"
        )


def _comma_expanded_compare(expr: ast.AST):
    """Detect a comma-expanded comparison shape and return its parts.

    Python parses ``"x, y, z > 0"`` as ``Tuple([x, y, Compare(z, Gt, 0)])``
    because of operator-precedence interaction with the comma. Returns
    ``(names, op, rhs)`` if ``expr`` matches that shape (or the rebuilt
    ``Compare(Tuple([x, y, z]), Gt, 0)`` shape), else ``None``.
    """
    # Python's natural parse: Tuple with trailing Compare.
    if (
        isinstance(expr, ast.Tuple)
        and expr.elts
        and all(isinstance(e, ast.Name) for e in expr.elts[:-1])
        and isinstance(expr.elts[-1], ast.Compare)
        and len(expr.elts[-1].ops) == 1
        and isinstance(expr.elts[-1].left, ast.Name)
    ):
        tail = expr.elts[-1]
        names = list(expr.elts[:-1]) + [tail.left]
        return names, tail.ops[0], tail.comparators[0]
    # Pre-rebuilt: Compare with a Tuple LHS.
    if (
        isinstance(expr, ast.Compare)
        and len(expr.ops) == 1
        and isinstance(expr.left, ast.Tuple)
        and all(isinstance(e, ast.Name) for e in expr.left.elts)
    ):
        return list(expr.left.elts), expr.ops[0], expr.comparators[0]
    return None


# =============================================================================
# Iterative resolver
# =============================================================================


_AMBIGUOUS_LIST_LIMIT = 10


class IterativeResolver:
    """Resolve a system of equations and constraints to a complete knowns dict.

    The resolver runs an iterative single-equation pass until no progress
    is made, then attempts a system-solve fallback for any remaining
    algebraic equations. Constraints are evaluated as soon as their
    referenced names are all known.
    """

    def __init__(
        self,
        equations: list[ParsedEquation],
        constraints: list[ParsedConstraint],
        params: dict[str, Param],
        supplied: dict[str, Any],
        component_name: str,
    ):
        from scadwright.component.equations import (
            _CURATED_BUILTINS, _CURATED_MATH,
        )

        self.equations = equations
        self.constraints = constraints
        self.params = params
        self.component_name = component_name

        # knowns: name → value, coerced via each Param's type so the
        # resolver sees the same form Param.__set__ would produce.
        #
        # `None` defaults (the `?` sigil) are added immediately so the
        # optional-handling path can detect the unset state.
        #
        # Non-None defaults are deferred: only applied if the iterative
        # loop stalls. This matches legacy behavior — a default value
        # yields to a solver-found value when the equations + user
        # inputs are sufficient on their own.
        self.knowns: dict[str, Any] = {
            name: _coerce_for_param(value, params.get(name))
            for name, value in supplied.items()
        }
        self._pending_defaults: dict[str, Any] = {}
        for name, param in params.items():
            if name in self.knowns:
                continue
            if not param.has_default():
                continue
            if param.default is None:
                self.knowns[name] = None
            else:
                self._pending_defaults[name] = _coerce_for_param(
                    param.default, param,
                )
        self._supplied_names = set(supplied.keys())

        # Curated namespace for evaluation (does not include knowns).
        self._curated_ns = {**_CURATED_BUILTINS, **_CURATED_MATH}

        # Pending indices into self.equations / self.constraints. Lists
        # preserve declaration order so error messages report the first
        # failing equation/constraint, matching how the legacy pipeline
        # surfaced errors.
        self._pending_eqs: list[int] = list(range(len(equations)))
        self._pending_constraints: list[int] = list(range(len(constraints)))

    # --- error-location helpers ---

    def _loc(self, eq_or_constraint) -> str:
        """Prefix string pointing at the source line in the user's
        ``equations`` list. Used by every per-equation/per-constraint
        error message."""
        return (
            f"{self.component_name}.equations"
            f"[{eq_or_constraint.source_line_index}]"
        )

    def _loc_multi(self, items) -> str:
        """Prefix for errors that span multiple equations (system-solve
        aggregates). Lists each unique source-line index."""
        unique = sorted({i.source_line_index for i in items})
        return f"{self.component_name}.equations[{', '.join(str(i) for i in unique)}]"

    # --- public ---

    def resolve(self) -> dict[str, Any]:
        """Run the iterative loop. Returns the final knowns dict.

        Raises ValidationError on insufficient/inconsistent/ambiguous.
        """
        # Initial constraint check on anything fully evaluable.
        self._check_pending_constraints()

        while self._pending_eqs:
            progress = False
            for i in list(self._pending_eqs):
                outcome = self._try_resolve_equation(self.equations[i])
                if outcome in ("resolved", "skipped", "consistent"):
                    self._pending_eqs.remove(i)
                if outcome == "resolved":
                    progress = True
            # New knowns may unlock constraints.
            self._check_pending_constraints()
            if progress:
                continue
            # No progress this pass — apply deferred Param defaults if
            # any, and re-iterate. Defaults yield to solver-found values
            # because they're only added when the loop is stuck.
            if self._pending_defaults:
                for name, value in self._pending_defaults.items():
                    if name not in self.knowns:
                        self.knowns[name] = value
                self._pending_defaults = {}
                continue
            # System-solve fallback for coupled equations.
            if not self._pending_eqs:
                break
            sys_progress = self._system_solve()
            if not sys_progress:
                self._raise_insufficient()

        # Final check on anything that's still pending (None-skipped or otherwise).
        self._check_pending_constraints()
        return self.knowns

    # --- per-equation resolve ---

    def _try_resolve_equation(self, eq: ParsedEquation) -> str:
        """Returns ``'resolved'``, ``'skipped'``, ``'consistent'``, or
        ``'postponed'``."""
        # OQ 6: explicit-None-supplied vs equation-pinning detection.
        # If one side is a bare Name that the user explicitly supplied as
        # None, and the other side evaluates (with all other knowns) to a
        # concrete non-None value, the equation contradicts the user's
        # explicit None. Surface that as a specific error.
        self._check_supplied_none_conflict(eq)

        # Try to substitute knowns into both sides.
        sub_lhs = substitute_knowns(eq.lhs, self.knowns, self._curated_ns)
        sub_rhs = substitute_knowns(eq.rhs, self.knowns, self._curated_ns)

        full_known_names = set(self.knowns) | set(self._curated_ns)
        lhs_unknowns = find_unknowns(sub_lhs, full_known_names)
        rhs_unknowns = find_unknowns(sub_rhs, full_known_names)
        all_unknowns = lhs_unknowns | rhs_unknowns

        # Optional handling: if any referenced name has value None and the
        # equation didn't manage to evaluate cleanly, decide skip vs.
        # inconsistent.
        none_refs = {
            n for n in eq.referenced_names
            if n in self.knowns and self.knowns[n] is None
        }
        if none_refs:
            return self._handle_none_referenced(
                eq, sub_lhs, sub_rhs, all_unknowns, none_refs
            )

        if not all_unknowns:
            return self._consistency_check(eq, sub_lhs, sub_rhs)

        # Forward-eval first: when one side is a bare unknown Name and
        # the other has no remaining unknowns, evaluate the other side
        # in Python and assign. Runtime errors (ZeroDivisionError,
        # TypeError, etc.) surface as derivation failures rather than
        # being swallowed.
        if (
            isinstance(sub_lhs, ast.Name)
            and sub_lhs.id in all_unknowns
            and not rhs_unknowns
        ):
            return self._forward_assign(eq, sub_lhs.id, sub_rhs)
        if (
            isinstance(sub_rhs, ast.Name)
            and sub_rhs.id in all_unknowns
            and not lhs_unknowns
        ):
            return self._forward_assign(eq, sub_rhs.id, sub_lhs)

        if is_fully_algebraic(sub_lhs) and is_fully_algebraic(sub_rhs):
            return self._sympy_solve_one(eq, sub_lhs, sub_rhs, all_unknowns)

        return "postponed"

    def _check_supplied_none_conflict(self, eq: ParsedEquation) -> None:
        """Raise if the equation pins a bare-Name target to a non-None
        value but the user explicitly supplied that name as None.
        """
        for side, other in ((eq.lhs, eq.rhs), (eq.rhs, eq.lhs)):
            if not isinstance(side, ast.Name):
                continue
            name = side.id
            if name not in self._supplied_names:
                continue
            if self.knowns.get(name) is not None:
                continue
            knowns_minus = {
                k: v for k, v in self.knowns.items() if k != name
            }
            sub_other = substitute_knowns(other, knowns_minus, self._curated_ns)
            full_names = set(knowns_minus) | set(self._curated_ns)
            if find_unknowns(sub_other, full_names):
                continue
            try:
                expr_node = ast.Expression(body=sub_other)
                ast.fix_missing_locations(expr_node)
                code = compile(expr_node, "<resolver>", "eval")
                full_ns = {
                    **self._curated_ns, **knowns_minus, "__builtins__": {},
                }
                val = eval(code, full_ns)
            except Exception:
                continue
            if val is not None:
                raise ValidationError(
                    f"{self._loc(eq)}: equation `{eq.raw}` would "
                    f"assign {name}={val!r} but {name} was explicitly "
                    f"supplied as None"
                )

    def _handle_none_referenced(
        self, eq, sub_lhs, sub_rhs, all_unknowns, none_refs,
    ) -> str:
        """An equation references one or more None-valued names. Try to
        evaluate; if it errors on None, skip; if it pins a None-supplied
        name to a value, raise inconsistent (per OQ 6).
        """
        if not all_unknowns:
            # Both sides reduced to constants — consistency-check.
            return self._consistency_check(eq, sub_lhs, sub_rhs)

        # Try a forward-eval if exactly one side is a bare-name unknown.
        # If the equation pins a None-supplied name, that's inconsistent.
        target_node = None
        value_node = None
        if (
            isinstance(sub_lhs, ast.Name) and sub_lhs.id in all_unknowns
        ):
            target_node, value_node = sub_lhs, sub_rhs
        elif (
            isinstance(sub_rhs, ast.Name) and sub_rhs.id in all_unknowns
        ):
            target_node, value_node = sub_rhs, sub_lhs

        if target_node is not None:
            target_name = target_node.id
            if target_name in none_refs and target_name in self._supplied_names:
                # User explicitly supplied None; equation tries to assign
                # a different value → inconsistent.
                try:
                    val = self._eval_node(value_node)
                except Exception:
                    return "skipped"
                raise ValidationError(
                    f"{self._loc(eq)}: equation `{eq.raw}` would "
                    f"assign {target_name}={val!r} but {target_name} was "
                    f"explicitly supplied as None"
                )
            # Otherwise: treat as a regular forward-eval.
            try:
                val = self._eval_node(value_node)
            except (TypeError, ValueError):
                return "skipped"
            self._assign_new(target_name, val, eq)
            return "resolved"

        # Couldn't pin a target. Try evaluating a constraint-style check.
        try:
            self._eval_node(sub_lhs)
            self._eval_node(sub_rhs)
        except (TypeError, ValueError):
            return "skipped"
        return "postponed"

    def _consistency_check(self, eq, sub_lhs, sub_rhs) -> str:
        try:
            lv = self._eval_node(sub_lhs)
            rv = self._eval_node(sub_rhs)
        except Exception:
            return "postponed"
        if self._values_equal(lv, rv):
            return "consistent"
        raise ValidationError(
            f"{self._loc(eq)}: equation violated: `{eq.raw}` "
            f"(lhs={lv!r}, rhs={rv!r})"
        )

    def _sympy_solve_one(self, eq, sub_lhs, sub_rhs, unknowns) -> str:
        if len(unknowns) > 1:
            return "postponed"

        import sympy as sp

        target = next(iter(unknowns))
        symbols = {n: sp.Symbol(n) for n in unknowns}
        try:
            lhs_expr = self._ast_to_sympy(sub_lhs, symbols)
            rhs_expr = self._ast_to_sympy(sub_rhs, symbols)
        except Exception:
            return "postponed"

        try:
            solutions = sp.solve(sp.Eq(lhs_expr, rhs_expr), symbols[target])
        except (NotImplementedError, Exception):
            return "postponed"
        if not solutions:
            raise ValidationError(
                f"{self._loc(eq)}: equation `{eq.raw}` has no solution"
            )

        numeric = self._extract_numeric(solutions)
        if not numeric:
            return "postponed"

        if len(numeric) == 1:
            # Single solution: assign directly. Per-Param validator
            # failures bubble up with their original message (e.g.,
            # "must be positive, got -5").
            self._assign_new(target, numeric[0], eq)
            return "resolved"

        # Multiple solutions: filter by per-Param validators first
        # (cheap), then by feasibility against the full constraint set
        # (expensive but necessary when the disambiguating bound lives
        # in a cross-equation constraint, e.g. ``angle < 180`` ruling
        # out the second branch of an asin solve).
        valid = self._filter_by_validators(target, numeric)
        if len(valid) > 1:
            valid = self._filter_by_feasibility(target, valid)
        if not valid:
            raise ValidationError(
                f"{self._loc(eq)}: equation `{eq.raw}`: no candidate "
                f"for {target} satisfies validators or constraints "
                f"(candidates: {numeric!r})"
            )
        if len(valid) > 1:
            shown = valid[:_AMBIGUOUS_LIST_LIMIT]
            raise ValidationError(
                f"{self._loc(eq)}: equation `{eq.raw}` has multiple "
                f"solutions for {target}: {shown!r}"
                + (" (truncated)" if len(valid) > _AMBIGUOUS_LIST_LIMIT else "")
            )

        self._assign_new(target, valid[0], eq)
        return "resolved"

    def _forward_assign(self, eq, target_name, value_node) -> str:
        try:
            value = self._eval_node(value_node)
        except Exception as exc:
            raise ValidationError(
                f"{self._loc(eq)}: equation `{eq.raw}` failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        self._assign_new(target_name, value, eq)
        return "resolved"

    # --- system solve ---

    def _system_solve(self) -> bool:
        """Hand all pending algebraic equations to sympy.solve as a
        system. Returns True if at least one new value was resolved.
        """
        import sympy as sp

        algebraic: list[tuple[int, ast.AST, ast.AST]] = []
        for i in self._pending_eqs:
            eq = self.equations[i]
            sub_lhs = substitute_knowns(eq.lhs, self.knowns, self._curated_ns)
            sub_rhs = substitute_knowns(eq.rhs, self.knowns, self._curated_ns)
            if is_fully_algebraic(sub_lhs) and is_fully_algebraic(sub_rhs):
                algebraic.append((i, sub_lhs, sub_rhs))

        if not algebraic:
            return False

        full_known_names = set(self.knowns) | set(self._curated_ns)
        unknowns: set[str] = set()
        for _, l, r in algebraic:
            unknowns |= find_unknowns(l, full_known_names)
            unknowns |= find_unknowns(r, full_known_names)
        if not unknowns:
            return False

        symbols = {n: sp.Symbol(n) for n in unknowns}
        sympy_eqs = []
        for _, l, r in algebraic:
            try:
                le = self._ast_to_sympy(l, symbols)
                re = self._ast_to_sympy(r, symbols)
                sympy_eqs.append(sp.Eq(le, re))
            except Exception:
                continue
        if not sympy_eqs:
            return False

        try:
            solutions = sp.solve(
                sympy_eqs, list(symbols.values()), dict=True,
            )
        except (NotImplementedError, Exception):
            return False

        algebraic_eqs = [self.equations[i] for i, _, _ in algebraic]

        if not solutions:
            raise ValidationError(
                f"{self._loc_multi(algebraic_eqs)}: equations are inconsistent "
                f"(no solution to the system)"
            )

        numeric_solutions = []
        for sol in solutions:
            try:
                cand = {sym.name: float(val.evalf()) for sym, val in sol.items()}
                numeric_solutions.append(cand)
            except (TypeError, ValueError, AttributeError):
                continue
        if not numeric_solutions:
            return False

        valid = []
        for cand in numeric_solutions:
            if self._candidate_passes_validators(cand):
                valid.append(cand)
        # When several candidates pass per-Param validators, narrow by
        # full-system feasibility — propagate each candidate forward
        # through the equation system and reject any that violate a
        # cross-equation constraint.
        if len(valid) > 1:
            valid = self._filter_systems_by_feasibility(valid)
        if not valid:
            raise ValidationError(
                f"{self._loc_multi(algebraic_eqs)}: equations have no "
                f"solution satisfying validators or constraints "
                f"(candidates: {numeric_solutions[:_AMBIGUOUS_LIST_LIMIT]!r})"
            )
        if len(valid) > 1:
            shown = valid[:_AMBIGUOUS_LIST_LIMIT]
            raise ValidationError(
                f"{self._loc_multi(algebraic_eqs)}: equations have multiple "
                f"solutions: {shown!r}"
                + (" (truncated)" if len(valid) > _AMBIGUOUS_LIST_LIMIT else "")
            )

        for name, value in valid[0].items():
            self._assign_new(name, value, raw_for_msg="system-solve")
        return True

    # --- assignment & validator helpers ---

    def _assign_new(self, name: str, value: Any, eq=None, raw_for_msg=None):
        # Consistency check if name was already known with a different value.
        if name in self.knowns and self.knowns[name] is not None:
            if not self._values_equal(self.knowns[name], value):
                raw = (
                    eq.raw if eq is not None
                    else (raw_for_msg or "system-solve")
                )
                prefix = (
                    self._loc(eq) if eq is not None else self.component_name
                )
                raise ValidationError(
                    f"{prefix}: equation `{raw}` would "
                    f"assign {name}={value!r} but {name} is already "
                    f"{self.knowns[name]!r}"
                )
            return  # no change

        # OQ 6: explicit None supplied + equation pinning value → inconsistent.
        if (
            name in self._supplied_names
            and self.knowns.get(name) is None
            and value is not None
        ):
            raw = (
                eq.raw if eq is not None
                else (raw_for_msg or "system-solve")
            )
            prefix = (
                self._loc(eq) if eq is not None else self.component_name
            )
            raise ValidationError(
                f"{prefix}: equation `{raw}` would assign "
                f"{name}={value!r} but {name} was explicitly supplied as None"
            )

        self.knowns[name] = value
        # Run validators on newly assigned value.
        param = self.params.get(name)
        if param is not None and value is not None:
            for validator in param.validators:
                try:
                    validator(value)
                except ValidationError as exc:
                    raise ValidationError(
                        f"{self.component_name}.{name}: {exc}"
                    ) from exc

    def _filter_by_validators(self, name: str, candidates: list[float]) -> list[float]:
        param = self.params.get(name)
        if param is None or not param.validators:
            return list(candidates)
        out = []
        for v in candidates:
            ok = True
            for validator in param.validators:
                try:
                    validator(v)
                except ValidationError:
                    ok = False
                    break
            if ok:
                out.append(v)
        return out

    def _candidate_passes_validators(self, cand: dict[str, float]) -> bool:
        for name, value in cand.items():
            param = self.params.get(name)
            if param is None:
                continue
            for validator in param.validators:
                try:
                    validator(value)
                except ValidationError:
                    return False
        return True

    def _filter_by_feasibility(
        self, target: str, candidates: list[float],
    ) -> list[float]:
        """Drop candidates whose tentative assignment violates a constraint.

        For each candidate value of ``target``, simulate forward through
        the equation system using forward-evaluation only (no sympy) and
        check every constraint whose names become known. A candidate
        whose downstream values would violate any constraint is dropped.

        Used to disambiguate sympy multi-solution returns when the
        deciding bound lives in a cross-equation constraint
        (e.g. ``angle < 180`` ruling out one branch of an asin).
        """
        survivors: list[float] = []
        for cand in candidates:
            tentative = dict(self.knowns)
            tentative[target] = cand

            # Forward-eval pass: keep substituting+evaluating until no
            # new values resolve. Bounded by the number of unresolved
            # equations.
            progress = True
            while progress:
                progress = False
                for eq in self.equations:
                    bare = None
                    if (
                        isinstance(eq.lhs, ast.Name)
                        and eq.lhs.id not in tentative
                    ):
                        bare = (eq.lhs.id, eq.rhs)
                    elif (
                        isinstance(eq.rhs, ast.Name)
                        and eq.rhs.id not in tentative
                    ):
                        bare = (eq.rhs.id, eq.lhs)
                    if bare is None:
                        continue
                    name, expr = bare
                    sub = substitute_knowns(expr, tentative, self._curated_ns)
                    full_known = set(tentative) | set(self._curated_ns)
                    if find_unknowns(sub, full_known):
                        continue
                    try:
                        val = self._eval_substituted(sub, tentative)
                    except Exception:
                        continue
                    tentative[name] = val
                    progress = True

            # Check every constraint whose names are known in the
            # tentative world. Any failure rules out this candidate.
            full_known = set(tentative) | set(self._curated_ns)
            feasible = True
            for c in self.constraints:
                if find_unknowns(c.expr, full_known):
                    continue
                try:
                    sub = substitute_knowns(c.expr, tentative, self._curated_ns)
                    val = self._eval_substituted(sub, tentative)
                except Exception:
                    continue
                if not val:
                    feasible = False
                    break
            if feasible:
                survivors.append(cand)
        return survivors

    def _filter_systems_by_feasibility(
        self, candidates: list[dict[str, float]],
    ) -> list[dict[str, float]]:
        """Drop system-solve candidate dicts whose values violate any
        cross-equation constraint.

        Each candidate is a ``{name: value}`` dict that satisfies the
        algebraic system. Apply the candidate to a tentative knowns
        copy, propagate forward through any equations that resolve, and
        reject the candidate if any constraint fails.
        """
        survivors: list[dict[str, float]] = []
        for cand in candidates:
            tentative = dict(self.knowns)
            tentative.update(cand)
            progress = True
            while progress:
                progress = False
                for eq in self.equations:
                    bare = None
                    if (
                        isinstance(eq.lhs, ast.Name)
                        and eq.lhs.id not in tentative
                    ):
                        bare = (eq.lhs.id, eq.rhs)
                    elif (
                        isinstance(eq.rhs, ast.Name)
                        and eq.rhs.id not in tentative
                    ):
                        bare = (eq.rhs.id, eq.lhs)
                    if bare is None:
                        continue
                    name, expr = bare
                    sub = substitute_knowns(expr, tentative, self._curated_ns)
                    full_known = set(tentative) | set(self._curated_ns)
                    if find_unknowns(sub, full_known):
                        continue
                    try:
                        val = self._eval_substituted(sub, tentative)
                    except Exception:
                        continue
                    tentative[name] = val
                    progress = True

            full_known = set(tentative) | set(self._curated_ns)
            feasible = True
            for c in self.constraints:
                if find_unknowns(c.expr, full_known):
                    continue
                try:
                    sub = substitute_knowns(c.expr, tentative, self._curated_ns)
                    val = self._eval_substituted(sub, tentative)
                except Exception:
                    continue
                if not val:
                    feasible = False
                    break
            if feasible:
                survivors.append(cand)
        return survivors

    def _eval_substituted(self, sub_node: ast.AST, tentative: dict) -> Any:
        """Compile and eval an AST node in a curated+tentative namespace."""
        expr_node = ast.Expression(body=sub_node)
        ast.fix_missing_locations(expr_node)
        code = compile(expr_node, "<feasibility>", "eval")
        ns = {**self._curated_ns, **tentative, "__builtins__": {}}
        return eval(code, ns)

    # --- constraint evaluation ---

    def _check_pending_constraints(self) -> bool:
        progress = False
        full_ns = {**self._curated_ns, **self.knowns, "__builtins__": {}}
        full_known_names = set(self.knowns) | set(self._curated_ns)
        for i in list(self._pending_constraints):
            c = self.constraints[i]
            unknowns = find_unknowns(c.expr, full_known_names)
            if unknowns:
                continue  # not yet evaluable
            try:
                expr_node = ast.Expression(body=c.expr)
                ast.fix_missing_locations(expr_node)
                code = compile(expr_node, "<constraint>", "eval")
                result = eval(code, full_ns)
            except (TypeError, ValueError):
                # None propagation → skip silently.
                self._pending_constraints.remove(i)
                progress = True
                continue
            except Exception as exc:
                raise ValidationError(
                    f"{self._loc(c)}: constraint `{c.raw}` "
                    f"failed to evaluate: {exc}"
                ) from exc
            self._pending_constraints.remove(i)
            progress = True
            if not result:
                # If the constraint is a name-vs-numeric form, the same
                # check is attached as a per-Param validator. Run it and
                # let its specific error message bubble up
                # ("must be positive, got -1") instead of the generic
                # constraint-violated message.
                pp_result = extract_per_param_validator(c)
                if pp_result is not None:
                    name, validator = pp_result
                    value = self.knowns.get(name)
                    if value is not None:
                        try:
                            validator(value)
                        except ValidationError as exc:
                            raise ValidationError(
                                f"{self.component_name}.{name}: {exc}"
                            ) from exc
                detail = _enrich_constraint_failure(c.expr, full_ns)
                msg = f"{self._loc(c)}: constraint violated: `{c.raw}`"
                if detail:
                    msg += f": {detail}"
                raise ValidationError(msg)
        return progress

    # --- error messages ---

    def _raise_insufficient(self):
        full_known_names = set(self.knowns) | set(self._curated_ns)
        unresolved: set[str] = set()
        pending_eqs = []
        for i in self._pending_eqs:
            eq = self.equations[i]
            pending_eqs.append(eq)
            sub_lhs = substitute_knowns(eq.lhs, self.knowns, self._curated_ns)
            sub_rhs = substitute_knowns(eq.rhs, self.knowns, self._curated_ns)
            unresolved |= find_unknowns(sub_lhs, full_known_names)
            unresolved |= find_unknowns(sub_rhs, full_known_names)
        given = sorted(
            n for n in self._supplied_names if self.knowns.get(n) is not None
        )
        # Enumerate sufficient input combinations to help the caller.
        subsets = _sufficient_subsets(pending_eqs, set(self.knowns))
        if subsets:
            combos = ", ".join(
                "{" + ", ".join(sorted(s)) + "}" for s in subsets[:8]
            )
        else:
            combos = "{" + ", ".join(sorted(unresolved)) + "}"
        raise ValidationError(
            f"{self.component_name}: cannot solve for equation variables: "
            f"given {{{', '.join(given) or 'none'}}}, "
            f"need one of: {combos}"
        )

    # --- AST → sympy ---

    def _ast_to_sympy(self, node: ast.AST, symbols: dict[str, Any]):
        """Convert a fully-algebraic AST to a sympy expression, sympifying
        any Names that resolve to concrete values in ``self.knowns``.
        """
        return ast_to_sympy(node, symbols, knowns=self.knowns)

    # --- helpers ---

    def _eval_node(self, node: ast.AST) -> Any:
        full_ns = {**self._curated_ns, **self.knowns, "__builtins__": {}}
        expr = ast.Expression(body=node)
        ast.fix_missing_locations(expr)
        code = compile(expr, "<resolver>", "eval")
        return eval(code, full_ns)

    def _values_equal(self, a: Any, b: Any) -> bool:
        """Tolerance-aware equality for consistency checks.

        Relative tolerance of 1e-6 (sub-micron in mm-scale CAD) with an
        absolute floor of 1e-9 for near-zero values. Loose enough to
        accept hand-typed values against full-precision sympy results
        (`1.41421356` vs sympy's `1.4142135623730951` for sqrt(2)),
        tight enough to reject any genuinely different values.
        """
        if a is None or b is None:
            return a is b
        try:
            af = float(a)
            bf = float(b)
        except (TypeError, ValueError):
            return a == b
        magnitude = max(abs(af), abs(bf))
        tolerance = max(1e-6 * magnitude, 1e-9)
        return abs(af - bf) <= tolerance

    def _extract_numeric(self, solutions) -> list[float]:
        out: list[float] = []
        for sol in solutions:
            try:
                out.append(float(sol.evalf()))
            except (TypeError, ValueError, AttributeError):
                # Symbolic / interval / conditional → not numeric.
                continue
        return out
