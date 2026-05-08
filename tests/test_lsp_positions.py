"""Position-arithmetic tests for the LSP server.

Three layers under test:

- The splitter's per-char raw-offset tracking
  (``_split_logical_lines`` / ``LogicalLine.cleaned_to_raw``).
- The annotation stripper's column map
  (``_extract_name_annotations_with_colmap``).
- The composition helpers in ``scadwright.lsp.positions``.

The diagnostic chain that the analyzer (later step) will use depends on
all three being correct independently AND on their composition. Tests
hammer each layer alone, then compose the layers, then run a few
end-to-end integrations against synthesized AST inputs to confirm the
shape an analyzer would actually feed in produces sane file ranges.
"""

from __future__ import annotations

import ast

import pytest

from scadwright.component.equations.lex import (
    LogicalLine,
    _extract_name_annotations,
    _extract_name_annotations_with_colmap,
    _split_equations_with_comments,
    _split_logical_lines,
)
from scadwright.lsp.analyze import EquationsBlock, EquationsHostString
from scadwright.lsp.positions import (
    CursorInBlock,
    find_cursor_in_block,
    map_cleaned_col_to_file,
    map_cleaned_col_to_raw_offset,
    map_raw_offset_to_file,
    offset_to_line_col,
)


# =============================================================================
# _split_logical_lines: offsets stay aligned with cleaned chars
# =============================================================================


def test_split_simple_two_lines_offsets_identity() -> None:
    text = "x = 1\ny = 2"
    lines = _split_logical_lines(text)
    assert len(lines) == 2
    assert lines[0].cleaned == "x = 1"
    assert lines[0].cleaned_to_raw == (0, 1, 2, 3, 4)
    assert lines[0].raw_start == 0
    assert lines[0].raw_end == 5
    assert lines[1].cleaned == "y = 2"
    # "y" sits at offset 6 in "x = 1\ny = 2".
    assert lines[1].cleaned_to_raw == (6, 7, 8, 9, 10)
    assert lines[1].raw_start == 6
    assert lines[1].raw_end == 11


def test_split_leading_whitespace_stripped_offsets_skip_whitespace() -> None:
    text = "    x = 1"
    lines = _split_logical_lines(text)
    assert lines[0].cleaned == "x = 1"
    # First cleaned char "x" sits at raw offset 4.
    assert lines[0].cleaned_to_raw[0] == 4
    assert lines[0].raw_start == 4
    assert lines[0].raw_end == 9


def test_split_trailing_whitespace_stripped_offsets() -> None:
    text = "x = 1   "
    lines = _split_logical_lines(text)
    assert lines[0].cleaned == "x = 1"
    assert lines[0].raw_end == 5  # last cleaned char "1" at offset 4, +1


def test_split_blank_lines_skipped_no_logical_line_emitted() -> None:
    text = "\n\nx = 1\n\n"
    lines = _split_logical_lines(text)
    assert len(lines) == 1
    assert lines[0].cleaned == "x = 1"
    assert lines[0].cleaned_to_raw[0] == 2  # after the two leading \n


def test_split_whole_line_comment_attached_to_next() -> None:
    text = "# rationale\nx = 1"
    lines = _split_logical_lines(text)
    assert len(lines) == 1
    assert lines[0].cleaned == "x = 1"
    assert lines[0].preceding_comment == "rationale"


def test_split_blank_line_breaks_comment_association() -> None:
    text = "# rationale\n\nx = 1"
    lines = _split_logical_lines(text)
    assert lines[0].preceding_comment is None


def test_split_inline_comment_kept_in_cleaned_with_offsets() -> None:
    text = "x = 1  # why"
    lines = _split_logical_lines(text)
    assert lines[0].cleaned == "x = 1  # why"
    # All chars present; verify a couple of offsets.
    assert lines[0].cleaned_to_raw[0] == 0  # x
    assert lines[0].cleaned_to_raw[7] == 7  # #
    assert lines[0].cleaned_to_raw[-1] == 11  # y


def test_split_backslash_continuation_glues_lines() -> None:
    # "x = 1 +\n  2"  →  "x = 1 +   2" (backslash continuation drops both
    # the `\` and the `\n`; the next line's leading whitespace stays).
    text = "x = 1 +\\\n  2"
    lines = _split_logical_lines(text)
    assert len(lines) == 1
    # cleaned is the strip of "x = 1 +  2", which is the same.
    assert lines[0].cleaned == "x = 1 +  2"
    # The "2" sits at offset 11 in raw text:
    # x(0) (1) =(2) (3) 1(4) (5) +(6) \(7) \n(8) (9) (10) 2(11)
    assert lines[0].cleaned_to_raw[-1] == 11


