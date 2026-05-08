"""Coordinate-system arithmetic for the LSP server.

Maps AST node positions inside an ``equations = "..."`` block back
to source-file ``(line, col)`` so an editor can place a diagnostic
range on the offending tokens, and maps a file cursor position
back into a logical line + column inside the splitter-cleaned text
so completion and hover handlers can reason about where the cursor
sits.

Three coordinate systems are involved:

1. **Doubly-cleaned text**: the per-line text after both
   :func:`scadwright.component.equations.lex._split_logical_lines`
   and
   :func:`scadwright.component.equations.lex._extract_name_annotations_with_colmap`
   have stripped continuations and ``?``/``:type`` tags. AST nodes
   produced by ``ast.parse(line, mode='eval')`` carry ``col_offset``
   values in this system.
2. **Raw equations text**: the literal contents of the
   ``equations = "..."`` host string, before any cleaning. The unit
   of the splitter's offsets.
3. **Source file**: the user's ``.py`` file, with newlines.

The chain is: doubly-cleaned col → splitter-cleaned col →
raw-equations offset → file ``(line, col)``.

Conventions: 0-based throughout (LSP's convention). Line numbers
in caller-supplied parameters and return values are 0-based; if
the caller is pulling positions from a Python ``ast.AST`` (where
``lineno`` is 1-based) the caller must subtract one before passing
in.

The end-of-range mapping (``is_exclusive_end=True`` on
:func:`map_cleaned_col_to_raw_offset`) treats the input column as
an AST ``end_col_offset`` (exclusive). The result is "one position
past the char at ``cleaned_col - 1``", which keeps highlight
ranges tight around the original tokens rather than reaching into
stripped annotations.
"""

from __future__ import annotations

from dataclasses import dataclass

from scadwright.component.equations import (
    LogicalLine,
    _split_logical_lines,
)
from scadwright.lsp.analyze import EquationsBlock, EquationsHostString


def offset_to_line_col(text: str, offset: int) -> tuple[int, int]:
    """Return ``(line_delta, col)`` for ``text[offset]``.

    ``line_delta`` is the count of ``\\n`` characters in
    ``text[:offset]``. ``col`` is the number of characters since
    the last newline (or the start of ``text`` if there is none).

    ``offset == len(text)`` is allowed (one-past-end is a valid
    range terminator). Raises :class:`ValueError` for negative
    offsets or offsets past the end.
    """
    if offset < 0 or offset > len(text):
        raise ValueError(
            f"offset {offset} out of range for text of length "
            f"{len(text)}"
        )
    line_delta = 0
    col = 0
    for ch in text[:offset]:
        if ch == "\n":
            line_delta += 1
            col = 0
        else:
            col += 1
    return line_delta, col


def map_raw_offset_to_file(
    raw_offset: int,
    *,
    host_text: str,
    host_start_line: int,
    host_start_col: int,
) -> tuple[int, int]:
    """Map a raw-equations offset to file ``(line, col)``.

    ``host_text`` is the raw equations string content (the value
    passed to :func:`_split_logical_lines`).
    ``host_start_line`` and ``host_start_col`` are the file
    position of ``host_text[0]``, both 0-based.

    For a triple-quoted host string the content starts just after
    the opening triple-quote (on the same line, or on the next line
    if the literal opens with ``\\n`` immediately). For a list of
    strings each element has its own host start position. The
    caller's AST walker is responsible for computing the host
    start position correctly.

    Returns 0-based ``(line, col)``.
    """
    line_delta, col_in_line = offset_to_line_col(host_text, raw_offset)
    if line_delta == 0:
        return host_start_line, host_start_col + col_in_line
    return host_start_line + line_delta, col_in_line


