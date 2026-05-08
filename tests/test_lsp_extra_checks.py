"""Tests for the LSP-only static checks layered on top of
``parse_equations_unified``. Currently covers the
undeclared-attribute-base warning.
"""

from __future__ import annotations

from scadwright.lsp.diagnostics import analyze_file


# =============================================================================
# Undeclared-base warnings
# =============================================================================


def test_undeclared_attribute_base_in_equation_warns() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = """\n'
        '    x = b.outer_d\n'
        '    """\n'
    )
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d.severity == "warning"
    assert "b.outer_d" in d.message
    assert "b" in d.message
    assert "Param" in d.message


def test_undeclared_base_diagnostic_hugs_offending_name() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = """\n'
        '    x = b.outer_d\n'
        '    """\n'
    )
    [d] = analyze_file(src)
    src_line = src.splitlines()[d.range.start_line]
    # The diagnostic range covers just the ``b``, not ``b.outer_d``.
    assert src_line[d.range.start_col:d.range.end_col] == "b"


def test_attribute_base_that_is_param_not_warned() -> None:
    src = (
        'class A:\n'
        '    b = Param(B)\n'
        '    equations = "x = b.outer_d"\n'
    )
    assert analyze_file(src) == []


def test_attribute_base_in_constraint_warns() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = """\n'
        '    width > 0\n'
        '    b.outer_d > 5\n'
        '    """\n'
    )
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 1
    assert diagnostics[0].severity == "warning"
    assert "b.outer_d" in diagnostics[0].message


def test_attribute_base_in_adjustment_rhs_warns() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = """\n'
        '    width += b.delta  # adjust\n'
        '    """\n'
    )
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 1
    assert "b.delta" in diagnostics[0].message


def test_multiple_attribute_reads_emit_one_warning_per_occurrence() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = """\n'
        '    x = b.foo + b.bar\n'
        '    """\n'
    )
    diagnostics = analyze_file(src)
    # Two attribute reads → two warnings.
    assert len(diagnostics) == 2
    messages = {d.message for d in diagnostics}
    assert any("b.foo" in m for m in messages)
    assert any("b.bar" in m for m in messages)


def test_auto_declared_target_is_not_treated_as_declared_for_attr_base() -> None:
    # ``b`` appears as an equation target (auto-declared), but the
    # runtime auto-declares it as Param(float) — floats can't have
    # ``.outer_d``, so we still warn statically.
    src = (
        'class A:\n'
        '    equations = """\n'
        '    b = 5\n'
        '    y = b.outer_d\n'
        '    """\n'
    )
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 1
    assert "b.outer_d" in diagnostics[0].message


def test_attribute_chain_only_flags_outer_base() -> None:
    # ``b.foo.bar`` — the AST walker visits two Attribute nodes.
    # The outer ``b.foo.bar`` has value=Attribute (not Name) → skip.
    # The inner ``b.foo`` has value=Name(b) → warn.
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = b.foo.bar"\n'
    )
    diagnostics = analyze_file(src)
    assert len(diagnostics) == 1
    assert "b.foo" in diagnostics[0].message


def test_clean_block_returns_no_diagnostics() -> None:
    # Sanity: a block with no attribute access, no Params referenced
    # outside the class, returns no diagnostics.
    src = (
        'class A:\n'
        '    equations = """\n'
        '    x = 5\n'
        '    y = x * 2\n'
        '    """\n'
    )
    assert analyze_file(src) == []


def test_existing_error_still_takes_precedence_over_warnings() -> None:
    # When the parser raises, we emit the error diagnostic and skip
    # the extra checks entirely. (The parser error makes the parsed
    # block unavailable for further inspection.)
    src = (
        'class A:\n'
        '    equations = """\n'
        '    y = snh(b.outer_d)\n'  # 'snh' is the typo; b is also undeclared
        '    """\n'
    )
    diagnostics = analyze_file(src)
    # Only the parse error fires, not the b.xyz warning.
    assert len(diagnostics) == 1
    assert diagnostics[0].severity == "error"
    assert "snh" in diagnostics[0].message


def test_warning_message_includes_class_prefix() -> None:
    src = (
        'class Bracket:\n'
        '    width = Param(float)\n'
        '    equations = "x = b.outer_d"\n'
    )
    [d] = analyze_file(src)
    assert "Bracket.equations[0]" in d.message
