"""End-to-end tests for ``scadwright.lsp.diagnostics.analyze_file``.

The full pipeline: source text → analyzer → splitter →
``parse_equations_unified`` → ValidationError → file-range
diagnostic. Tests verify that:

- A clean file yields no diagnostics.
- A file with one bad equations block yields one diagnostic with
  the message preserved and the range covering the offending line.
- Multiple blocks (good + bad, multiple bad) yield diagnostics in
  source order.
- A Python syntax error in the surrounding file yields no
  diagnostics (the analyzer can't locate blocks; the editor's
  Python LSP surfaces the syntax error).
- Each major error category surfaces a diagnostic with severity
  "error" and a usable range.
"""

from __future__ import annotations

import pytest

from scadwright.lsp.diagnostics import (
    Diagnostic,
    DiagnosticRange,
    analyze_file,
)


# =============================================================================
# Happy path
# =============================================================================


def test_clean_file_no_diagnostics() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    width = 5\n'
        '    height = 3\n'
        '    """\n'
    )
    assert analyze_file(src) == []


def test_file_without_equations_blocks_no_diagnostics() -> None:
    src = "class A:\n    x = 1\n"
    assert analyze_file(src) == []


def test_file_with_no_classes_no_diagnostics() -> None:
    src = "x = 1\n"
    assert analyze_file(src) == []


def test_python_syntax_error_returns_no_diagnostics() -> None:
    # The Python parser fails before we can locate any equations
    # block. Pyright/Pylance handle the syntax error; we don't.
    src = "class A:\n    equations = \n"
    assert analyze_file(src) == []


# =============================================================================
# Single bad block — error categories
# =============================================================================


def test_chained_equals_produces_diagnostic_with_correct_line() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    x = y = 5\n'
        '    """\n'
    )
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d.severity == "error"
    assert "chained" in d.message.lower() or "more than one top-level" in d.message
    # The "x = y = 5" line is the third line of the file (index 2).
    assert d.range.start_line == 2
    assert d.range.start_col == 4  # leading 4 spaces


def test_unknown_function_produces_diagnostic() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    y = snh(x)\n'
        '    """\n'
    )
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert "snh" in d.message
    assert d.range.start_line == 2


def test_unknown_type_tag_produces_diagnostic() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    ?x:floot = 5\n'
        '    """\n'
    )
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 1
    assert "floot" in diagnostics[0].message


def test_self_referential_equation_produces_diagnostic() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    x = x - 1\n'
        '    """\n'
    )
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 1
    assert "self-referential" in diagnostics[0].message


def test_double_equals_outside_if_produces_diagnostic() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    x == 5\n'
        '    """\n'
    )
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 1
    assert "==" in diagnostics[0].message


def test_walrus_produces_diagnostic() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    x = (y := 5)\n'
        '    """\n'
    )
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 1
    assert "walrus" in diagnostics[0].message


# =============================================================================
# Range arithmetic
# =============================================================================


def test_diagnostic_range_hugs_offending_token_when_node_captured() -> None:
    # ``_check_unknown_function_calls`` captures the callee Name node
    # (``snh``). The diagnostic range covers just that name, not the
    # whole logical line.
    src = (
        'class A:\n'
        '    equations = """\n'
        '    width = 5\n'
        '    y = snh(x)\n'      # the offending line
        '    z = 3\n'
        '    """\n'
    )
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 1
    d = diagnostics[0]
    # "    y = snh(x)" — 4-space indent. y(4) (5) =(6) (7) s(8) n(9) h(10) ((11) ...
    assert d.range.start_line == 3
    assert d.range.start_col == 8  # start of "snh"
    assert d.range.end_line == 3
    assert d.range.end_col == 11  # one past the "h" of "snh"


def test_diagnostic_for_list_form_targets_the_failing_element() -> None:
    src = (
        'class A:\n'
        '    equations = ["x = 1", "y = snh(x)"]\n'
    )
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 1
    d = diagnostics[0]
    # Both elements live on line 1. The offending callee Name (``snh``)
    # in the second element is what the diagnostic range hugs.
    assert d.range.start_line == 1
    src_line = src.splitlines()[1]
    assert src_line[d.range.start_col:d.range.end_col] == "snh"


