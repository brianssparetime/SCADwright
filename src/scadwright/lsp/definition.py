"""Definition-location resolver for cursor positions in equations text.

Maps a name in an equations block to the source range where the
name was first introduced. The handler in ``server.py`` adapts
the internal :class:`DefinitionLocation` shape into
``lsprotocol.types.Location`` at the LSP boundary.

Resolution order in expression context:

1. Class-declared Params: each :class:`scadwright.lsp.analyze.ParamInfo`
   carries the file range of its ``name = Param(...)`` (or
   ``name: T = Param(...)``) statement.
2. Auto-declared bare-Name targets: the first occurrence anywhere
   in the block. Block-wide rather than cursor-relative because
   the runtime auto-declares targets as Params at class-define
   time, so they're visible to every equation regardless of source
   order.

Curated names (``sin``, ``len``, ``pi``, ...) and unknown names
yield ``None`` — the editor falls back to its normal Python LSP
or shows nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from scadwright.component.equations.lex import _split_logical_lines
from scadwright.lsp.analyze import (
    EquationsBlock,
    auto_declared_origins_in_block,
)
from scadwright.lsp.context import ContextKind
from scadwright.lsp.positions import map_raw_offset_to_file
from scadwright.lsp.resolve import resolve_chain_to_block


@dataclass(frozen=True)
class DefinitionLocation:
    """0-based file range for a definition site.

    Carries no URI — the server adapter combines this with the
    document's URI to produce a full ``lsprotocol.types.Location``.
    """
    start_line: int
    start_col: int
    end_line: int
    end_col: int


def build_definition_location(
    name: str,
    context: ContextKind,
    block: EquationsBlock,
    *,
    attribute_chain: list[str] | None = None,
    sibling_blocks: tuple[EquationsBlock, ...] = (),
) -> DefinitionLocation | None:
    """Find the definition location of ``name`` in ``block``.

    Expression context resolves Params and auto-declared targets.
    Attribute context (``spec.clearances.|``) resolves the dotted
    chain through Param type_text lookups and returns the definition
    of ``name`` in the resolved block. Type-tag, string, and comment
    contexts return ``None``.
    """
    if context == ContextKind.ATTRIBUTE:
        if attribute_chain is not None:
            resolved = resolve_chain_to_block(
                attribute_chain, block, sibling_blocks,
            )
            if resolved is not None:
                return _param_definition(name, resolved)
        return None
    if context != ContextKind.EXPRESSION:
        return None
    param_loc = _param_definition(name, block)
    if param_loc is not None:
        return param_loc
    return _auto_declared_definition(name, block)


def _param_definition(
    name: str, block: EquationsBlock,
) -> DefinitionLocation | None:
    """Return the assignment range for a class-declared Param, or
    ``None`` if no such Param exists or its position info is
    missing (the latter only happens for ParamInfo instances
    constructed outside ``find_equations_blocks``).
    """
    for p in block.params:
        if p.name != name:
            continue
        if (
            p.assign_start_line is None
            or p.assign_start_col is None
            or p.assign_end_line is None
            or p.assign_end_col is None
        ):
            return None
        return DefinitionLocation(
            start_line=p.assign_start_line,
            start_col=p.assign_start_col,
            end_line=p.assign_end_line,
            end_col=p.assign_end_col,
        )
    return None


def _auto_declared_definition(
    name: str, block: EquationsBlock,
) -> DefinitionLocation | None:
    """Return the file range of the logical line where ``name`` first
    appears as a bare-Name equation target, or ``None`` when ``name``
    isn't auto-declared anywhere in the block.

    The range covers the entire offending line — a coarser scope
    than per-token, but that's what the editor centers on for
    goto-definition.
    """
    origins = auto_declared_origins_in_block(block)
    origin = origins.get(name)
    if origin is None:
        return None
    host_index, line_index = origin
    if host_index < 0 or host_index >= len(block.hosts):
        return None
    host = block.hosts[host_index]
    lines = _split_logical_lines(host.raw_text)
    if line_index < 0 or line_index >= len(lines):
        return None
    line = lines[line_index]
    start_line, start_col = map_raw_offset_to_file(
        line.raw_start,
        host_text=host.raw_text,
        host_start_line=host.content_start_line,
        host_start_col=host.content_start_col,
    )
    end_line, end_col = map_raw_offset_to_file(
        line.raw_end,
        host_text=host.raw_text,
        host_start_line=host.content_start_line,
        host_start_col=host.content_start_col,
    )
    return DefinitionLocation(
        start_line=start_line,
        start_col=start_col,
        end_line=end_line,
        end_col=end_col,
    )