def test_split_bracket_continuation_newline_becomes_space() -> None:
    text = "f(\n  x,\n  y\n) = 1"
    lines = _split_logical_lines(text)
    assert len(lines) == 1
    # The synthetic spaces that replace the \n take that newline's offset.
    # Find a synthetic-space position by checking the raw text at its
    # mapped offset.
    for cleaned_idx, raw_idx in enumerate(lines[0].cleaned_to_raw):
        if lines[0].cleaned[cleaned_idx] == " " and text[raw_idx] == "\n":
            return  # at least one synthetic space found, well-mapped
    pytest.fail("expected at least one synthetic space mapped to a newline")


def test_split_triple_quoted_string_preserves_inner_offsets() -> None:
    # Equations text containing a literal triple-quoted string with
    # newlines inside. The whole literal lives on one logical line.
    text = 'x = """a\nb"""'
    lines = _split_logical_lines(text)
    assert len(lines) == 1
    # Inner "a" sits at offset 7. cleaned content includes the literal
    # verbatim, so position 7 of the raw text (the "a") should appear.
    raw_a_idx = text.index("a")
    assert raw_a_idx in lines[0].cleaned_to_raw


def test_split_string_literal_with_hash_inside_not_a_comment() -> None:
    text = 'x = "a # b" + 1'
    lines = _split_logical_lines(text)
    assert lines[0].cleaned == 'x = "a # b" + 1'
    # The "#" is at offset 7, kept verbatim with that offset.
    raw_hash = text.index("#")
    assert raw_hash in lines[0].cleaned_to_raw


def test_split_consecutive_comments_closest_wins() -> None:
    text = "# first\n# second\nx = 1"
    lines = _split_logical_lines(text)
    assert lines[0].preceding_comment == "second"


def test_split_unterminated_triple_quote_offsets_remain_sensible() -> None:
    # Mirror the existing un-tracked splitter's tolerance: an unclosed
    # triple-quote shouldn't crash; the partial buffer becomes the line.
    text = 'x = """unterminated'
    lines = _split_logical_lines(text)
    assert len(lines) == 1
    # Offsets cover the full input range.
    assert lines[0].raw_start == 0
    assert lines[0].raw_end == len(text)
    # Each cleaned char's offset is within bounds.
    assert all(0 <= o < len(text) for o in lines[0].cleaned_to_raw)


def test_split_crlf_treated_as_lf_with_cr_kept_in_cleaned() -> None:
    # The splitter recognizes only `\n` as a line break; the `\r` is a
    # regular char that gets right-stripped by the line strip. Verify
    # the offsets still align with the original raw positions.
    text = "x = 1\r\ny = 2"
    lines = _split_logical_lines(text)
    assert len(lines) == 2
    # First line cleans to "x = 1" (the trailing \r is whitespace).
    assert lines[0].cleaned == "x = 1"
    assert lines[0].cleaned_to_raw == (0, 1, 2, 3, 4)
    # Second line "y = 2" starts at offset 7 (after "x = 1\r\n").
    assert lines[1].cleaned == "y = 2"
    assert lines[1].cleaned_to_raw[0] == 7


def test_split_multiple_sigils_on_one_line_offsets_align() -> None:
    text = "?x = ?y + 5"
    lines = _split_logical_lines(text)
    assert lines[0].cleaned == text  # splitter doesn't strip sigils
    cleaned, opt, _, colmap = _extract_name_annotations_with_colmap(
        lines[0].cleaned,
    )
    assert cleaned == "x = y + 5"
    assert opt == {"x", "y"}
    # input: ?(0) x(1) (2) =(3) (4) ?(5) y(6) (7) +(8) (9) 5(10)
    # cleaned: x(1) (2) =(3) (4) y(6) (7) +(8) (9) 5(10)
    assert colmap == (1, 2, 3, 4, 6, 7, 8, 9, 10)


def test_annotation_empty_input_returns_empty_colmap() -> None:
    cleaned, opt, typed, colmap = _extract_name_annotations_with_colmap("")
    assert cleaned == ""
    assert opt == set()
    assert typed == {}
    assert colmap == ()


def test_map_cleaned_col_empty_colmap_returns_raw_start() -> None:
    # Synthesize a degenerate LogicalLine to exercise the empty-colmap
    # path. Real inputs that go through the splitter never produce an
    # empty colmap (a logical line always has at least one cleaned char,
    # otherwise it's dropped). But the helper handles the edge.
    line = LogicalLine(
        cleaned="",
        raw_start=42,
        raw_end=42,
        cleaned_to_raw=(),
        preceding_comment=None,
    )
    assert map_cleaned_col_to_raw_offset(
        0, annotation_colmap=(), line=line,
    ) == 42
    assert map_cleaned_col_to_raw_offset(
        0, annotation_colmap=(), line=line, is_exclusive_end=True,
    ) == 42


