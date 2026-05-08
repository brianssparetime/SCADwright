"""Document-symbol generator for the LSP outline view.

Given the equations blocks discovered in a file, emit a tree of
``DocumentSymbol`` entries: one ``Class`` symbol per Component
class, with each ``Param`` declaration as a ``Variable`` child.
The handler in ``server.py`` adapts the internal shape into
``lsprotocol.types.DocumentSymbol`` at the LSP boundary.

This module deliberately does *not* surface every class or every
top-level function in the file — the editor's normal Python LSP
(Pyright, Pylance, ruff-lsp, ...) already does that. We surface
only structures that are equations-aware so the outline view
shows the maker their parametric model's shape, not duplicates
of what their language server already provides.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scadwright.lsp.analyze import EquationsBlock


@dataclass(frozen=True)
class DocumentSymbol:
    """Internal LSP-shaped document symbol.

    ``kind`` is a lowercase string ("class" or "variable"); the
    server adapter maps to :class:`lsprotocol.types.SymbolKind`.
    ``range`` is the symbol's full source range (including its
    body for a class). ``selection_range`` is the range the
    editor centers the cursor on when the symbol is activated —
    typically just the name.

    All line / column fields are 0-based.
    """
    name: str
    kind: str
    detail: str | None
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    selection_start_line: int
    selection_start_col: int
    selection_end_line: int
    selection_end_col: int
    children: tuple["DocumentSymbol", ...] = field(default_factory=tuple)


def build_document_symbols(
    blocks: list[EquationsBlock],
) -> list[DocumentSymbol]:
    """Build a flat list of class-level symbols, one per block.

    The list mirrors the source order of the blocks
    (``find_equations_blocks`` already returns them in source
    order). Each class symbol has its Params as children.
    """
    out: list[DocumentSymbol] = []
    for block in blocks:
        symbol = _class_symbol(block)
        if symbol is not None:
            out.append(symbol)
    return out


def _class_symbol(block: EquationsBlock) -> DocumentSymbol | None:
    """Build the ``Class`` symbol for a block, or ``None`` when the
    block is missing class-range info (only happens for blocks
    constructed directly in tests).
    """
    if (
        block.class_start_line is None
        or block.class_start_col is None
        or block.class_end_line is None
        or block.class_end_col is None
    ):
        return None
    name_start = _class_name_start_col(block)
    name_end = name_start + len(block.class_name)
    children = tuple(
        s for s in (_param_symbol(p) for p in block.params) if s is not None
    )
    return DocumentSymbol(
        name=block.class_name,
        kind="class",
        detail=None,
        start_line=block.class_start_line,
        start_col=block.class_start_col,
        end_line=block.class_end_line,
        end_col=block.class_end_col,
        selection_start_line=block.class_start_line,
        selection_start_col=name_start,
        selection_end_line=block.class_start_line,
        selection_end_col=name_end,
        children=children,
    )


def _class_name_start_col(block: EquationsBlock) -> int:
    """Column where the class name begins on its declaration line.

    Computed from ``class_start_col`` (the ``c`` of ``class``) plus
    ``len("class ")``. Only correct when the source uses a single
    space between ``class`` and the name; an unusual layout (extra
    whitespace, comment between keywords) would be slightly off.
    The selection-range guarantee in LSP only requires that the
    range be contained inside the symbol's full range, so a
    pessimistic answer still keeps the outline functional.
    """
    return (block.class_start_col or 0) + len("class ")


def _param_symbol(param) -> DocumentSymbol | None:
    """Build a ``Variable`` symbol for a Param, or ``None`` when the
    Param's assign-position info is missing."""
    if (
        param.assign_start_line is None
        or param.assign_start_col is None
        or param.assign_end_line is None
        or param.assign_end_col is None
    ):
        return None
    name_end_col = param.assign_start_col + len(param.name)
    return DocumentSymbol(
        name=param.name,
        kind="variable",
        detail=param.signature(),
        start_line=param.assign_start_line,
        start_col=param.assign_start_col,
        end_line=param.assign_end_line,
        end_col=param.assign_end_col,
        selection_start_line=param.assign_start_line,
        selection_start_col=param.assign_start_col,
        selection_end_line=param.assign_start_line,
        selection_end_col=name_end_col,
    )
