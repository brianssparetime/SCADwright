"""Class-definition-time validation passes.

Each ``_check_*`` function inspects the parsed equations/constraints and
raises ``ValidationError`` when something would only fail later in a
confusing way. The point is to surface user mistakes at class-define
time, with a message naming the offending line, rather than at
construction time with a deeper traceback.
"""

from __future__ import annotations

import ast

from scadwright.component.equations import _NUMERIC_FUNCTION_NAMES
from scadwright.component.resolver.overrides import _classify_override_targets
from scadwright.component.resolver.sympy_bridge import ast_to_sympy
from scadwright.component.resolver.types import (
    ParsedConstraint,
    ParsedEquation,
    _classdef_loc,
    _classdef_loc_multi,
    equation_bare_targets,
)
from scadwright.component.resolver_ast import is_fully_algebraic
from scadwright.component.resolver_ast import _free_names as _free_names_in
from scadwright.errors import ValidationError


_ARITHMETIC_BINOPS = (
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
    ast.Mod, ast.Pow,
)


def _check_bool_in_arithmetic(
    typed_names: dict[str, str],
    equations: list[ParsedEquation],
    constraints: list[ParsedConstraint],
    class_name: str = "",
) -> None:
    """Reject `:bool`-tagged names that participate in arithmetic.

    Python silently treats `True` as `1` in arithmetic, which masks
    bugs like ``x = direction * 2``. A bool-tagged name may appear in
    truthy contexts (``if direction``, ``not direction``, comparisons)
    and as an equation target/value; arithmetic operands and numeric-
    yielding calls reject it at class-define time.
    """
    bool_names = {n for n, t in typed_names.items() if t == "bool"}
    if not bool_names:
        return

    def _walk(node: ast.AST, raw: str, loc: str) -> None:
        # Arithmetic operand check: a Name in bool_names appearing as
        # the left or right of an arithmetic BinOp is a category error.
        if isinstance(node, ast.BinOp) and isinstance(node.op, _ARITHMETIC_BINOPS):
            for side in (node.left, node.right):
                if isinstance(side, ast.Name) and side.id in bool_names:
                    raise ValidationError(
                        f"{loc}: bool-tagged name `{side.id}` used as an "
                        f"arithmetic operand in `{raw}`; bools can be "
                        f"tested in conditions but not used in arithmetic."
                    )
        # Numeric-yielding call: a Name in bool_names passed to sin/sqrt
        # /min/etc. is similarly a category error.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _NUMERIC_FUNCTION_NAMES
        ):
            for arg in node.args:
                if isinstance(arg, ast.Name) and arg.id in bool_names:
                    raise ValidationError(
                        f"{loc}: bool-tagged name `{arg.id}` passed to "
                        f"numeric-yielding call `{node.func.id}` in "
                        f"`{raw}`; bools can be tested in conditions but "
                        f"not used as numeric arguments."
                    )
        for child in ast.iter_child_nodes(node):
            _walk(child, raw, loc)

    for eq in equations:
        loc = _classdef_loc(class_name, eq.source_line_index)
        _walk(eq.lhs, eq.raw, loc)
        _walk(eq.rhs, eq.raw, loc)
    for c in constraints:
        loc = _classdef_loc(class_name, c.source_line_index)
        _walk(c.expr, c.raw, loc)


def _check_override_rhs_evaluable(
    equations: list[ParsedEquation],
    optional_names: frozenset[str],
    class_name: str = "",
) -> None:
    """Reject override-pattern equations whose RHS would throw when
    the LHS is None.

    Uses :func:`_override_rhs_dry_run` to discriminate. ``"unsafe"``
    classifications raise immediately; ``"override"`` and ``"defer"``
    are accepted (the latter falls through to the iterative loop or
    to the non-float-target check, depending on the typing).
    """
    classifications = _classify_override_targets(equations, optional_names)
    for i, (target_name, kind) in classifications.items():
        if kind != "unsafe":
            continue
        eq = equations[i]
        raise ValidationError(
            f"{_classdef_loc(class_name, eq.source_line_index)}: "
            f"override pattern `{eq.raw}` cannot be evaluated when "
            f"`{target_name}` is None — the RHS raises (TypeError or "
            f"ValueError) on that binding. Use a shape that handles "
            f"None gracefully: `{target_name} or default`, "
            f"`default if {target_name} is None else {target_name}`, "
            f"`{target_name} if {target_name} is not None else default`, "
            f"or any other expression that yields a value when "
            f"`{target_name}` is None."
        )


