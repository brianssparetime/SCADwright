"""AST utilities for the iterative equation resolver.

These functions operate on Python AST nodes that represent the right-hand
side (or both sides) of an `equations` entry. They're pure utilities with
no dependency on the rest of the equations machinery.

Three primitives:

- ``find_unknowns(node, knowns)``: free-name analysis. Which Name
  identifiers in the expression are not yet known? Comprehension-bound
  and lambda-bound names are correctly excluded.

- ``substitute_knowns(node, knowns, namespace=None)``: bottom-up partial
  evaluation. Replace every fully-known sub-expression with an
  ``ast.Constant`` holding its evaluated value. Returns a new AST; the
  input is not modified.

- ``is_fully_algebraic(node)``: structural check. Is this expression
  entirely composed of operations sympy can handle (arithmetic, the
  algebraic function set, plain Names and numeric Constants)? If yes
  it's safe to hand to sympy; if no, sympy can't reason about it and
  the resolver must Python-eval instead.
"""

from __future__ import annotations

import ast
from typing import Any

from scadwright.component.equations import _ALGEBRAIC_FUNCTION_NAMES


# Sentinel returned by the constant-fold path when eval fails. Distinct
# from ``None`` because ``None`` is a valid value to fold (e.g. an
# unsupplied optional Param).
_UNSAFE = object()


def _is_constant_safe(value: Any) -> bool:
    """True if ``value`` is safe to embed as ``ast.Constant``.

    Python's ``compile()`` only accepts a narrow set of types in
    ``ast.Constant``: numerics, bools, strings, bytes, ``None``, and
    tuples/frozensets thereof recursively. Folding a callable (like
    ``sin`` from the curated math namespace) into a Constant would also
    break downstream ``is_fully_algebraic`` checks because a Call's
    ``func`` slot is expected to be a ``Name``.

    Used to gate the fold-to-Constant step in :func:`substitute_knowns`.
    """
    if value is _UNSAFE:
        return False
    if value is None:
        return True
    # ``type(value) is bool`` excludes ``int`` from passing as a bool;
    # bool is its own branch below regardless. Use exact-type checks for
    # container types so namedtuples (tuple subclasses) and other
    # subclasses don't slip through — Python's ``compile()`` rejects
    # ``ast.Constant`` containing subclass instances.
    t = type(value)
    if t is bool:
        return True
    if t in (int, float, complex, str, bytes):
        return True
    if t is tuple or t is frozenset:
        return all(_is_constant_safe(item) for item in value)
    return False


# =============================================================================
# Free-variable analysis
# =============================================================================


def find_unknowns(node: ast.AST, knowns: dict[str, Any] | set[str]) -> set[str]:
    """Return the set of free Name identifiers in ``node`` that aren't in
    ``knowns``.

    Comprehension loop variables and lambda parameters are bound names,
    not free, and are excluded from the result. ``knowns`` can be a dict
    (keys treated as the known names) or a set/frozenset.
    """
    free = _free_names(node)
    if isinstance(knowns, dict):
        known_names = set(knowns.keys())
    else:
        known_names = set(knowns)
    return free - known_names


def _free_names(node: ast.AST) -> set[str]:
    """Collect identifiers that appear in ``Load`` context and aren't
    bound somewhere within ``node``.

    Conservative: any name used as a comprehension target or lambda
    parameter anywhere in the subtree is treated as bound everywhere in
    the subtree. This collapses Python's true scoping rules but is
    correct for the expression shapes that appear in equations
    (arithmetic, function calls, single-level comprehensions). Real
    Python evaluation at the resolver layer handles any scoping subtlety
    correctly because the evaluator gets the full namespace regardless
    of what this analysis decides.
    """
    bound = _bound_names(node)
    free: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
            if sub.id not in bound:
                free.add(sub.id)
    return free


def _bound_names(node: ast.AST) -> set[str]:
    """Names introduced by binding constructs anywhere within ``node``."""
    bound: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.comprehension):
            bound |= _names_in_target(sub.target)
        elif isinstance(sub, ast.Lambda):
            for arg in sub.args.args:
                bound.add(arg.arg)
            for arg in sub.args.posonlyargs:
                bound.add(arg.arg)
            for arg in sub.args.kwonlyargs:
                bound.add(arg.arg)
            if sub.args.vararg:
                bound.add(sub.args.vararg.arg)
            if sub.args.kwarg:
                bound.add(sub.args.kwarg.arg)
    return bound