def test_split_existing_with_comments_wrapper_unchanged() -> None:
    # The string-only wrapper ``_split_equations_with_comments`` must
    # match the rich function's projection. Existing callers depend
    # on its output shape.
    text = "# why\nx = 1\ny, z = 5"
    rich = _split_logical_lines(text)
    flat = _split_equations_with_comments(text)
    assert len(rich) == len(flat)
    for rline, (cleaned, comment) in zip(rich, flat):
        assert rline.cleaned == cleaned
        assert rline.preceding_comment == comment


# =============================================================================
# _extract_name_annotations_with_colmap: colmap mirrors the cleaned text
# =============================================================================


def test_annotation_no_sigil_colmap_is_identity() -> None:
    cleaned, opt, typed, colmap = _extract_name_annotations_with_colmap("x = 5")
    assert cleaned == "x = 5"
    assert opt == set()
    assert typed == {}
    assert colmap == (0, 1, 2, 3, 4)


def test_annotation_question_sigil_shifts_colmap() -> None:
    cleaned, opt, typed, colmap = _extract_name_annotations_with_colmap("?x = 5")
    assert cleaned == "x = 5"
    assert opt == {"x"}
    assert typed == {}
    # cleaned[0]='x' came from input col 1 (after the stripped '?').
    assert colmap == (1, 2, 3, 4, 5)


def test_annotation_inline_type_tag_jumps_colmap() -> None:
    cleaned, opt, typed, colmap = _extract_name_annotations_with_colmap("x:int = 5")
    assert cleaned == "x = 5"
    assert opt == set()
    assert typed == {"x": "int"}
    # x(0) :(1) i(2) n(3) t(4) (5) =(6) (7) 5(8)
    # cleaned: x(0) (5) =(6) (7) 5(8)
    assert colmap == (0, 5, 6, 7, 8)


def test_annotation_question_plus_type_combined() -> None:
    cleaned, opt, typed, colmap = _extract_name_annotations_with_colmap(
        "?x:int = 5"
    )
    assert cleaned == "x = 5"
    assert opt == {"x"}
    assert typed == {"x": "int"}
    # ?(0) x(1) :(2) i(3) n(4) t(5) (6) =(7) (8) 5(9)
    # cleaned: x(1) (6) =(7) (8) 5(9)
    assert colmap == (1, 6, 7, 8, 9)


def test_annotation_type_tag_with_spaces_around_colon() -> None:
    cleaned, opt, typed, colmap = _extract_name_annotations_with_colmap(
        "x : int = 5"
    )
    assert cleaned == "x = 5"
    assert typed == {"x": "int"}
    # x(0) (1) :(2) (3) i(4) n(5) t(6) (7) =(8) (9) 5(10)
    # cleaned: x(0) (7) =(8) (9) 5(10)
    assert colmap == (0, 7, 8, 9, 10)


def test_annotation_type_tag_inside_brackets_not_recognized() -> None:
    cleaned, opt, typed, colmap = _extract_name_annotations_with_colmap(
        "x[y:5] = 1"
    )
    assert cleaned == "x[y:5] = 1"
    assert typed == {}
    # Identity colmap.
    assert colmap == tuple(range(len("x[y:5] = 1")))


def test_annotation_type_tag_inside_braces_not_recognized() -> None:
    cleaned, opt, typed, colmap = _extract_name_annotations_with_colmap(
        '{a:1, b:2} = m'
    )
    assert cleaned == "{a:1, b:2} = m"
    assert typed == {}


def test_annotation_type_tag_inside_parens_is_recognized() -> None:
    cleaned, opt, typed, colmap = _extract_name_annotations_with_colmap(
        "f(x:int) = 5"
    )
    assert cleaned == "f(x) = 5"
    assert typed == {"x": "int"}


def test_annotation_question_inside_string_not_stripped() -> None:
    cleaned, _, _, colmap = _extract_name_annotations_with_colmap('s = "?x"')
    assert cleaned == 's = "?x"'
    assert colmap == tuple(range(len('s = "?x"')))


def test_annotation_question_inside_comment_not_stripped() -> None:
    cleaned, _, _, colmap = _extract_name_annotations_with_colmap("x = 1  # ?y")
    assert cleaned == "x = 1  # ?y"