def _check_non_float_solver_target(
    typed_names: dict[str, str],
    equations: list[ParsedEquation],
    optional_names: frozenset[str],
    class_name: str = "",
) -> None:
    """Reject non-float-typed names appearing as bare-Name targets of
    equations the resolver would solve.

    The resolver works over floats; it cannot derive int / bool / str
    / tuple / list / dict values from algebraic equations. A non-float-
    typed name as a bare-Name target on either side of an equation is
    a class-define-time error, except when the equation is an
    optional-default override pattern (the equation's RHS evaluates
    to a non-None value when the target is None — see
    :func:`_override_rhs_dry_run`).
    """
    non_float_typed = {
        n for n, t in typed_names.items()
        if t in ("int", "bool", "str", "tuple", "list", "dict")
    }
    if not non_float_typed:
        return

    classifications = _classify_override_targets(equations, optional_names)

    for i, eq in enumerate(equations):
        for name, other in equation_bare_targets(eq):
            if name not in non_float_typed:
                continue
            # Override path: dry-run says the RHS yields a value with
            # target=None. Allowed regardless of type.
            if classifications.get(i, ("", ""))[1] == "override":
                continue
            raise ValidationError(
                f"{_classdef_loc(class_name, eq.source_line_index)}: "
                f"name `{name}` is tagged `:{typed_names[name]}` and "
                f"cannot be derived from an equation. Non-float-typed "
                f"names must be supplied by the caller or filled by an "
                f"optional-default pattern whose RHS yields a value "
                f"when `{name}` is None (e.g., `?{name}:"
                f"{typed_names[name]} = ?{name} or default`). "
                f"Offending equation: `{eq.raw}`."
            )


def _check_eq_placement(
    equations: list[ParsedEquation],
    constraints: list[ParsedConstraint],
    class_name: str = "",
) -> None:
    """Reject ``==`` outside an ``if`` condition.

    `=` is the equation operator; `==` is a Python comparison whose
    only legitimate use in equations is inside the ``test`` of a
    conditional expression (``a if cond == 1 else b``). A bare
    ``count == 1`` line outside an ``if`` is almost certainly the
    user reaching for the equation operator, so we surface a clear
    error rather than silently letting it be a constraint.
    """

    def _walk(node: ast.AST, in_iftest: bool, raw: str, loc: str) -> None:
        if isinstance(node, ast.Compare):
            for op in node.ops:
                if isinstance(op, ast.Eq) and not in_iftest:
                    raise ValidationError(
                        f"{loc}: cannot use `==` as a top-level "
                        f"comparison in `{raw}`; use `=` for an "
                        f"equation, `in (...)` for membership, or "
                        f"wrap in `if` to use as a comparison inside "
                        f"a conditional expression."
                    )
            # Children of a Compare never become an IfExp.test on their
            # own, so propagate the flag unchanged.
            for child in ast.iter_child_nodes(node):
                _walk(child, in_iftest, raw, loc)
            return
        if isinstance(node, ast.IfExp):
            _walk(node.test, True, raw, loc)
            _walk(node.body, in_iftest, raw, loc)
            _walk(node.orelse, in_iftest, raw, loc)
            return
        # Comprehension generators carry `if` filter clauses that are
        # also Python-level `if` conditions — `==` inside them is fine.
        if isinstance(node, (
            ast.GeneratorExp, ast.ListComp, ast.SetComp, ast.DictComp,
        )):
            # Element / key / value: not in an `if` test.
            if isinstance(node, ast.DictComp):
                _walk(node.key, in_iftest, raw, loc)
                _walk(node.value, in_iftest, raw, loc)
            else:
                _walk(node.elt, in_iftest, raw, loc)
            for gen in node.generators:
                _walk(gen.iter, in_iftest, raw, loc)
                _walk(gen.target, in_iftest, raw, loc)
                # Each `if` clause is an `if`-condition.
                for ifclause in gen.ifs:
                    _walk(ifclause, True, raw, loc)
            return
        for child in ast.iter_child_nodes(node):
            _walk(child, in_iftest, raw, loc)

    for eq in equations:
        loc = _classdef_loc(class_name, eq.source_line_index)
        _walk(eq.lhs, False, eq.raw, loc)
        _walk(eq.rhs, False, eq.raw, loc)
    for c in constraints:
        loc = _classdef_loc(class_name, c.source_line_index)
        _walk(c.expr, False, c.raw, loc)


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
    from scadwright.component.resolver.types import _PREDICATE_CALL_NAMES

    # Names that appear as bare-Name targets of any equation (either
    # side) act like Param-bound names — exempt them from the call check.
    eq_target_names: set[str] = {
        name
        for eq in equations
        for name, _ in equation_bare_targets(eq)
    }

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

    symbols: dict[str, "object"] = {}
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
