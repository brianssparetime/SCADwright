"""Tests for the LSP document-symbol generator.

Verifies the outline tree shape — one Class symbol per
equations-bearing class, with each Param declaration as a
Variable child — plus range computation for the class header
and Param assignments.
"""

from __future__ import annotations

from scadwright.lsp.analyze import find_equations_blocks
from scadwright.lsp.symbols import (
    DocumentSymbol,
    build_document_symbols,
)


def _symbols(src: str) -> list[DocumentSymbol]:
    return build_document_symbols(find_equations_blocks(src))


def test_class_with_no_params_emits_class_with_no_children() -> None:
    src = (
        'class A:\n'
        '    equations = "x = 1"\n'
    )
    [sym] = _symbols(src)
    assert sym.name == "A"
    assert sym.kind == "class"
    assert sym.children == ()


def test_class_with_one_param_emits_one_child() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    [cls_sym] = _symbols(src)
    assert cls_sym.name == "A"
    assert len(cls_sym.children) == 1
    [child] = cls_sym.children
    assert child.name == "width"
    assert child.kind == "variable"
    assert child.detail == "Param(float)"


def test_multiple_params_appear_in_source_order() -> None:
    src = (
        'class A:\n'
        '    height = Param(float)\n'
        '    width = Param(float)\n'
        '    depth = Param(float)\n'
        '    equations = "x = width"\n'
    )
    [cls_sym] = _symbols(src)
    assert [c.name for c in cls_sym.children] == [
        "height", "width", "depth",
    ]


def test_multiple_classes_emit_multiple_symbols() -> None:
    src = (
        'class A:\n'
        '    a = Param(float)\n'
        '    equations = "x = a"\n'
        '\n'
        'class B:\n'
        '    b = Param(float)\n'
        '    equations = "y = b"\n'
    )
    syms = _symbols(src)
    assert [s.name for s in syms] == ["A", "B"]


def test_class_without_equations_is_not_emitted() -> None:
    # The editor's regular Python LSP already shows plain classes;
    # we only surface ones that have an equations block.
    src = (
        'class Plain:\n'
        '    x = 1\n'
        '\n'
        'class WithEquations:\n'
        '    equations = "x = 1"\n'
    )
    syms = _symbols(src)
    assert [s.name for s in syms] == ["WithEquations"]


def test_no_classes_returns_empty() -> None:
    assert _symbols("x = 1\n") == []


def test_class_range_covers_class_through_body() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    [cls_sym] = _symbols(src)
    # ``class A:`` is on file line 0.
    assert cls_sym.start_line == 0
    assert cls_sym.start_col == 0
    # End line is the last line of the body (``equations`` line).
    assert cls_sym.end_line == 2


def test_class_selection_range_covers_just_the_name() -> None:
    src = (
        'class Bracket:\n'
        '    equations = "x = 1"\n'
    )
    [cls_sym] = _symbols(src)
    assert cls_sym.selection_start_line == 0
    # ``class `` is 6 chars; the name starts at col 6.
    assert cls_sym.selection_start_col == 6
    assert cls_sym.selection_end_col == 6 + len("Bracket")


def test_param_range_covers_assignment_statement() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    [cls_sym] = _symbols(src)
    [child] = cls_sym.children
    assert child.start_line == 1
    assert child.start_col == 4
    src_line = src.splitlines()[1]
    assert (
        src_line[child.start_col:child.end_col]
        == "width = Param(float)"
    )


def test_param_selection_range_covers_just_the_name() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    [cls_sym] = _symbols(src)
    [child] = cls_sym.children
    assert child.selection_start_line == 1
    assert child.selection_start_col == 4
    assert child.selection_end_col == 4 + len("width")


def test_param_detail_uses_signature() -> None:
    src = (
        'class A:\n'
        '    width = Param(float, default=5, doc="The width")\n'
        '    equations = "x = width"\n'
    )
    [cls_sym] = _symbols(src)
    [child] = cls_sym.children
    # ``doc=`` is intentionally omitted from the signature; doc text
    # surfaces in hover, not the outline detail.
    assert child.detail == "Param(float, default=5)"


def test_nested_classes_appear_at_top_level() -> None:
    # Nested ``class Inner:`` with its own equations block produces a
    # separate top-level entry rather than being nested as a child of
    # ``Outer``. LSP accepts both shapes; this test pins the current
    # flat output so a future change to true hierarchical nesting is
    # deliberate, not accidental.
    src = (
        'class Outer:\n'
        '    equations = "x = 1"\n'
        '\n'
        '    class Inner:\n'
        '        equations = "y = 2"\n'
    )
    syms = _symbols(src)
    assert {s.name for s in syms} == {"Outer", "Inner"}
    assert len(syms) == 2