def map_cleaned_col_to_raw_offset(
    cleaned_col: int,
    *,
    annotation_colmap: tuple[int, ...],
    line: LogicalLine,
    is_exclusive_end: bool = False,
) -> int:
    """Map a doubly-cleaned column to a raw-equations offset.

    ``cleaned_col`` is a 0-based column in the post-annotation-
    strip line text. ``annotation_colmap`` is the colmap returned
    by
    :func:`scadwright.component.equations.lex._extract_name_annotations_with_colmap`
    on ``line.cleaned``.

    The annotation and splitter layers compose as a chain:
    ``cleaned_col`` is the position of a char in the annotation-
    stripped text; that char came from
    ``line.cleaned[annotation_colmap[cleaned_col]]``; that char in
    turn came from raw position
    ``line.cleaned_to_raw[annotation_colmap[cleaned_col]]``. So:

    - **Inclusive** (start-of-range): single chained lookup
      ``cleaned_to_raw[annotation_colmap[cleaned_col]]``.
    - **Exclusive end**: same chained lookup applied to
      ``cleaned_col - 1`` (the inclusive last-included char), then
      ``+ 1`` once at the raw layer to express "just after that
      raw char". The single ``+ 1`` is correct because both
      layers are linear projections; doubling the +1 would skip
      stripped annotations on the way out.

    Edge cases:

    - ``cleaned_col == 0`` with ``is_exclusive_end=True`` returns
      ``line.raw_start`` (degenerate zero-width range at the start
      — AST nodes never produce this, but the function does not
      raise on it).
    - ``cleaned_col == len(annotation_colmap)`` is allowed and
      treated as one-past-end (collapses to the same exclusive
      formula).
    - Empty cleaned text returns ``line.raw_start`` for any input.
    """
    if cleaned_col < 0:
        raise ValueError(f"cleaned_col {cleaned_col} is negative")
    if cleaned_col > len(annotation_colmap):
        raise ValueError(
            f"cleaned_col {cleaned_col} past end of cleaned text "
            f"(length {len(annotation_colmap)})"
        )
    if not annotation_colmap:
        return line.raw_start

    # Both end-of-range and one-past-end-of-cleaned reduce to the same
    # "raw position one past the char at index K" computation; pick K
    # accordingly.
    one_past_end = (
        is_exclusive_end or cleaned_col == len(annotation_colmap)
    )
    if one_past_end:
        if cleaned_col == 0:
            return line.raw_start
        k = cleaned_col - 1
        return line.cleaned_to_raw[annotation_colmap[k]] + 1
    return line.cleaned_to_raw[annotation_colmap[cleaned_col]]


def map_cleaned_col_to_file(
    cleaned_col: int,
    *,
    annotation_colmap: tuple[int, ...],
    line: LogicalLine,
    host_text: str,
    host_start_line: int,
    host_start_col: int,
    is_exclusive_end: bool = False,
) -> tuple[int, int]:
    """Compose the full chain: doubly-cleaned col → file ``(line, col)``.

    See :func:`map_cleaned_col_to_raw_offset` and
    :func:`map_raw_offset_to_file` for the two halves. This is the
    helper most LSP-side callers will use directly.
    """
    raw_offset = map_cleaned_col_to_raw_offset(
        cleaned_col,
        annotation_colmap=annotation_colmap,
        line=line,
        is_exclusive_end=is_exclusive_end,
    )
    return map_raw_offset_to_file(
        raw_offset,
        host_text=host_text,
        host_start_line=host_start_line,
        host_start_col=host_start_col,
    )


# =============================================================================
# Inverse mapping: file cursor → (host, line, splitter col)
# =============================================================================


@dataclass(frozen=True)
class CursorInBlock:
    """Where a cursor lies inside an equations block.

    ``host_index`` indexes into ``block.hosts``. ``line_index`` is
    the position of the logical line within that host's split (the
    list returned by
    :func:`scadwright.component.equations.lex._split_logical_lines`
    on ``host.raw_text``). ``splitter_col`` is the column in
    ``line.cleaned`` (the splitter-cleaned text — sigils and type
    tags are still present at this layer) where the cursor sits, or
    one past the end (``len(line.cleaned)``) when the cursor is at
    the line's tail.

    Cursors in stripped or whitespace gaps map to the nearest valid
    splitter column rather than ``None``: a user typing ``?`` and
    expecting completion is at the start of an identifier even if
    the ``?`` itself doesn't appear in the cleaned text. Returning
    a position keeps the completion / hover surface alive in those
    common cases.
    """
    host_index: int
    line_index: int
    splitter_col: int