def _names_in_target(target: ast.AST) -> set[str]:
    """Names introduced by an assignment target (handles tuple unpacking)."""
    names: set[str] = set()
    for sub in ast.walk(target):
        if isinstance(sub, ast.Name):
            names.add(sub.id)
    return names


# =============================================================================
# Bottom-up partial evaluation
# =============================================================================


def substitute_knowns(
    node: ast.AST,
    knowns: dict[str, Any],
    namespace: dict[str, Any] | None = None,
) -> ast.AST:
    """Walk ``node`` and replace fully-known sub-expressions with
    ``ast.Constant`` nodes holding the evaluated value.

    ``knowns`` maps name to value. ``namespace`` provides any additional
    callable or constant the eval needs (e.g., the curated builtins and
    math functions); the function is folded into the eval globals.

    Top-down: if the entire ``node`` is fully known it's collapsed in
    one step. Otherwise children are processed and partial results bubble
    up. Returns a new AST; the input is not modified.
    """
    full_ns = _build_eval_namespace(knowns, namespace)
    return _substitute_walk(node, knowns, full_ns, frozenset())


def _build_eval_namespace(
    knowns: dict[str, Any], extra: dict[str, Any] | None
) -> dict[str, Any]:
    ns: dict[str, Any] = {"__builtins__": {}}
    if extra:
        ns.update(extra)
    ns.update(knowns)
    return ns


def _substitute_walk(
    node: ast.AST,
    knowns: dict[str, Any],
    full_ns: dict[str, Any],
    bound: frozenset[str],
) -> ast.AST:
    """Bottom-up partial-eval walk.

    ``bound`` is the set of names bound by an enclosing comprehension or
    lambda. Those names must NOT be folded even if they happen to match
    something in ``full_ns`` (e.g., ``e`` colliding with ``math.e``).
    """
    # Reject folding any expression that references a bound name in
    # Load context — even if every other name is known, the bound name
    # is supposed to come from the iteration, not from ``full_ns``.
    if isinstance(node, ast.expr):
        unknowns = find_unknowns(node, full_ns)
        load_names = _load_names(node)
        bound_loads = load_names & bound
        if not unknowns and not bound_loads:
            try:
                expr_node = ast.Expression(body=node)
                ast.fix_missing_locations(expr_node)
                code = compile(expr_node, "<substitute_knowns>", "eval")
                value = eval(code, full_ns)
            except Exception:
                # Eval failed (None propagation, division by zero, etc.).
                # Don't collapse this node; let the caller decide what to do.
                value = _UNSAFE
            if _is_constant_safe(value):
                new_node = ast.Constant(value=value)
                ast.copy_location(new_node, node)
                return new_node
            # Don't collapse non-scalar values into ast.Constant: a
            # callable (e.g. ``sin`` from the curated namespace) would
            # break ``is_fully_algebraic`` (Call.func ceases to be a
            # Name); a tuple-of-namedtuples or other complex value would
            # later trip ``compile()`` when the resolver tries to
            # forward-eval. Fall through to per-field recursion so we
            # only fold scalars that are safe to embed as constants.

    # Comprehensions and lambdas introduce new bindings in their own
    # subtree. Reproduce them carefully: the iter expressions in
    # generators are evaluated in the enclosing scope (so they see the
    # outer ``bound``), but elt/ifs/body see the inner bindings too.
    if isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp, ast.DictComp)):
        return _substitute_comprehension(node, knowns, full_ns, bound)
    if isinstance(node, ast.Lambda):
        return _substitute_lambda(node, knowns, full_ns, bound)

    if isinstance(node, ast.AST):
        new_fields: dict[str, Any] = {}
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                new_fields[field] = [
                    _substitute_walk(item, knowns, full_ns, bound)
                    if isinstance(item, ast.AST) else item
                    for item in value
                ]
            elif isinstance(value, ast.AST):
                new_fields[field] = _substitute_walk(value, knowns, full_ns, bound)
            else:
                new_fields[field] = value
        new_node = type(node)(**new_fields)
        ast.copy_location(new_node, node)
        return new_node

    return node


