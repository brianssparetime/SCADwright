"""Hand-rolled scanners for the equations DSL.

Three scanners share a common discipline (string-literal awareness,
``#``-comment awareness, bracket-depth tracking where it matters):

- ``_extract_name_annotations`` — strips the ``?`` sigil and ``:type``
  tags from a single equations line, returning the cleaned text plus
  the optional-name set and typed-name dict.
- ``_extract_optional_markers`` — backward-compat wrapper that returns
  just ``(cleaned, optional_names)``.
- ``_split_equations_text`` — splits a multi-line ``equations``
  string into logical equation lines, honoring triple-quoted strings,
  bracket continuations, and ``\\``-newline continuations.
- ``_bracket_depth`` — net bracket/paren/brace depth used by the
  splitter for line continuation.

``_INLINE_TYPE_ALLOWLIST`` (the closed set of type names accepted in
``name:type`` annotations) lives here so the scanner-side validation
shares the table with the auto-declare path downstream.

``_require_sympy`` raises a helpful ``ImportError`` when sympy isn't
installed; the resolver and the equation parser call it at the points
they're about to use sympy.
"""

from __future__ import annotations


# =============================================================================
# Inline type-annotation allowlist
# =============================================================================
#
# Closed set of type names accepted in ``name:type`` annotations inside
# ``equations`` text. Maps the textual type name to the runtime type. No
# namespace lookup; custom classes use ``Param(CustomType)`` instead.

_INLINE_TYPE_ALLOWLIST: dict[str, type] = {
    "bool": bool, "int": int, "str": str,
    "tuple": tuple, "list": list, "dict": dict,
}


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
# Sigil and type-tag extraction: `?name` and `name:type`
# =============================================================================


def _extract_name_annotations(
    eq_str: str,
) -> tuple[str, set[str], dict[str, str]]:
    """Strip ``?`` sigils and ``:type`` tags from an equations string.

    Returns ``(cleaned, optional_names, typed_names)``:

    - ``cleaned``: the input with every ``?`` and every ``:type``
      annotation stripped. The bare identifier remains in place.
    - ``optional_names``: identifiers that carried a ``?`` prefix.
      They auto-declare as ``Param(type, default=None)`` (or
      ``Param(float, default=None)`` if no type tag).
    - ``typed_names``: identifier → type-name string for every
      identifier carrying a ``:type`` tag. Type-name validation
      against the allowlist happens downstream.

    A hand-rolled scanner, not a regex, so string literals and ``#``
    comments are respected: a literal ``?`` or ``:`` inside ``"..."``
    or ``'...'`` or after ``#`` is left alone. Handles single-quote
    and double-quote forms, triple-quoted strings, and backslash
    escapes inside single-quoted strings.

    Type-tag recognition: after consuming an identifier (with or
    without a leading ``?``), if the next non-whitespace character is
    ``:`` and the next non-whitespace character after that starts an
    identifier, the type is captured and the ``:`` and surrounding
    whitespace and type identifier are stripped from the cleaned
    output. All four spacings work: ``count:int``, ``count: int``,
    ``count :int``, ``count : int``.

    Tag recognition is suppressed inside ``[...]`` and ``{...}`` — in
    those contexts the ``:`` is a slice separator or a dict-key
    separator, not a type-tag separator. Tags inside ``(...)`` are
    still recognized (parens are grouping or call syntax; ``:`` has no
    other meaning there). Strings and comments are eaten before any
    bracket counting, so brackets inside them don't affect depth.
    """
    out: list[str] = []
    optional: set[str] = set()
    typed: dict[str, str] = {}
    i = 0
    n = len(eq_str)
    # Net depth of `[` and `{` combined; `(` is not counted because
    # tags are valid inside parens (`len(size:tuple) = 3`,
    # `func(arg:int)`, `(?count:int) > 0`). Inside `[...]` `:` is a
    # slice colon; inside `{...}` `:` is a dict-key colon — both
    # suppress tag recognition.
    bracket_depth = 0

    def _read_identifier(start: int) -> tuple[str, int]:
        """Read an identifier starting at ``start``; return (name, end)."""
        j = start
        while j < n and (eq_str[j].isalnum() or eq_str[j] == "_"):
            j += 1
        return eq_str[start:j], j

    def _maybe_type_tag(name: str, after: int) -> int:
        """If the chars at ``after`` form ``[ws]:[ws]type``, record and
        return the position after the type identifier; otherwise return
        ``after`` unchanged.

        Whitespace (spaces or tabs) on either side of the ``:`` is
        accepted. Newlines are not — a type tag is always within a
        single logical line.
        """
        j = after
        while j < n and eq_str[j] in " \t":
            j += 1
        if j >= n or eq_str[j] != ":":
            return after
        j += 1
        while j < n and eq_str[j] in " \t":
            j += 1
        if j >= n or not (eq_str[j].isalpha() or eq_str[j] == "_"):
            return after
        type_name, type_end = _read_identifier(j)
        typed[name] = type_name
        return type_end

    while i < n:
        c = eq_str[i]

        # Triple-quoted string — copy through the matching closing triple.
        if c in ("'", '"') and eq_str[i:i + 3] == c * 3:
            end = eq_str.find(c * 3, i + 3)
            if end == -1:
                out.append(eq_str[i:])
                return "".join(out), optional, typed
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
                return "".join(out), optional, typed
            out.append(eq_str[i:eol])
            i = eol
            continue

        # Optional sigil: `?` followed directly by an identifier start.
        # Strip the `?`, optionally consume a `:type` tag (only when not
        # inside `[...]`/`{...}` — see depth note above).
        if c == "?" and i + 1 < n and (eq_str[i + 1].isalpha() or eq_str[i + 1] == "_"):
            name, name_end = _read_identifier(i + 1)
            optional.add(name)
            out.append(name)
            i = _maybe_type_tag(name, name_end) if bracket_depth == 0 else name_end
            continue

        # Bare identifier start: read the identifier, then check for a
        # `:type` tag immediately after. We can't proactively skip
        # identifiers that aren't type-tagged because we'd lose the
        # ability to scan the next char — but the bookkeeping cost is
        # cheap: only commit the strip if a `:identifier` follows.
        # Suppressed inside `[...]`/`{...}` so slice and dict-key colons
        # aren't mis-read as tags.
        if c.isalpha() or c == "_":
            name, name_end = _read_identifier(i)
            out.append(name)
            i = _maybe_type_tag(name, name_end) if bracket_depth == 0 else name_end
            continue

        # Bracket/brace depth tracking. Parens are NOT counted: tags are
        # legitimate inside `(...)`. Negative depth from unmatched
        # closers is harmless — downstream parsing surfaces the syntax
        # error; we just continue to behave like top level.
        if c == "[" or c == "{":
            bracket_depth += 1
        elif c == "]" or c == "}":
            bracket_depth -= 1

        # Plain character.
        out.append(c)
        i += 1

    return "".join(out), optional, typed


def _extract_optional_markers(eq_str: str) -> tuple[str, set[str]]:
    """Backward-compat wrapper around :func:`_extract_name_annotations`.

    Returns just ``(cleaned, optional_names)``, discarding the typed-
    names dict. Callers that need type tags should use
    :func:`_extract_name_annotations` directly.
    """
    cleaned, optional, _typed = _extract_name_annotations(eq_str)
    return cleaned, optional


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