def find_cursor_in_block(
    block: EquationsBlock,
    file_line: int,
    file_col: int,
) -> CursorInBlock | None:
    """Locate a 0-based file ``(line, col)`` cursor within an equations
    block.

    Returns ``None`` when the cursor lies outside every host string
    in the block, or in a region of host text that isn't part of any
    cleaned logical line (leading whitespace before the first line,
    inter-line whitespace between two cleaned lines, or trailing
    whitespace after the last line).
    """
    for host_index, host in enumerate(block.hosts):
        located = _find_cursor_in_host(host, file_line, file_col)
        if located is not None:
            line_index, splitter_col = located
            return CursorInBlock(
                host_index=host_index,
                line_index=line_index,
                splitter_col=splitter_col,
            )
    return None


def _find_cursor_in_host(
    host: EquationsHostString, file_line: int, file_col: int,
) -> tuple[int, int] | None:
    """Map ``(file_line, file_col)`` to ``(line_index, splitter_col)`` in
    one host's logical lines, or return ``None``.

    Association is by physical-line overlap, not strict raw-offset
    containment: a cursor in the leading indent or trailing
    whitespace of a logical line still associates with that line and
    snaps to the nearest cleaned column. A cursor on a blank line
    between two cleaned lines associates with neither.
    """
    raw_offset = _file_to_raw_offset(host, file_line, file_col)
    if raw_offset is None:
        return None
    raw_text = host.raw_text
    physical_line_start = raw_text.rfind("\n", 0, raw_offset) + 1
    next_nl = raw_text.find("\n", raw_offset)
    physical_line_end = (
        len(raw_text) if next_nl == -1 else next_nl
    )
    for line_index, line in enumerate(_split_logical_lines(raw_text)):
        if (
            line.raw_start <= physical_line_end
            and line.raw_end >= physical_line_start
        ):
            splitter_col = _raw_offset_to_splitter_col(line, raw_offset)
            return line_index, splitter_col
    return None


def _file_to_raw_offset(
    host: EquationsHostString, file_line: int, file_col: int,
) -> int | None:
    """Convert a file ``(line, col)`` to an offset in ``host.raw_text``,
    or return ``None`` when the position is outside the host's content.

    The file position is checked against the host's start; once the
    correct line within ``raw_text`` is located, ``file_col`` is
    added and bounds-checked against that line's range.
    """
    line_delta = file_line - host.content_start_line
    if line_delta < 0:
        return None
    if line_delta == 0:
        line_start_in_raw = 0
        col_in_line = file_col - host.content_start_col
        if col_in_line < 0:
            return None
    else:
        line_start_in_raw = 0
        for _ in range(line_delta):
            idx = host.raw_text.find("\n", line_start_in_raw)
            if idx == -1:
                return None
            line_start_in_raw = idx + 1
        col_in_line = file_col
    next_nl = host.raw_text.find("\n", line_start_in_raw)
    line_end_in_raw = (
        len(host.raw_text) if next_nl == -1 else next_nl
    )
    target = line_start_in_raw + col_in_line
    if target < line_start_in_raw or target > line_end_in_raw:
        return None
    return target


def _raw_offset_to_splitter_col(line: LogicalLine, raw_offset: int) -> int:
    """Map a raw offset within a logical line's range back to a column
    in ``line.cleaned``.

    Cursors in whitespace gaps (leading/trailing whitespace stripped
    by the splitter) snap to the nearest valid cleaned column —
    ``0`` for leading-side gaps, ``len(line.cleaned)`` for trailing.
    The cleaned-to-raw array is monotonically increasing because the
    splitter never duplicates raw positions, so a linear search
    finds the matching index.
    """
    cleaned_to_raw = line.cleaned_to_raw
    if not cleaned_to_raw:
        return 0
    if raw_offset <= cleaned_to_raw[0]:
        return 0
    if raw_offset > cleaned_to_raw[-1]:
        return len(line.cleaned)
    for i, ro in enumerate(cleaned_to_raw):
        if ro >= raw_offset:
            return i
    return len(line.cleaned)