def test_annotation_existing_wrapper_drops_colmap_unchanged() -> None:
    cleaned1, opt1, typed1 = _extract_name_annotations("?x:int = 5")
    cleaned2, opt2, typed2, _colmap = _extract_name_annotations_with_colmap(
        "?x:int = 5"
    )
    assert cleaned1 == cleaned2
    assert opt1 == opt2
    assert typed1 == typed2


# =============================================================================
# offset_to_line_col: newline counting
# =============================================================================


def test_offset_to_line_col_zero_in_single_line_returns_zero() -> None:
    assert offset_to_line_col("abc", 0) == (0, 0)


def test_offset_to_line_col_at_newline_position() -> None:
    # "ab\ncd" — offset 2 is the \n. text[:2] = "ab" (no \n). So (0, 2).
    assert offset_to_line_col("ab\ncd", 2) == (0, 2)


def test_offset_to_line_col_right_after_newline() -> None:
    # offset 3 is "c" — first char of line 1.
    assert offset_to_line_col("ab\ncd", 3) == (1, 0)


def test_offset_to_line_col_one_past_end_allowed() -> None:
    assert offset_to_line_col("ab", 2) == (0, 2)


def test_offset_to_line_col_negative_raises() -> None:
    with pytest.raises(ValueError):
        offset_to_line_col("ab", -1)


def test_offset_to_line_col_past_end_raises() -> None:
    with pytest.raises(ValueError):
        offset_to_line_col("ab", 3)


def test_offset_to_line_col_third_line() -> None:
    text = "a\nb\nc"  # offsets: a(0) \n(1) b(2) \n(3) c(4)
    assert offset_to_line_col(text, 4) == (2, 0)


# =============================================================================
# map_raw_offset_to_file: composes line/col with host start
# =============================================================================


def test_map_raw_offset_same_line_as_host_start() -> None:
    # host_text = "x = 1", host starts at file (line=2, col=17) — e.g.,
    # immediately after `equations = """` on line 2.
    line, col = map_raw_offset_to_file(
        0, host_text="x = 1", host_start_line=2, host_start_col=17,
    )
    assert (line, col) == (2, 17)
    line, col = map_raw_offset_to_file(
        4, host_text="x = 1", host_start_line=2, host_start_col=17,
    )
    assert (line, col) == (2, 21)


def test_map_raw_offset_after_newline_resets_col() -> None:
    # After a newline, col is from start of line, not host_start_col.
    line, col = map_raw_offset_to_file(
        6,  # "y" in "x = 1\ny = 2"
        host_text="x = 1\ny = 2",
        host_start_line=2,
        host_start_col=17,
    )
    assert (line, col) == (3, 0)


def test_map_raw_offset_one_past_end_allowed() -> None:
    line, col = map_raw_offset_to_file(
        5,  # one past end of "x = 1"
        host_text="x = 1",
        host_start_line=0,
        host_start_col=0,
    )
    assert (line, col) == (0, 5)


def test_map_raw_offset_into_second_logical_line() -> None:
    line, col = map_raw_offset_to_file(
        8,  # offset of "5" in "x = 1\ny = 5"
        host_text="x = 1\ny = 5",
        host_start_line=10,
        host_start_col=4,
    )
    # text[:8] has one \n; col on that line is 8 - 6 = 2.
    assert (line, col) == (11, 2)


# =============================================================================
# map_cleaned_col_to_raw_offset: handles annotations + splitter together
# =============================================================================


def _line_for(text: str) -> LogicalLine:
    """Helper: split a one-line input and return its single LogicalLine."""
    lines = _split_logical_lines(text)
    assert len(lines) == 1
    return lines[0]


def test_map_cleaned_col_inclusive_no_annotations() -> None:
    line = _line_for("x = 5")
    cleaned, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    assert cleaned == "x = 5"
    # cleaned col 0 → raw 0 (the 'x').
    assert map_cleaned_col_to_raw_offset(
        0, annotation_colmap=colmap, line=line,
    ) == 0
    # cleaned col 4 → raw 4 (the '5').
    assert map_cleaned_col_to_raw_offset(
        4, annotation_colmap=colmap, line=line,
    ) == 4


def test_map_cleaned_col_inclusive_with_question_sigil() -> None:
    # "?x = 5" — splitter cleaned (after strip) is "?x = 5"; annotation
    # cleaned is "x = 5" with colmap (1, 2, 3, 4, 5).
    line = _line_for("?x = 5")
    _, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    # cleaned col 0 ("x" in "x = 5") → raw col 1 in line.cleaned →
    # raw offset 1 in original text.
    assert map_cleaned_col_to_raw_offset(
        0, annotation_colmap=colmap, line=line,
    ) == 1