def test_error_in_third_logical_line_of_one_host() -> None:
    # Exercises within-host source-index mapping: the offending logical
    # line is index 2 in the flattened eq_lines list, and its file
    # position is on the fifth source line.
    src = (
        'class A:\n'
        '    equations = """\n'
        '    width = 5\n'
        '    height = 3\n'
        '    y = snh(x)\n'      # offender — file line 4 (0-based)
        '    """\n'
    )
    [d] = analyze_file(src)
    assert d.range.start_line == 4
    # ``snh`` is the captured Name node. file col = 4-space indent +
    # offset of ``snh`` in the cleaned line "y = snh(x)" (col 4) = 8.
    assert d.range.start_col == 8
    assert d.range.end_col == 11


def test_error_in_first_line_of_second_host_in_list_form() -> None:
    # Exercises cross-host source-index mapping: the offender is the
    # only logical line in the second list element, on a different
    # source line from the first. Its file position must reflect the
    # second host's content_start, not a stale offset from the first.
    src = (
        'class A:\n'
        '    equations = [\n'
        '        "x = 1",\n'
        '        "y = snh(x)",\n'  # offender — file line 3
        '    ]\n'
    )
    [d] = analyze_file(src)
    assert d.range.start_line == 3
    # Second host's content begins at col 9 (8 spaces + opening quote);
    # ``snh`` sits at col 4 within its cleaned text "y = snh(x)" so
    # the diagnostic hugs cols 13-16 in the file.
    assert d.range.start_col == 13
    assert d.range.end_col == 16


def test_adjustment_uniformity_violation_end_to_end() -> None:
    # Adjustments are a real equation form; verify the diagnostics
    # pipeline carries an adjustment-side ValidationError through
    # to a usable file range.
    src = (
        'class A:\n'
        '    equations = """\n'
        '    x += 1  # bump\n'
        '    x *= 2  # scale\n'  # offender — mixes additive and multiplicative
        '    """\n'
    )
    [d] = analyze_file(src)
    assert "adjust" in d.message.lower()
    assert d.range.start_line == 3
    assert d.range.start_col == 4


# =============================================================================
# Multi-block files
# =============================================================================


def test_two_classes_one_bad_one_good_one_diagnostic() -> None:
    src = (
        'class A:\n'
        '    equations = "y = snh(x)"\n'
        '\n'
        'class B:\n'
        '    equations = "x = 1"\n'
    )
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 1
    assert diagnostics[0].range.start_line == 1


def test_two_bad_classes_two_diagnostics_in_source_order() -> None:
    src = (
        'class A:\n'
        '    equations = "y = snh(x)"\n'
        '\n'
        'class B:\n'
        '    equations = "x == 5"\n'
    )
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 2
    assert diagnostics[0].range.start_line < diagnostics[1].range.start_line


def test_class_name_appears_in_message() -> None:
    src = 'class Bracket:\n    equations = "y = snh(x)"\n'
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 1
    assert "Bracket" in diagnostics[0].message


# =============================================================================
# Diagnostic shape sanity
# =============================================================================


def test_diagnostic_default_source_is_scadwright() -> None:
    src = 'class A:\n    equations = "y = snh(x)"\n'
    [d] = analyze_file(src)
    assert d.source == "scadwright"


def test_diagnostic_severity_is_error() -> None:
    src = 'class A:\n    equations = "y = snh(x)"\n'
    [d] = analyze_file(src)
    assert d.severity == "error"


def test_diagnostic_dataclass_is_immutable() -> None:
    d = Diagnostic(
        range=DiagnosticRange(0, 0, 0, 0),
        severity="error",
        message="x",
    )
    with pytest.raises(Exception):
        d.severity = "warning"  # type: ignore[misc]


def test_diagnostic_range_is_half_open() -> None:
    # Sanity: end_col > start_col for a same-line range.
    src = 'class A:\n    equations = "y = snh(x)"\n'
    [d] = analyze_file(src)
    assert d.range.end_line >= d.range.start_line
    if d.range.end_line == d.range.start_line:
        assert d.range.end_col > d.range.start_col


# =============================================================================
# Edge case: empty equations
# =============================================================================


def test_empty_equations_string_no_diagnostic() -> None:
    src = 'class A:\n    equations = ""\n'
    assert analyze_file(src) == []


def test_only_whitespace_equations_no_diagnostic() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '\n'
        '    \n'
        '    """\n'
    )
    assert analyze_file(src) == []


# =============================================================================
# Column-precise ranges across error categories
# =============================================================================


def test_walrus_diagnostic_hugs_named_expr() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    x = (y := 5)\n'
        '    """\n'
    )
    [d] = analyze_file(src)
    src_line = src.splitlines()[d.range.start_line]
    # The captured node is the NamedExpr ``(y := 5)``; AST positions
    # it from ``y`` through just past the ``5``.
    assert src_line[d.range.start_col:d.range.end_col] == "y := 5"