def _load_names(node: ast.AST) -> set[str]:
    """All Names appearing in Load context anywhere within ``node``."""
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
            out.add(sub.id)
    return out


def _substitute_comprehension(
    node, knowns, full_ns, bound: frozenset[str],
):
    """Walk a comprehension node, threading bindings through generators
    so inner bindings don't leak out and outer ``bound`` names don't
    fold inside.
    """
    new_generators = []
    inner_bound = set(bound)
    for gen in node.generators:
        # ``gen.iter`` is evaluated in the scope OUTSIDE the new binding
        # introduced by ``gen.target``. Substitute it with the current
        # ``inner_bound`` (which already includes any prior generators
        # in the same comprehension).
        new_iter = _substitute_walk(gen.iter, knowns, full_ns, frozenset(inner_bound))
        # Add the target's bindings before walking the ifs.
        inner_bound |= _names_in_target(gen.target)
        new_ifs = [
            _substitute_walk(i, knowns, full_ns, frozenset(inner_bound))
            for i in gen.ifs
        ]
        new_gen = ast.comprehension(
            target=gen.target,
            iter=new_iter,
            ifs=new_ifs,
            is_async=gen.is_async,
        )
        ast.copy_location(new_gen, gen)
        new_generators.append(new_gen)

    inner_bound_frozen = frozenset(inner_bound)
    fields: dict[str, Any] = {"generators": new_generators}
    if isinstance(node, ast.DictComp):
        fields["key"] = _substitute_walk(node.key, knowns, full_ns, inner_bound_frozen)
        fields["value"] = _substitute_walk(node.value, knowns, full_ns, inner_bound_frozen)
    else:
        fields["elt"] = _substitute_walk(node.elt, knowns, full_ns, inner_bound_frozen)

    new_node = type(node)(**fields)
    ast.copy_location(new_node, node)
    return new_node


def _substitute_lambda(node, knowns, full_ns, bound: frozenset[str]):
    """Walk a lambda body with its parameter names added to ``bound``."""
    args = node.args
    inner_bound = set(bound)
    for arg in args.args:
        inner_bound.add(arg.arg)
    for arg in args.posonlyargs:
        inner_bound.add(arg.arg)
    for arg in args.kwonlyargs:
        inner_bound.add(arg.arg)
    if args.vararg:
        inner_bound.add(args.vararg.arg)
    if args.kwarg:
        inner_bound.add(args.kwarg.arg)
    new_body = _substitute_walk(node.body, knowns, full_ns, frozenset(inner_bound))
    new_node = ast.Lambda(args=args, body=new_body)
    ast.copy_location(new_node, node)
    return new_node


# =============================================================================
# Algebraic-shape detection
# =============================================================================


def is_fully_algebraic(node: ast.AST) -> bool:
    """True if every operation in ``node`` is something sympy can reason
    about.

    Allowed: ``Name``, numeric ``Constant``, ``BinOp``, ``UnaryOp``,
    ``Compare`` (comparison chain), ``Tuple`` of bare names (for
    comma-expanded constraint LHS shapes), and ``Call`` whose callee is
    a bare name in the algebraic function allowlist (``sin``, ``cos``,
    ``sqrt``, ``min``, ``max``, etc.).

    Disallowed: attribute access, subscript, comprehensions, conditional
    expressions, list/dict/set/tuple-of-non-Names literals, lambdas, and
    calls to anything outside the algebraic allowlist.
    """
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (int, float)) and not isinstance(
            node.value, bool
        )
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.BinOp):
        return is_fully_algebraic(node.left) and is_fully_algebraic(node.right)
    if isinstance(node, ast.UnaryOp):
        return is_fully_algebraic(node.operand)
    if isinstance(node, ast.Compare):
        return is_fully_algebraic(node.left) and all(
            is_fully_algebraic(c) for c in node.comparators
        )
    if isinstance(node, ast.Tuple):
        return all(isinstance(e, ast.Name) for e in node.elts)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            return False
        if node.func.id not in _ALGEBRAIC_FUNCTION_NAMES:
            return False
        if node.keywords:
            return False
        return all(is_fully_algebraic(a) for a in node.args)
    return False
