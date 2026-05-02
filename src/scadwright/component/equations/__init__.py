"""Curated namespace and helpers used by the iterative equation resolver.

The actual equation-solving and constraint-checking machinery lives in
``scadwright.component.resolver``. This package holds the small shared
pieces, organized by concern:

- :mod:`.lex` — hand-rolled scanners (``_extract_name_annotations``,
  ``_extract_optional_markers``, ``_split_equations_text``,
  ``_bracket_depth``, ``_INLINE_TYPE_ALLOWLIST``, ``_require_sympy``).
- :mod:`.curated` — the curated namespace exposed inside derivation
  and predicate expressions (``_CURATED_BUILTINS``, ``_CURATED_MATH``)
  plus the cardinality helpers
  (``_exactly_one``/``_at_least_one``/``_at_most_one``/``_all_or_none``).
- :mod:`.names` — function-name allowlists (``_NUMERIC_FUNCTION_NAMES``
  and ``_ALGEBRAIC_FUNCTION_NAMES``) used by both the auto-declare
  heuristic and the ``is_fully_algebraic`` sympy gate.

The full surface is re-exported at package level so existing
``from scadwright.component.equations import ...`` imports keep working.
"""

from scadwright.component.equations.curated import (
    _CURATED_BUILTINS,
    _CURATED_MATH,
    _all_or_none,
    _at_least_one,
    _at_most_one,
    _exactly_one,
)
from scadwright.component.equations.lex import (
    _INLINE_TYPE_ALLOWLIST,
    _bracket_depth,
    _extract_name_annotations,
    _extract_optional_markers,
    _require_sympy,
    _split_equations_text,
)
from scadwright.component.equations.names import (
    _ALGEBRAIC_FUNCTION_NAMES,
    _NUMERIC_FUNCTION_NAMES,
)

__all__ = [
    "_ALGEBRAIC_FUNCTION_NAMES",
    "_CURATED_BUILTINS",
    "_CURATED_MATH",
    "_INLINE_TYPE_ALLOWLIST",
    "_NUMERIC_FUNCTION_NAMES",
    "_all_or_none",
    "_at_least_one",
    "_at_most_one",
    "_bracket_depth",
    "_exactly_one",
    "_extract_name_annotations",
    "_extract_optional_markers",
    "_require_sympy",
    "_split_equations_text",
]