def test_double_equals_diagnostic_hugs_compare() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    x == 5\n'
        '    """\n'
    )
    [d] = analyze_file(src)
    src_line = src.splitlines()[d.range.start_line]
    # ``_check_eq_placement`` captures the whole ``Compare`` node.
    assert src_line[d.range.start_col:d.range.end_col] == "x == 5"


def test_bool_in_arithmetic_diagnostic_hugs_offending_name() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    ?direction:bool or True\n'
        '    y = direction * 2\n'
        '    """\n'
    )
    [d] = analyze_file(src)
    src_line = src.splitlines()[d.range.start_line]
    assert src_line[d.range.start_col:d.range.end_col] == "direction"


def test_chained_equals_falls_back_to_whole_line() -> None:
    # Chained ``=`` is a pre-parse error with no AST node; the
    # diagnostic covers the whole offending line.
    src = (
        'class A:\n'
        '    equations = """\n'
        '    x = y = 5\n'
        '    """\n'
    )
    [d] = analyze_file(src)
    src_line = src.splitlines()[d.range.start_line]
    assert src_line[d.range.start_col:d.range.end_col] == "x = y = 5"


def test_self_referential_falls_back_to_whole_line() -> None:
    # ``_check_self_reference`` captures no node — the whole equation
    # reduces to a contradiction. Whole-line range.
    src = (
        'class A:\n'
        '    equations = """\n'
        '    x = x - 1\n'
        '    """\n'
    )
    [d] = analyze_file(src)
    src_line = src.splitlines()[d.range.start_line]
    assert src_line[d.range.start_col:d.range.end_col] == "x = x - 1"


# =============================================================================
# _node_range fallback behavior
# =============================================================================


def test_node_range_logs_warning_on_out_of_bounds(caplog) -> None:
    # Construct a synthetic ValidationError with an AST node whose
    # col_offset is past the end of its colmap. The diagnostics layer
    # should emit a WARNING and fall back to whole-line.
    import ast
    import logging
    from scadwright.component.equations import LogicalLine
    from scadwright.errors import ValidationError
    from scadwright.lsp.analyze import EquationsHostString
    from scadwright.lsp.diagnostics import _LineOrigin, _diagnostic_from_error

    line = LogicalLine(
        cleaned="x = 5",
        raw_start=0,
        raw_end=5,
        cleaned_to_raw=(0, 1, 2, 3, 4),
        preceding_comment=None,
    )
    host = EquationsHostString(
        raw_text="x = 5", content_start_line=0, content_start_col=0,
    )
    origin = _LineOrigin(host=host, line=line)
    bogus_node = ast.Name(id="x", ctx=ast.Load())
    bogus_node.col_offset = 0
    bogus_node.end_col_offset = 100  # well past the cleaned-line length
    err = ValidationError(
        "test message",
        equations_source_index=0,
        equations_node=bogus_node,
        equations_colmap=(0, 1, 2, 3, 4),
    )
    with caplog.at_level(logging.WARNING, logger="scadwright.lsp.diagnostics"):
        d = _diagnostic_from_error(err, [origin])
    # Whole-line range.
    assert d.range.start_col == 0
    assert d.range.end_col == 5
    # WARNING emitted.
    assert any("out of bounds" in rec.message for rec in caplog.records)


def test_node_range_uses_colmap_from_error_when_available(monkeypatch) -> None:
    # If err.equations_colmap is set, _node_range must use it directly
    # without recomputing via _extract_name_annotations_with_colmap.
    # Sentinel: replace the recompute helper with one that errors so a
    # successful call confirms it wasn't invoked.
    import scadwright.lsp.diagnostics as diag

    def _should_not_be_called(_text: str):
        raise AssertionError("colmap was recomputed despite being attached")

    monkeypatch.setattr(
        diag, "_extract_name_annotations_with_colmap",
        _should_not_be_called,
    )
    src = (
        'class A:\n'
        '    equations = """\n'
        '    y = snh(x)\n'
        '    """\n'
    )
    # Should not raise from the monkey-patched recompute helper because
    # parse_equations_unified attaches the colmap and _diagnostic_from_error
    # uses it.
    [d] = diag.analyze_file(src)
    # Confirms the precise range was computed from the attached colmap.
    src_line = src.splitlines()[d.range.start_line]
    assert src_line[d.range.start_col:d.range.end_col] == "snh"
