"""Parse the user's ``equations`` list into the unified representation.

Per-line classification (equation vs constraint), comma-broadcast
expansion, malformed-shape rejection, and the top-level orchestration
of class-define-time validation passes all live here.
"""

from __future__ import annotations

import ast
from typing import Sequence

from scadwright.component.resolver.types import (
    ParsedAdjustment,
    ParsedConstraint,
    ParsedEquation,
    _PREDICATE_CALL_NAMES,
    _classdef_loc,
)
from scadwright.component.resolver_ast import _free_names as _free_names_in
from scadwright.errors import ValidationError


# Adjustment operators recognized inside ``equations`` blocks. Each
# pairs a 2-character source token with a one-line summary of what the
# resolver does at apply time. The set is closed: ``^=``, ``%=``, etc.
# are NOT supported in this feature (per spec).
_ADJUSTMENT_OPS: frozenset[str] = frozenset({"+=", "-=", "*=", "/="})


# Synthetic Name bound by the resolver during deferred-constraint
# evaluation. ``adjusted(x)`` calls are AST-rewritten to
# ``Subscript(Name("__adjusted__"), Constant("x"))``; the resolver
# binds ``__adjusted__`` to the post-adjust ``knowns`` dict so the
# subscript evaluates to the post-adjust value of ``x`` while bare
# names continue to resolve from the pre-adjust namespace.
_ADJUSTED_NS = "__adjusted__"

# User-facing name for the rule-context marker that wraps a name to
# read its post-adjust value. Centralized so renames stay consistent
# and the validator/rewriter/checker all reference the same string.
_ADJUSTED_FN_NAME = "adjusted"


def _peel_trailing_comment(line: str) -> tuple[str, str | None]:
    """Strip a trailing ``# ...`` comment and return ``(line, comment)``.

    The comment text returned has its leading ``#`` and surrounding
    whitespace stripped; ``None`` is returned when there is no trailing
    comment. Quote-aware so a ``#`` inside ``"..."``/``'...'`` doesn't
    end the line.

    Used by the adjustment path: a logical line like
    ``cam_barrel_od += 0.3   # printer overshoot`` arrives here and is
    split into the parseable left-hand side and the captured comment.
    Equation/constraint paths still leave the comment alone — the
    classification scanner already ignores comments correctly.
    """
    n = len(line)
    i = 0
    while i < n:
        c = line[i]
        if c in ("'", '"') and i + 2 < n and line[i + 1] == c and line[i + 2] == c:
            end = line.find(c * 3, i + 3)
            if end == -1:
                return line, None
            i = end + 3
            continue
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
        if c == "#":
            head = line[:i].rstrip()
            comment = line[i + 1:].strip()
            return head, comment
        i += 1
    return line, None


def _split_top_level_adjustment(
    line: str,
) -> tuple[str, str, str] | None:
    """Detect a top-level adjustment operator (``+=``, ``-=``, ``*=``,
    ``/=``) and split the line into ``(lhs_text, op, rhs_text)``.

    Returns ``None`` for any other shape — callers fall through to the
    equation/constraint classifier.

    "Top-level" means: not inside ``(...)``, ``[...]``, ``{...}``, not
    inside a string literal. Comments aren't possible here (the caller
    has already peeled them).

    Multi-character operator recognition is careful: ``==`` must not be
    mistaken for ``=`` followed by another ``=``, ``<=``/``>=``/``!=``
    are comparisons (not adjustments), and ``+=`` etc. take precedence
    over ``=`` so ``x += 5`` doesn't mis-parse as ``"x +" = "5"``.
    """
    n = len(line)
    i = 0
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    while i < n:
        c = line[i]

        if c in ("'", '"') and i + 2 < n and line[i + 1] == c and line[i + 2] == c:
            end = line.find(c * 3, i + 3)
            if end == -1:
                return None
            i = end + 3
            continue
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
        if c == "(":
            paren_depth += 1
            i += 1
            continue
        if c == ")":
            paren_depth -= 1
            i += 1
            continue
        if c == "[":
            bracket_depth += 1
            i += 1
            continue
        if c == "]":
            bracket_depth -= 1
            i += 1
            continue
        if c == "{":
            brace_depth += 1
            i += 1
            continue
        if c == "}":
            brace_depth -= 1
            i += 1
            continue

        # Top-level only.
        if paren_depth == 0 and bracket_depth == 0 and brace_depth == 0:
            # Two-char adjustment ops: +=, -=, *=, /=
            if c in "+-*/" and i + 1 < n and line[i + 1] == "=":
                op = line[i:i + 2]
                # Reject **=, //= explicitly: they aren't in the closed
                # adjustment-op set, and silently treating /= as // would
                # surprise the user.
                if c in "*/" and i > 0 and line[i - 1] == c:
                    return None
                if op in _ADJUSTMENT_OPS:
                    lhs_text = line[:i].strip()
                    rhs_text = line[i + 2:].strip()
                    return lhs_text, op, rhs_text
        i += 1

    return None