def test_map_cleaned_col_inclusive_with_type_tag() -> None:
    # "x:int = 5" — annotation cleaned is "x = 5" with colmap (0, 5, 6, 7, 8).
    line = _line_for("x:int = 5")
    _, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    # cleaned col 1 (the space after "x" in cleaned) → raw col 5.
    assert map_cleaned_col_to_raw_offset(
        1, annotation_colmap=colmap, line=line,
    ) == 5


def test_map_cleaned_col_one_past_end_inclusive() -> None:
    line = _line_for("x = 5")
    _, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    # cleaned col 5 (one past end of "x = 5") → raw col 5.
    assert map_cleaned_col_to_raw_offset(
        5, annotation_colmap=colmap, line=line,
    ) == 5


def test_map_cleaned_col_negative_raises() -> None:
    line = _line_for("x = 5")
    _, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    with pytest.raises(ValueError):
        map_cleaned_col_to_raw_offset(
            -1, annotation_colmap=colmap, line=line,
        )


def test_map_cleaned_col_past_end_raises() -> None:
    line = _line_for("x = 5")
    _, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    with pytest.raises(ValueError):
        map_cleaned_col_to_raw_offset(
            6, annotation_colmap=colmap, line=line,
        )


def test_map_cleaned_col_exclusive_end_hugs_previous_char() -> None:
    # "?x = 5" → cleaned "x = 5". The AST node Name(x) has col_offset=0,
    # end_col_offset=1. Mapping end col 1 with is_exclusive_end=True
    # should land at "one past x's raw position" = raw 2 (just after x
    # in "?x = 5"), NOT raw 2 because annotation_colmap[1]=2 is the
    # space — happens to be the same here. Test with type-tag where
    # colmap jumps.
    line = _line_for("?x:int = 5")
    _, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    # Cleaned "x = 5". Name(x) end_col=1. Inclusive map of 1 would jump
    # over ":int " to col 6. Exclusive should hug — one past x's raw
    # position. x is at raw 1; one past = 2.
    inclusive = map_cleaned_col_to_raw_offset(
        1, annotation_colmap=colmap, line=line,
    )
    exclusive = map_cleaned_col_to_raw_offset(
        1, annotation_colmap=colmap, line=line, is_exclusive_end=True,
    )
    assert inclusive != exclusive
    assert exclusive == 2  # one past the "x" at raw position 1


def test_map_cleaned_col_exclusive_end_one_past_end() -> None:
    line = _line_for("?x = 5")
    _, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    # Range covering the whole cleaned text "x = 5": end_col = 5.
    # Should land at raw 6 (one past the last char "5" at raw position 5).
    end = map_cleaned_col_to_raw_offset(
        5, annotation_colmap=colmap, line=line, is_exclusive_end=True,
    )
    assert end == 6


def test_map_cleaned_col_exclusive_end_zero_returns_raw_start() -> None:
    line = _line_for("    x = 5")  # leading whitespace; raw_start = 4
    _, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    end = map_cleaned_col_to_raw_offset(
        0, annotation_colmap=colmap, line=line, is_exclusive_end=True,
    )
    assert end == line.raw_start == 4


# =============================================================================
# map_cleaned_col_to_file: full chain
# =============================================================================


def test_full_chain_simple_single_line_block() -> None:
    # Equations text: just "x = 5". Host starts at file (line=2, col=17).
    host_text = "x = 5"
    line = _line_for(host_text)
    cleaned, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    # Map cleaned col 0 ("x") to file. Should be (2, 17).
    assert map_cleaned_col_to_file(
        0,
        annotation_colmap=colmap, line=line,
        host_text=host_text, host_start_line=2, host_start_col=17,
    ) == (2, 17)
    # Map cleaned col 4 ("5") to file. (2, 21).
    assert map_cleaned_col_to_file(
        4,
        annotation_colmap=colmap, line=line,
        host_text=host_text, host_start_line=2, host_start_col=17,
    ) == (2, 21)


def test_full_chain_multi_line_block_second_line() -> None:
    host_text = "x = 1\ny = 2"
    lines = _split_logical_lines(host_text)
    second = lines[1]
    _, _, _, colmap = _extract_name_annotations_with_colmap(second.cleaned)
    # Second line "y = 2" is on file line host_start_line + 1, col 0
    # (because the \n in host_text resets col).
    assert map_cleaned_col_to_file(
        0,
        annotation_colmap=colmap, line=second,
        host_text=host_text, host_start_line=2, host_start_col=17,
    ) == (3, 0)


