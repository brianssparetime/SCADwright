"""Iterative resolver for the equations DSL.

Given a parsed list of equations and constraints plus the user's
supplied values, the resolver iteratively fills in unknowns until it
either succeeds or produces an explanatory error (insufficient,
inconsistent, or ambiguous).

Public surface, re-exported here so callers can write
``from scadwright.component.resolver import IterativeResolver`` etc.
without caring which sibling module each name lives in:

- :class:`ParsedEquation`, :class:`ParsedConstraint`: dataclass shapes
  the resolver consumes.
- :func:`parse_equations_unified`: converts the raw equations list into
  the unified representation, running every class-define-time
  validation pass along the way.
- :func:`extract_per_param_validator`: recognizer for ``name OP const``
  shapes; the auto-init layer attaches the resulting validator to the
  Param so it also fires on direct ``Param.__set__`` calls.
- :class:`IterativeResolver`: the resolver itself. Construct with the
  parsed data and supplied values, call ``resolve()``.
- :func:`ast_to_sympy`: AST → sympy bridge, exposed for tooling that
  needs to reason about the same algebraic subset.
"""

from scadwright.component.resolver.iterative import IterativeResolver
from scadwright.component.resolver.parsing import parse_equations_unified
from scadwright.component.resolver.per_param import extract_per_param_validator
from scadwright.component.resolver.sympy_bridge import ast_to_sympy
from scadwright.component.resolver.types import (
    ParsedConstraint,
    ParsedEquation,
)

__all__ = [
    "IterativeResolver",
    "ParsedConstraint",
    "ParsedEquation",
    "ast_to_sympy",
    "extract_per_param_validator",
    "parse_equations_unified",
]
