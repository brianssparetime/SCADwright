"""Curated namespace and helpers used by the iterative equation resolver.

The actual equation-solving and constraint-checking machinery lives in
``scadwright.component.resolver``. This module holds the small
shared pieces:

- ``_require_sympy``: imports sympy and raises a helpful ImportError
  when it isn't installed.
- ``_extract_optional_markers``: strips the ``?`` sigil from an
  equations-list string and returns the names that were prefixed.
- ``_CURATED_BUILTINS`` and ``_CURATED_MATH``: the names available
  inside derivation and predicate expressions. Anything not in these
  (or in the Component's Param/derivation set) is rejected at
  class-definition time.
- The cardinality helpers (``exactly_one``, ``at_least_one``,
  ``at_most_one``, ``all_or_none``) registered into the curated
  namespace so users can write
  ``"exactly_one(?fillet, ?chamfer)"`` etc.
"""

from __future__ import annotations

import math
from typing import Any


def _require_sympy():
    """Import sympy, or raise ImportError with extras-install hint."""
    try:
        import sympy  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "Components with `equations` require sympy. "
            "Install with: pip install 'scadwright[equations]'"
        ) from e


# =============================================================================
# Optional-parameter sigil: `?name`
# =============================================================================


def _extract_optional_markers(eq_str: str) -> tuple[str, set[str]]:
    """Strip ``?name`` prefixes from an equations-list string.

    Returns ``(cleaned, optional_names)`` — the cleaned string with every
    ``?`` removed, and the set of names that were prefixed. The sigil
    marks a Param as optional (auto-declared ``Param(float, default=None)``).

    A hand-rolled scanner, not a regex, so string literals and ``#``
    comments are respected: a literal ``?`` inside ``"..."`` or
    ``'...'`` is left alone. Handles single-quote and double-quote
    forms, triple-quoted strings (no escape processing inside, matching
    Python semantics), and backslash escapes inside single-quoted
    strings.
    """
    out: list[str] = []
    optional: set[str] = set()
    i = 0
    n = len(eq_str)
    while i < n:
        c = eq_str[i]

        # Triple-quoted string — copy through the matching closing triple.
        if c in ("'", '"') and eq_str[i:i + 3] == c * 3:
            end = eq_str.find(c * 3, i + 3)
            if end == -1:
                out.append(eq_str[i:])
                return "".join(out), optional
            out.append(eq_str[i:end + 3])
            i = end + 3
            continue

        # Single-line string literal — copy through the matching quote,
        # respecting backslash escapes.
        if c in ("'", '"'):
            quote = c
            j = i + 1
            while j < n and eq_str[j] != quote:
                if eq_str[j] == "\\" and j + 1 < n:
                    j += 2
                else:
                    j += 1
            out.append(eq_str[i:min(j + 1, n)])
            i = min(j + 1, n)
            continue

        # Comment — copy to end of line (rare in equations; handle anyway).
        if c == "#":
            eol = eq_str.find("\n", i)
            if eol == -1:
                out.append(eq_str[i:])
                return "".join(out), optional
            out.append(eq_str[i:eol])
            i = eol
            continue

        # Optional sigil: `?` followed directly by an identifier start.
        if c == "?" and i + 1 < n and (eq_str[i + 1].isalpha() or eq_str[i + 1] == "_"):
            j = i + 1
            while j < n and (eq_str[j].isalnum() or eq_str[j] == "_"):
                j += 1
            name = eq_str[i + 1:j]
            optional.add(name)
            out.append(name)
            i = j
            continue

        # Plain character.
        out.append(c)
        i += 1

    return "".join(out), optional


# =============================================================================
# Multi-line `equations = """..."""` splitter
# =============================================================================