def test_full_chain_with_question_sigil_adjusts_for_strip() -> None:
    host_text = "?x = 5"
    line = _line_for(host_text)
    _, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    # Cleaned text is "x = 5". cleaned col 0 = "x" — should map to file
    # col host_start_col + 1 (the original "?" was stripped).
    file_line, file_col = map_cleaned_col_to_file(
        0,
        annotation_colmap=colmap, line=line,
        host_text=host_text, host_start_line=10, host_start_col=4,
    )
    assert (file_line, file_col) == (10, 5)


def test_full_chain_with_type_tag_adjusts() -> None:
    host_text = "x:int = 5"
    line = _line_for(host_text)
    _, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    # Cleaned "x = 5". cleaned col 2 (the "=") — should map to file col
    # corresponding to original "=" position.
    file_line, file_col = map_cleaned_col_to_file(
        2,
        annotation_colmap=colmap, line=line,
        host_text=host_text, host_start_line=0, host_start_col=0,
    )
    # Original: x(0) :(1) i(2) n(3) t(4) (5) =(6) (7) 5(8). "=" at col 6.
    assert (file_line, file_col) == (0, 6)


def test_full_chain_ast_name_range_round_trip() -> None:
    # Realistic flow: parse the cleaned text as a Python expression, take
    # an AST Name's col_offset / end_col_offset, and map both to file
    # positions. The squiggle should hug the original "x" exactly.
    host_text = "?x:int = 5"
    line = _line_for(host_text)
    cleaned, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    # cleaned = "x = 5". Parse as an expression — but it's an assignment
    # at top level so we need ``mode='exec'`` and dig in. Easier: parse
    # only the LHS.
    tree = ast.parse("x", mode="eval")
    name_node = tree.body
    assert isinstance(name_node, ast.Name)
    assert name_node.col_offset == 0
    assert name_node.end_col_offset == 1
    # Map both ends.
    start = map_cleaned_col_to_file(
        name_node.col_offset,
        annotation_colmap=colmap, line=line,
        host_text=host_text, host_start_line=5, host_start_col=20,
    )
    end = map_cleaned_col_to_file(
        name_node.end_col_offset,
        annotation_colmap=colmap, line=line,
        host_text=host_text, host_start_line=5, host_start_col=20,
        is_exclusive_end=True,
    )
    # Original position of "x" in host_text: col 1 (after the "?"). File
    # col = host_start_col + 1 = 21. End: just past the "x" = 22.
    assert start == (5, 21)
    assert end == (5, 22)


def test_full_chain_bracket_continuation_crosses_newline() -> None:
    # Host text uses bracket continuation: f(\n  x) = 1. The arg "x"
    # on the second line should map to file_line + 1 with col reset.
    host_text = "f(\n  x) = 1"
    line = _line_for(host_text)
    _, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    # Find the "x" in cleaned. After splitter, \n becomes space; cleaned
    # is "f(   x) = 1" — wait, leading whitespace of next raw line is
    # preserved as part of buf. So cleaned = "f( " + "  x) = 1" =
    # "f(   x) = 1" (with the synthetic space + "  " from the next line).
    # Locate "x" by index.
    x_in_cleaned = line.cleaned.index("x")
    # In the doubly-cleaned text it's at the same column (no annotations).
    file_line, file_col = map_cleaned_col_to_file(
        x_in_cleaned,
        annotation_colmap=colmap, line=line,
        host_text=host_text, host_start_line=0, host_start_col=0,
    )
    # Original "x" sits at host_text offset = position of "x" in raw,
    # which is on the second line at col 2.
    assert file_line == 1
    assert file_col == 2


def test_full_chain_two_line_block_with_indent() -> None:
    # User equations text typed inside a triple-quote at indent 4:
    # equations = """
    #     x = 1
    #     y = x + 2
    # """
    # The host_text is the inside of the triple-quote (everything after
    # the leading newline). We strip the leading "\n    " mentally and
    # treat host_start_(line, col) as the position of the first content
    # char, which depends on how the analyzer locates the host.
    host_text = "    x = 1\n    y = x + 2\n    "
    lines = _split_logical_lines(host_text)
    assert len(lines) == 2
    # First logical line "x = 1": leading whitespace stripped, raw_start
    # is the offset of "x" in host_text.
    assert host_text[lines[0].raw_start] == "x"
    _, _, _, colmap = _extract_name_annotations_with_colmap(lines[0].cleaned)
    # If host_start_line=2 col=0 and the "    x" has a leading 4-space
    # indent in raw, the "x" is at file (2, 4).
    file_line, file_col = map_cleaned_col_to_file(
        0,
        annotation_colmap=colmap, line=lines[0],
        host_text=host_text, host_start_line=2, host_start_col=0,
    )
    assert (file_line, file_col) == (2, 4)
    # Second logical line "y = x + 2" — its first cleaned char "y" is on
    # raw line 1 (after one \n) at col 4.
    _, _, _, colmap2 = _extract_name_annotations_with_colmap(lines[1].cleaned)
    file_line2, file_col2 = map_cleaned_col_to_file(
        0,
        annotation_colmap=colmap2, line=lines[1],
        host_text=host_text, host_start_line=2, host_start_col=0,
    )
    assert (file_line2, file_col2) == (3, 4)


