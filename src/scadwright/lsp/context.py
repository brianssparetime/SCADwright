"""Syntactic-context detection for cursor positions in equation lines.

Given a splitter-cleaned equation line and a column, classify the
cursor's context as one of:

- ``EXPRESSION``: the cursor sits at a position where a name or
  expression can be typed. The default for cursors not in a string,
  comment, or type-tag spot.
- ``TYPE_TAG``: the cursor sits after a ``:`` that introduces an
  inline type tag (``?count:`` and the user is typing the type
  name). Suppressed inside ``[...]`` and ``{...}`` because ``:``
  there is a slice or dict-key separator.
- ``ATTRIBUTE``: the cursor sits after a ``.`` (the user is typing
  an attribute name on an expression base).
- ``STRING``: the cursor sits inside a string literal (single,
  double, triple-single, or triple-double quoted).
- ``COMMENT``: the cursor sits inside a ``#`` comment.

The detector operates on the splitter-cleaned line text
(``LogicalLine.cleaned``) — sigils and type tags are still present
at this layer, so detecting "after a ``:``" is straightforward.
"""

from __future__ import annotations

from enum import Enum


class ContextKind(Enum):
    """Cursor-context classification for completion and hover."""
    EXPRESSION = "expression"
    TYPE_TAG = "type_tag"
    ATTRIBUTE = "attribute"
    STRING = "string"
    COMMENT = "comment"


def classify_context(line: str, col: int) -> ContextKind:
    """Return the syntactic context of the cursor at ``col`` in ``line``.

    ``col`` is a column within ``line`` (the splitter-cleaned text).
    ``col == len(line)`` is allowed (cursor at end of line); negative
    columns are clamped to 0.
    """
    if col < 0:
        col = 0
    state = _scan_line_state(line, col)
    if state.in_string:
        return ContextKind.STRING
    if state.in_comment:
        return ContextKind.COMMENT
    prev = _previous_non_blank_non_ident(line, col)
    if prev == ".":
        return ContextKind.ATTRIBUTE
    if prev == ":" and state.bracket_depth == 0:
        return ContextKind.TYPE_TAG
    return ContextKind.EXPRESSION


# =============================================================================
# Internals
# =============================================================================


class _ScanState:
    """State captured after scanning ``line[:col]``.

    ``in_string`` covers all four quote styles. ``bracket_depth`` is
    the net count of ``[`` and ``{`` minus their closers; ``(`` is
    not counted because type tags are valid inside parens but not
    inside slices or dict-key positions.
    """
    __slots__ = ("in_string", "in_comment", "bracket_depth")

    def __init__(
        self, in_string: bool, in_comment: bool, bracket_depth: int,
    ) -> None:
        self.in_string = in_string
        self.in_comment = in_comment
        self.bracket_depth = bracket_depth


def _scan_line_state(line: str, target_col: int) -> _ScanState:
    """Walk forward through ``line[:target_col]`` tracking string,
    comment, and bracket-depth state.
    """
    in_single = False
    in_double = False
    in_triple_single = False
    in_triple_double = False
    in_comment = False
    bracket_depth = 0
    i = 0
    n = min(len(line), target_col)
    while i < n:
        # Triple-quote opens (only if not already inside a string/comment).
        if not (
            in_single
            or in_double
            or in_triple_single
            or in_triple_double
            or in_comment
        ):
            if line[i:i + 3] == '"""':
                in_triple_double = True
                i += 3
                continue
            if line[i:i + 3] == "'''":
                in_triple_single = True
                i += 3
                continue
        # Triple-quote closes.
        if in_triple_double and line[i:i + 3] == '"""':
            in_triple_double = False
            i += 3
            continue
        if in_triple_single and line[i:i + 3] == "'''":
            in_triple_single = False
            i += 3
            continue
        # Inside any triple-quoted string: just advance.
        if in_triple_single or in_triple_double:
            i += 1
            continue
        # Inside a single-quoted string (single or double quote): respect
        # backslash escapes; a closing quote of the right type ends the
        # string.
        if in_single:
            if line[i] == "\\" and i + 1 < n:
                i += 2
                continue
            if line[i] == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if line[i] == "\\" and i + 1 < n:
                i += 2
                continue
            if line[i] == '"':
                in_double = False
            i += 1
            continue
        # Inside a `#` comment: just advance.
        if in_comment:
            i += 1
            continue
        # Not inside any string or comment.
        c = line[i]
        if c == "'":
            in_single = True
            i += 1
            continue
        if c == '"':
            in_double = True
            i += 1
            continue
        if c == "#":
            in_comment = True
            i += 1
            continue
        if c == "[" or c == "{":
            bracket_depth += 1
        elif c == "]" or c == "}":
            bracket_depth -= 1
        i += 1
    in_string = (
        in_single or in_double or in_triple_single or in_triple_double
    )
    return _ScanState(
        in_string=in_string,
        in_comment=in_comment,
        bracket_depth=bracket_depth,
    )


def _previous_non_blank_non_ident(line: str, col: int) -> str | None:
    """Walk left from ``col`` over identifier characters and horizontal
    whitespace; return the next non-blank non-identifier character,
    or ``None`` when start-of-line is reached first.

    Used by :func:`classify_context` to pick out the operator
    immediately preceding the cursor's name-being-typed: ``.`` for
    attribute access, ``:`` for type-tag annotation. The walk is
    identical for both cases; the operator-specific suppression
    (e.g., bracket-depth check for ``:``) lives in the caller.
    """
    i = col - 1
    while i >= 0 and (line[i].isalnum() or line[i] == "_"):
        i -= 1
    while i >= 0 and line[i] in " \t":
        i -= 1
    return line[i] if i >= 0 else None


def extract_attribute_chain(line: str, col: int) -> list[str] | None:
    """If the cursor is in attribute-completion position (after a
    ``.`` whose left operand is an identifier chain), return the
    chain of identifiers leading up to the cursor. Else ``None``.

    For ``spec.clearances.|``, returns ``["spec", "clearances"]``.
    For ``spec.|``, returns ``["spec"]``.

    Non-identifier bases (parenthesized expressions, subscripts,
    calls) yield ``None`` — the static type information needed to
    resolve their attributes isn't available without actually
    running the code.
    """
    i = col - 1
    while i >= 0 and (line[i].isalnum() or line[i] == "_"):
        i -= 1
    while i >= 0 and line[i] in " \t":
        i -= 1
    if i < 0 or line[i] != ".":
        return None
    chain: list[str] = []
    while True:
        i -= 1  # skip the dot
        while i >= 0 and line[i] in " \t":
            i -= 1
        if i < 0 or not (line[i].isalnum() or line[i] == "_"):
            break
        end = i + 1
        while i >= 0 and (line[i].isalnum() or line[i] == "_"):
            i -= 1
        start = i + 1
        name = line[start:end]
        if name[0].isdigit():
            break
        chain.append(name)
        while i >= 0 and line[i] in " \t":
            i -= 1
        if i < 0 or line[i] != ".":
            break
    if not chain:
        return None
    chain.reverse()
    return chain


def extract_attribute_base(line: str, col: int) -> str | None:
    """If the cursor is in attribute-completion position (after a
    ``.`` whose left operand is an identifier), return the leftmost
    base identifier. Else ``None``.

    Thin wrapper over :func:`extract_attribute_chain` for callers
    that only need the base name.
    """
    chain = extract_attribute_chain(line, col)
    if chain is None:
        return None
    return chain[0]