def _split_equations_text(text: str) -> list[str]:
    """Split a multi-line ``equations`` string into logical equation lines.

    Mirrors the lexical conventions of the per-line scanners
    (``_extract_optional_markers``, ``_split_top_level_equals``): single,
    double, and triple-quoted string literals are recognized so a ``#``
    or quote inside a literal isn't misread as a comment or boundary.

    A logical line ends at a newline, except when:

    - the newline lies inside a string literal (kept verbatim — an
      unterminated literal is left for downstream parsing to surface);
    - bracket/paren/brace depth is positive (the line continues);
    - the newline is preceded by a ``\\`` outside strings/comments (the
      backslash and newline are swallowed, the line continues). A ``\\``
      that falls inside a ``#`` comment does NOT continue the line —
      matching Python.

    After splitting, each logical line is stripped; empty lines and
    whole-line ``#`` comments are dropped. Inline comments mid-line
    survive — the per-line scanners that consume each entry already
    handle them.
    """
    lines: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(text)
    in_comment = False

    def _flush() -> None:
        s = "".join(buf).strip()
        buf.clear()
        if not s or s.startswith("#"):
            return
        lines.append(s)

    while i < n:
        c = text[i]

        # Inside an end-of-line `#` comment: scan to newline, then end the
        # logical line. A trailing backslash inside a comment does NOT
        # continue the line (Python semantics).
        if in_comment:
            if c == "\n":
                in_comment = False
                _flush()
                i += 1
                continue
            buf.append(c)
            i += 1
            continue

        # Triple-quoted string — copy through the closing triple verbatim,
        # newlines included.
        if c in ("'", '"') and text[i:i + 3] == c * 3:
            end = text.find(c * 3, i + 3)
            if end == -1:
                buf.append(text[i:])
                i = n
                break
            buf.append(text[i:end + 3])
            i = end + 3
            continue

        # Single-line string literal — copy through the matching quote,
        # honoring backslash escapes.
        if c in ("'", '"'):
            quote = c
            j = i + 1
            while j < n and text[j] != quote:
                if text[j] == "\\" and j + 1 < n:
                    j += 2
                else:
                    j += 1
            buf.append(text[i:min(j + 1, n)])
            i = min(j + 1, n)
            continue

        # Start of a comment: stay on this logical line until the next
        # newline (handled above).
        if c == "#":
            in_comment = True
            buf.append(c)
            i += 1
            continue

        # Backslash continuation: `\` immediately before `\n` (outside
        # strings and comments) swallows both, gluing this line to the
        # next.
        if c == "\\" and i + 1 < n and text[i + 1] == "\n":
            i += 2
            continue

        # Newline outside strings/comments: continue the logical line if
        # any bracket is open; otherwise flush.
        if c == "\n":
            depth = _bracket_depth("".join(buf))
            if depth > 0:
                buf.append(" ")
                i += 1
                continue
            _flush()
            i += 1
            continue

        buf.append(c)
        i += 1

    if in_comment:
        in_comment = False
    _flush()
    return lines


def _bracket_depth(s: str) -> int:
    """Net bracket/paren/brace depth in ``s``, ignoring quoted regions.

    Used by ``_split_equations_text`` to decide whether a newline
    continues the current logical line. Triple-quoted and single-quoted
    string literals are skipped so brackets inside literals don't count.
    """
    depth = 0
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in ("'", '"') and s[i:i + 3] == c * 3:
            end = s.find(c * 3, i + 3)
            i = n if end == -1 else end + 3
            continue
        if c in ("'", '"'):
            quote = c
            j = i + 1
            while j < n and s[j] != quote:
                if s[j] == "\\" and j + 1 < n:
                    j += 2
                else:
                    j += 1
            i = min(j + 1, n)
            continue
        if c == "#":
            eol = s.find("\n", i)
            i = n if eol == -1 else eol
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        i += 1
    return depth


# =============================================================================
# Cardinality helpers (used in `equations` strings via the curated namespace)
# =============================================================================


def _exactly_one(*args: Any) -> bool:
    """True iff exactly one argument is not None."""
    return sum(1 for x in args if x is not None) == 1


def _at_least_one(*args: Any) -> bool:
    """True iff at least one argument is not None."""
    return any(x is not None for x in args)


def _at_most_one(*args: Any) -> bool:
    """True iff zero or one argument is not None. Vacuously True for ()."""
    return sum(1 for x in args if x is not None) <= 1


def _all_or_none(*args: Any) -> bool:
    """True iff every argument is None, or every argument is not None.

    Vacuously True for ().
    """
    set_count = sum(1 for x in args if x is not None)
    return set_count == 0 or set_count == len(args)


# =============================================================================
# Curated namespace for derivation and predicate evaluation
# =============================================================================


_CURATED_BUILTINS: dict[str, Any] = {
    "range": range, "tuple": tuple, "list": list, "dict": dict,
    "set": set, "frozenset": frozenset,
    "zip": zip, "enumerate": enumerate,
    "sum": sum, "abs": abs, "round": round, "len": len,
    "min": min, "max": max,
    "int": int, "float": float, "bool": bool, "str": str,
    "all": all, "any": any,
    "sorted": sorted, "reversed": reversed,
    "True": True, "False": False, "None": None,
    # Cardinality helpers. Each checks `x is not None` on every argument;
    # pair naturally with the `?` sigil (`exactly_one(?a, ?b)` etc.).
    "exactly_one": _exactly_one,
    "at_least_one": _at_least_one,
    "at_most_one": _at_most_one,
    "all_or_none": _all_or_none,
}


_CURATED_MATH: dict[str, Any] = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
    "sqrt": math.sqrt, "log": math.log, "exp": math.exp,
    "ceil": math.ceil, "floor": math.floor,
    "pi": math.pi, "e": math.e, "inf": math.inf,
}