def test_full_chain_inline_comment_does_not_offset() -> None:
    host_text = "x = 5  # rationale"
    line = _line_for(host_text)
    _, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    # cleaned is "x = 5  # rationale" (no annotations to strip).
    # Map cleaned col 4 ("5") to file: (0, 4).
    assert map_cleaned_col_to_file(
        4,
        annotation_colmap=colmap, line=line,
        host_text=host_text, host_start_line=0, host_start_col=0,
    ) == (0, 4)


def test_full_chain_ast_binop_spans_correct_range() -> None:
    # Realistic: parse "y = x + 2" and extract the BinOp's range.
    host_text = "?y:int = ?x + 2"
    line = _line_for(host_text)
    cleaned, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    assert cleaned == "y = x + 2"
    # Parse the RHS. We split on '=' first.
    tree = ast.parse("x + 2", mode="eval")
    binop = tree.body
    assert isinstance(binop, ast.BinOp)
    # In "x + 2", x is at col 0, the BinOp's end_col_offset is 5.
    assert binop.col_offset == 0
    assert binop.end_col_offset == 5
    # But the cleaned text we built positions starts at "y = ", so the
    # rhs starts at cleaned col 4 in the joined cleaned text. For this
    # test we'll exercise the start of the RHS by offsetting.
    rhs_start_in_cleaned = cleaned.index("x")
    rhs_end_in_cleaned = rhs_start_in_cleaned + binop.end_col_offset
    start = map_cleaned_col_to_file(
        rhs_start_in_cleaned,
        annotation_colmap=colmap, line=line,
        host_text=host_text, host_start_line=0, host_start_col=0,
    )
    end = map_cleaned_col_to_file(
        rhs_end_in_cleaned,
        annotation_colmap=colmap, line=line,
        host_text=host_text, host_start_line=0, host_start_col=0,
        is_exclusive_end=True,
    )
    # Host_text: ?(0) y(1) :(2) i(3) n(4) t(5) (6) =(7) (8) ?(9) x(10) (11) +(12) (13) 2(14)
    # x at raw col 10. End of "x + 2" exclusive: raw col 15.
    assert start == (0, 10)
    assert end == (0, 15)


# =============================================================================
# Inverse mapping: file cursor → block / line / splitter col
# =============================================================================


def _make_block(hosts: list[EquationsHostString]) -> EquationsBlock:
    return EquationsBlock(
        class_name="T",
        hosts=tuple(hosts),
        param_names=frozenset(),
    )


def test_find_cursor_single_line_host_returns_correct_splitter_col() -> None:
    # Host: equations = "x = 5" content begins at file (0, 17).
    host = EquationsHostString(
        raw_text="x = 5",
        content_start_line=0,
        content_start_col=17,
    )
    block = _make_block([host])
    # Cursor on the "=" — file col 19 (= 17 + 2).
    cursor = find_cursor_in_block(block, 0, 19)
    assert cursor == CursorInBlock(host_index=0, line_index=0, splitter_col=2)


def test_find_cursor_at_end_of_line_returns_one_past_end() -> None:
    host = EquationsHostString(
        raw_text="x = 5", content_start_line=0, content_start_col=17,
    )
    block = _make_block([host])
    # Cursor just past the "5" — file col 22.
    cursor = find_cursor_in_block(block, 0, 22)
    assert cursor is not None
    assert cursor.splitter_col == len("x = 5")


def test_find_cursor_before_host_returns_none() -> None:
    host = EquationsHostString(
        raw_text="x = 5", content_start_line=0, content_start_col=17,
    )
    block = _make_block([host])
    assert find_cursor_in_block(block, 0, 5) is None  # before content_start_col
    assert find_cursor_in_block(block, -1, 0) is None  # before content_start_line
    # File line later than the host's only line.
    assert find_cursor_in_block(block, 5, 0) is None


def test_find_cursor_after_line_end_returns_none() -> None:
    host = EquationsHostString(
        raw_text="x = 5", content_start_line=0, content_start_col=17,
    )
    block = _make_block([host])
    # Cursor past "x = 5" by several columns.
    assert find_cursor_in_block(block, 0, 50) is None


