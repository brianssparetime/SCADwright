"""Function-name allowlists used by the resolver and class-define-time checks.

Two related but distinct sets. Each answers a different question, so
membership differs — keep them separate even though they overlap.
"""

from __future__ import annotations


# Calls that return a single scalar number AND expect numeric arguments.
# Used to (a) auto-declare a Param as float when the equation RHS is
# provably numeric (``base._yields_scalar_numeric``) and (b) reject
# ``:bool``-tagged names passed as numeric arguments
# (``checks._check_bool_in_arithmetic``). The two questions share the
# same answer in this DSL because the curated namespace's numeric
# producers are also the ones that demand numeric inputs.
_NUMERIC_FUNCTION_NAMES = frozenset({
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
    "degrees", "radians",
    "sqrt", "log", "exp", "abs", "ceil", "floor",
    "min", "max", "sum", "round",
    "int", "float",
})


# Calls sympy can reason about symbolically. Subset of
# ``_NUMERIC_FUNCTION_NAMES`` minus ``{sum, round, int, float}`` — sympy
# can't symbolically invert sequence folds (``sum``), discontinuous
# rounding (``round``), or type coercions (``int``/``float``) — plus
# ``{Min, Max}`` as the sympy-idiom capitalized aliases. Used by
# ``resolver_ast.is_fully_algebraic`` to gate ``sympy.solve`` on a
# substituted expression. Must stay aligned with the lambda dict in
# ``resolver/sympy_bridge._ensure_algebraic_functions``; that function
# asserts equality on first call.
_ALGEBRAIC_FUNCTION_NAMES = frozenset({
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
    "degrees", "radians",
    "sqrt", "log", "exp", "abs", "ceil", "floor",
    "min", "max", "Min", "Max",
})
