"""Shared dataclasses, error-prefix helpers, and bare-name allowlists.

These are the leaves of the resolver subpackage's import graph: every
other module imports from here, this module imports from no sibling.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


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


# =============================================================================
# Bare-name call allowlists shared between parsing and class-def-time checks
# =============================================================================


# Predicate-shape calls plus cardinality helpers — all are valid bare-
# name call targets in equations text.
_PREDICATE_CALL_NAMES = frozenset({
    "all", "any", "isinstance",
    "exactly_one", "at_least_one", "at_most_one", "all_or_none",
})