def test_find_cursor_multiline_host_each_line() -> None:
    # equations = """
    # width = 5
    # height = 3
    # """ — content begins at file (1, 19), raw_text starts with `\n`.
    raw = "\n    width = 5\n    height = 3\n    "
    host = EquationsHostString(
        raw_text=raw, content_start_line=1, content_start_col=19,
    )
    block = _make_block([host])
    # Cursor on the "w" in "width" — file (2, 4).
    c = find_cursor_in_block(block, 2, 4)
    assert c is not None
    assert c.line_index == 0
    assert c.splitter_col == 0  # cleaned line is "width = 5", "w" is col 0
    # Cursor on the "=" in "height = 3" — file (3, 11).
    c = find_cursor_in_block(block, 3, 11)
    assert c is not None
    assert c.line_index == 1
    assert c.splitter_col == 7  # "height = 3" — col 7 is "="


def test_find_cursor_in_leading_whitespace_snaps_to_col_0() -> None:
    # Cursor in the indent before "width" — file (2, 1) inside "    width = 5".
    raw = "\n    width = 5\n    "
    host = EquationsHostString(
        raw_text=raw, content_start_line=1, content_start_col=19,
    )
    block = _make_block([host])
    cursor = find_cursor_in_block(block, 2, 1)
    assert cursor is not None
    assert cursor.line_index == 0
    assert cursor.splitter_col == 0  # snaps to start of cleaned line


def test_find_cursor_list_form_first_vs_second_element() -> None:
    # equations = ["x = 1", "y = 2"] — two hosts on file line 1.
    h0 = EquationsHostString(
        raw_text="x = 1", content_start_line=1, content_start_col=18,
    )
    h1 = EquationsHostString(
        raw_text="y = 2", content_start_line=1, content_start_col=27,
    )
    block = _make_block([h0, h1])
    # Cursor on "x" in first host.
    c = find_cursor_in_block(block, 1, 18)
    assert c is not None and c.host_index == 0
    # Cursor on "y" in second host.
    c = find_cursor_in_block(block, 1, 27)
    assert c is not None and c.host_index == 1
    # Cursor between hosts (in the `, ` separator) — outside both.
    assert find_cursor_in_block(block, 1, 24) is None


def test_find_cursor_inside_question_sigil_position() -> None:
    # Host: "?x = 5". The cursor on the "?" itself doesn't appear in
    # the cleaned-cleaned text (sigil stripped), but the splitter
    # cleaned still shows it. Splitter col 0 is the "?".
    host = EquationsHostString(
        raw_text="?x = 5", content_start_line=0, content_start_col=0,
    )
    block = _make_block([host])
    cursor = find_cursor_in_block(block, 0, 0)
    assert cursor is not None
    assert cursor.splitter_col == 0


def test_find_cursor_multiline_host_intermediate_blank_no_match() -> None:
    # Triple-quoted with a blank line between two equations. Cursor on
    # the blank line should fall outside any logical line.
    raw = "\n    x = 1\n\n    y = 2\n    "
    host = EquationsHostString(
        raw_text=raw, content_start_line=1, content_start_col=19,
    )
    block = _make_block([host])
    # Cursor on the blank line — file line 3 (0-based: 1 host start, 2 first eq, 3 blank, 4 second eq).
    assert find_cursor_in_block(block, 3, 0) is None


def test_find_cursor_round_trip_against_forward_map() -> None:
    # Property-style: pick several cleaned-line columns, forward-map
    # to file (line, col) via map_cleaned_col_to_file, inverse-map
    # back via find_cursor_in_block, and verify the result lands on
    # the expected splitter_col (not always the original cleaned_col,
    # because the inverse returns splitter coords; reproduce the
    # forward chain to compare).
    host_text = "?x:int = 5"
    host = EquationsHostString(
        raw_text=host_text, content_start_line=0, content_start_col=10,
    )
    block = _make_block([host])
    line = _split_logical_lines(host_text)[0]
    cleaned, _, _, colmap = _extract_name_annotations_with_colmap(line.cleaned)
    # For each cleaned-col, forward-map to file then inverse-map.
    for cleaned_col in range(len(cleaned)):
        # Expected splitter_col = colmap[cleaned_col].
        expected_splitter_col = colmap[cleaned_col]
        file_pos = map_cleaned_col_to_file(
            cleaned_col,
            annotation_colmap=colmap, line=line,
            host_text=host_text, host_start_line=0, host_start_col=10,
        )
        cursor = find_cursor_in_block(block, file_pos[0], file_pos[1])
        assert cursor is not None
        assert cursor.host_index == 0
        assert cursor.line_index == 0
        assert cursor.splitter_col == expected_splitter_col