def _split_top_level_equals(
    line: str, class_name: str = "", source_index: int = 0,
) -> tuple[str, str] | None:
    """Find the single top-level ``=`` and split the line.

    Returns ``(lhs_text, rhs_text)`` if exactly one top-level ``=`` is
    found, else ``None`` (the line is a constraint, not an equation).

    Only a lone ``=`` is the equation operator. ``==`` is a Python
    comparison and is recognized but skipped (placement validation
    elsewhere ensures it appears only inside ``if`` conditions).
    ``<=``, ``>=``, ``!=`` are also skipped as comparison operators.

    "Top-level" means: not inside ``(...)``, ``[...]``, ``{...}``, not
    inside a single/double/triple-quoted string, not inside a ``#``
    comment.

    Multiple top-level ``=`` operators raise ``ValidationError``
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

        # `==` — Python comparison; skip as two characters. Must be
        # checked before the lone `=` case below.
        if c == "=" and i + 1 < n and line[i + 1] == "=":
            i += 2
            continue

        # `+=`, `-=`, `*=`, `/=` — adjustment operators, not equation.
        # Take precedence over the lone `=` case so that a malformed call
        # path which hands an adjustment line to this scanner doesn't
        # mis-classify it as ``"x +" = "5"``. The normal classifier
        # detects adjustments first; this is defense-in-depth.
        if c in "+-*/" and i + 1 < n and line[i + 1] == "=":
            i += 2
            continue

        # `=` (equation operator) — only the lone form, only at depth 0.
        if c == "=" and paren_depth == 0 and bracket_depth == 0 and brace_depth == 0:
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
            f"(more than one top-level `=`); write each equation on its own line."
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
    preceding_comments: Sequence[str | None] | None = None,
) -> tuple[
    list[ParsedEquation], list[ParsedConstraint],
    frozenset[str],
    dict[str, str],
    list[ParsedAdjustment],
]:
    """Parse the equations list into the unified representation.

    Returns ``(equations, constraints, all_optionals, typed_names,
    adjustments)``.

    Per-line classification, comma-expansion, malformed-shape rejection,
    self-reference detection, and mutual-inconsistency detection all
    happen here. Anything malformed or inconsistent surfaces as a
    ValidationError. Sympy is required (used for the algebraic checks);
    if it's not importable, ``_require_sympy`` raises a helpful error.

    ``class_name`` (optional) is the owning Component's class name. When
    set, error messages prefix with ``ClassName.equations[N]:``; when
    empty, the prefix is just ``equations[N]:``.

    ``preceding_comments`` (optional) is a parallel sequence aligned
    with ``eq_strs``: each entry is the immediately-preceding whole-line
    comment text (leading ``#`` stripped) for that line, or ``None``
    when there was no preceding comment. Used by the adjustment path to
    capture rationale for the introspection API. When omitted, every
    line is treated as having no preceding comment.

    ``typed_names`` maps each name carrying an inline ``:type`` tag to
    its type-name string. The type names are validated against the
    inline allowlist here; cross-site type agreement is enforced at the
    same time. Auto-declare consumes the dict downstream.
    """
    from scadwright.component.equations import (
        _INLINE_TYPE_ALLOWLIST,
        _extract_name_annotations,
        _require_sympy,
    )
    from scadwright.component.resolver.checks import (
        _check_adjusted_only_in_rules,
        _check_adjustment_rhs_no_adjusted_refs,
        _check_adjustment_uniformity,
        _check_bool_in_arithmetic,
        _check_eq_placement,
        _check_mutual_inconsistency,
        _check_non_float_solver_target,
        _check_override_rhs_evaluable,
        _check_self_reference,
        _check_unknown_function_calls,
    )

    _require_sympy()

    equations: list[ParsedEquation] = []
    constraints: list[ParsedConstraint] = []
    adjustments: list[ParsedAdjustment] = []
    all_optionals: set[str] = set()
    typed_names: dict[str, str] = {}
    # Track which source line each type assertion came from so
    # disagreement errors can point at both sites.
    typed_first_seen: dict[str, int] = {}

    if preceding_comments is None:
        preceding_comments = [None] * len(eq_strs)
    elif len(preceding_comments) != len(eq_strs):
        # Caller bug, not user-facing. Surface immediately.
        raise ValueError(
            f"preceding_comments has {len(preceding_comments)} entries "
            f"but eq_strs has {len(eq_strs)}; they must align."
        )

    for source_index, raw in enumerate(eq_strs):
        cleaned, line_opts, line_typed = _extract_name_annotations(raw)
        all_optionals |= line_opts
        line_opts_frozen = frozenset(line_opts)

        # Validate type-tag allowlist + cross-site agreement.
        for name, type_name in line_typed.items():
            if type_name not in _INLINE_TYPE_ALLOWLIST:
                raise ValidationError(
                    f"{_classdef_loc(class_name, source_index)}: unknown "
                    f"type tag `:{type_name}` on `{name}` in {raw!r}; "
                    f"allowed types are "
                    f"{sorted(_INLINE_TYPE_ALLOWLIST)}."
                )
            if name in typed_names and typed_names[name] != type_name:
                raise ValidationError(
                    f"{_classdef_loc(class_name, source_index)}: type "
                    f"disagreement on `{name}`: tagged `:{type_name}` "
                    f"here but `:{typed_names[name]}` at "
                    f"{_classdef_loc(class_name, typed_first_seen[name])}."
                )
            if name not in typed_names:
                typed_names[name] = type_name
                typed_first_seen[name] = source_index

        # Step 1: try adjustment classification. Adjustments are the
        # only line shape that uses the ``+=`` / ``-=`` / ``*=`` / ``/=``
        # tokens, so detection is unambiguous. Trailing comment is peeled
        # so the adjustment parser sees a clean LHS-op-RHS.
        body_text, trailing_comment = _peel_trailing_comment(cleaned)
        adj = _split_top_level_adjustment(body_text)
        if adj is not None:
            lhs_text, op, rhs_text = adj
            comment = trailing_comment
            if not comment:
                pre = preceding_comments[source_index]
                comment = pre or ""
            _emit_adjustment(
                lhs_text, op, rhs_text, cleaned, line_opts_frozen,
                source_index, class_name, comment, adjustments,
            )
            continue

        # Step 2: split on a top-level equation operator. If the line
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
    _check_eq_placement(equations, constraints, class_name)
    # Run the adjusted()-context check before the unknown-function
    # check — a misplaced ``adjusted(x)`` would otherwise surface as
    # "unknown function 'adjusted'", which buries the actual rule.
    _check_adjusted_only_in_rules(equations, adjustments, class_name)
    _check_unknown_function_calls(equations, constraints, class_name)
    _check_bool_in_arithmetic(typed_names, equations, constraints, class_name)
    _check_non_float_solver_target(
        typed_names, equations, frozenset(all_optionals), class_name,
    )
    _check_override_rhs_evaluable(
        equations, frozenset(all_optionals), class_name,
    )
    _check_self_reference(equations, class_name)
    _check_mutual_inconsistency(equations, class_name)
    _check_adjustment_uniformity(adjustments, class_name)
    _check_adjustment_rhs_no_adjusted_refs(adjustments, class_name)

    return (
        equations,
        constraints,
        frozenset(all_optionals),
        typed_names,
        adjustments,
    )


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

    # `?name` on a bare-Name target is the optional-default override
    # shape: the equation's RHS supplies the value when the user
    # didn't. The resolver skips applying the None default for these
    # names at startup so the equation can fill them in normally. For
    # non-float-typed names, ``_check_non_float_solver_target``
    # validates that the override RHS matches one of the accepted
    # shapes (`name or const`, `const if name is None else name`,
    # `name if name is not None else const`).

    refs = frozenset(_free_names_in(lhs) | _free_names_in(rhs))
    out.append(ParsedEquation(
        raw=raw, lhs=lhs, rhs=rhs,
        referenced_names=refs, line_optionals=line_opts,
        source_line_index=source_index,
    ))


def _emit_adjustment(
    lhs_text: str,
    op: str,
    rhs_text: str,
    raw: str,
    line_opts: frozenset[str],
    source_index: int,
    class_name: str,
    comment: str,
    out: list[ParsedAdjustment],
) -> None:
    """Build one or more ``ParsedAdjustment`` entries from a parsed
    ``lhs OP rhs`` triple.

    LHS must parse as either a bare ``Name`` (``cam_barrel_od += 0.3``)
    or a comma-separated list of bare ``Name``s (``a, b += slop`` —
    broadcasts to one adjustment per name, sharing the RHS, comment,
    and source-line index). Anything else (subscripts, attributes,
    expressions) is a class-def-time error.

    The RHS is parsed as a Python expression and stored as an AST node.
    Free names in the RHS get ``referenced_names``, used by the
    no-reference-to-adjusted-names check and by the resolver's
    None-skip path.
    """
    if not lhs_text:
        raise ValidationError(
            f"{_classdef_loc(class_name, source_index)}: cannot parse "
            f"adjustment {raw!r}: empty left-hand side. Write the "
            f"name being adjusted before the operator, e.g. "
            f"`x {op} 0.3` to add 0.3 to `x`."
        )
    if not rhs_text:
        raise ValidationError(
            f"{_classdef_loc(class_name, source_index)}: cannot parse "
            f"adjustment {raw!r}: empty right-hand side. Write a "
            f"value or expression after the operator, e.g. "
            f"`{lhs_text} {op} 0.3`."
        )

    # Parse the LHS as a Python expression so we can structurally check
    # it. We accept either ``Name`` or ``Tuple[Name, Name, ...]``.
    lhs_node = _parse_expr(lhs_text, raw, class_name, source_index)
    rhs_node = _parse_expr(rhs_text, raw, class_name, source_index)

    if isinstance(lhs_node, ast.Name):
        names = [lhs_node.id]
    elif (
        isinstance(lhs_node, ast.Tuple)
        and lhs_node.elts
        and all(isinstance(e, ast.Name) for e in lhs_node.elts)
    ):
        names = [e.id for e in lhs_node.elts]
    else:
        raise ValidationError(
            f"{_classdef_loc(class_name, source_index)}: adjustment "
            f"{raw!r}: left-hand side must be a name "
            f"(or a comma-separated list of names for broadcast); "
            f"got {ast.unparse(lhs_node)!r}."
        )

    refs = frozenset(_free_names_in(rhs_node))
    for name in names:
        out.append(ParsedAdjustment(
            raw=raw, name=name, op=op, rhs=rhs_node,
            referenced_names=refs, line_optionals=line_opts,
            comment=comment, source_line_index=source_index,
        ))


def _validate_and_rewrite_adjusted_calls(
    expr: ast.expr, raw: str, source_index: int, class_name: str,
) -> tuple[ast.expr, frozenset[str]]:
    """Detect, validate, and rewrite ``adjusted(name)`` calls in a
    constraint expression.

    Returns ``(rewritten_expr, wrapped_names)``. Each call of the form
    ``adjusted(X)`` is replaced with a synthetic
    ``Subscript(Name("__adjusted__"), Constant("X"))`` so the resolver
    can evaluate it against a namespace where ``__adjusted__`` maps to
    the post-adjust ``knowns`` dict. Bare-name references in the same
    expression are left untouched and resolve from the pre-adjust
    namespace by default.

    Validates each call has exactly one positional argument that is a
    bare ``Name``. Anything else (no args, multiple args, attribute
    access, expression) is a class-def-time error with a message
    naming the offending shape.
    """
    wrapped: set[str] = set()

    class _Rewriter(ast.NodeTransformer):
        def visit_Call(self, node: ast.Call) -> ast.AST:
            if not (
                isinstance(node.func, ast.Name)
                and node.func.id == _ADJUSTED_FN_NAME
            ):
                self.generic_visit(node)
                return node
            if node.keywords:
                raise ValidationError(
                    f"{_classdef_loc(class_name, source_index)}: "
                    f"`{_ADJUSTED_FN_NAME}(...)` does not accept "
                    f"keyword arguments in {raw!r}."
                )
            if len(node.args) != 1:
                raise ValidationError(
                    f"{_classdef_loc(class_name, source_index)}: "
                    f"`{_ADJUSTED_FN_NAME}(...)` takes exactly one "
                    f"argument; got {len(node.args)} in {raw!r}."
                )
            arg = node.args[0]
            if not isinstance(arg, ast.Name):
                shape = type(arg).__name__
                raise ValidationError(
                    f"{_classdef_loc(class_name, source_index)}: "
                    f"`{_ADJUSTED_FN_NAME}(...)` argument must be a "
                    f"bare name; got {shape} in {raw!r}."
                )
            wrapped.add(arg.id)
            new_node = ast.Subscript(
                value=ast.Name(id=_ADJUSTED_NS, ctx=ast.Load()),
                slice=ast.Constant(value=arg.id),
                ctx=ast.Load(),
            )
            ast.copy_location(new_node, node)
            return new_node

    rewritten = _Rewriter().visit(expr)
    ast.fix_missing_locations(rewritten)
    return rewritten, frozenset(wrapped)


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

    ``adjusted(name)`` calls inside the rule body are validated and
    rewritten into a synthetic subscript form so the resolver can
    evaluate them against the post-adjust namespace. The wrapped names
    are folded into ``referenced_names`` so auto-declare still finds
    them.
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
            # Compute referenced_names from the original (pre-rewrite)
            # AST so wrapped names are captured naturally.
            refs = frozenset(_free_names_in(new_compare)) - {_ADJUSTED_FN_NAME}
            rewritten, wrapped = _validate_and_rewrite_adjusted_calls(
                new_compare, raw, source_index, class_name,
            )
            # Use the expanded form as the raw text so error messages
            # name the specific failing component (e.g., "b < c") rather
            # than the original comma-expanded line ("a, b < c").
            try:
                expanded_raw = ast.unparse(new_compare)
            except Exception:
                expanded_raw = raw
            out.append(ParsedConstraint(
                raw=expanded_raw, expr=rewritten,
                referenced_names=refs, line_optionals=line_opts,
                source_line_index=source_index,
                uses_adjusted=bool(wrapped),
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

    refs = frozenset(_free_names_in(expr)) - {_ADJUSTED_FN_NAME}
    rewritten, wrapped = _validate_and_rewrite_adjusted_calls(
        expr, raw, source_index, class_name,
    )
    out.append(ParsedConstraint(
        raw=raw, expr=rewritten,
        referenced_names=refs, line_optionals=line_opts,
        source_line_index=source_index,
        uses_adjusted=bool(wrapped),
    ))


# =============================================================================
# Comma-broadcast shape detection
# =============================================================================
#
# Python's parser handles ``x, y > 0`` and ``x, y = 5`` very differently
# because of operator precedence: the comma binds looser than assignment
# but tighter than comparison. We get two sister shapes that the
# emitters need to recognize:
#
# - LHS comma-list with a value-side (``x, y = expr``) — the LHS parses
#   as a Tuple of bare Names. Detected by ``_bare_name_tuple``, used in
#   ``_emit_equation``'s broadcast branch.
# - Constraint comma-list (``x, y > 0``) — Python parses this as
#   ``Tuple([x, y, Compare(z, Gt, 0)])`` so the trailing Compare gets
#   absorbed into the tuple. Detected by ``_comma_expanded_compare``,
#   used in ``_emit_constraint``.
#
# Kept side-by-side so the two parser-edge cases stay legible together.


def _bare_name_tuple(node: ast.expr) -> list[ast.Name] | None:
    """Return the list of Names if ``node`` is a Tuple of bare Names.

    Used by ``_emit_equation`` to detect comma-broadcast equation
    targets (``x, y = 5``). Returns None for any other shape,
    including a Tuple containing non-Name elements.
    """
    if not isinstance(node, ast.Tuple):
        return None
    if not all(isinstance(e, ast.Name) for e in node.elts):
        return None
    return list(node.elts)


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
# Predicate shape recognition (constraint vs equation classification)
# =============================================================================


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
