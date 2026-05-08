"""LSP-shaped diagnostic generation from equations validation.

Walks every equations block in a Python source file and runs the
class-define-time validators on each. A raised ``ValidationError``
becomes a ``Diagnostic`` whose range covers either the offending
AST sub-node (when the validator captured one and the position
chain maps cleanly) or the entire offending logical line (the
fallback).

Range-tightening uses ``ValidationError.equations_node``: a
captured node carries ``col_offset`` and ``end_col_offset``
relative to the *cleaned* equation line (``_parse_expr`` shifts
nodes from the substring it parsed up to the cleaned-line
coordinate system). Those columns are mapped through the
annotation-strip colmap and the splitter's ``cleaned_to_raw``
array to a file ``(line, col)`` range. Pre-parse errors and
system-wide errors (mutual inconsistency, adjustment uniformity)
have no node and fall back to whole-line highlights.

``parse_equations_unified`` raises on the first error per
equations block, so each block contributes at most one diagnostic.
Multiple failing blocks in one file produce multiple diagnostics
in source order.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass

from scadwright.component.equations import (
    LogicalLine,
    _extract_name_annotations_with_colmap,
    _split_logical_lines,
)
from scadwright.component.resolver import parse_equations_unified
from scadwright.errors import ValidationError
from scadwright.lsp.analyze import (
    EquationsBlock,
    EquationsHostString,
    find_equations_blocks,
)
from scadwright.lsp.positions import (
    map_cleaned_col_to_file,
    map_raw_offset_to_file,
)


_SOURCE_NAME = "scadwright"
_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiagnosticRange:
    """A 0-based half-open range in source-file coordinates.

    ``start_line`` / ``start_col`` are inclusive; ``end_line`` /
    ``end_col`` are exclusive. Matches the LSP convention so a
    pygls adaptor can copy the four ints directly into a
    ``lsprotocol`` ``Range``.
    """
    start_line: int
    start_col: int
    end_line: int
    end_col: int


@dataclass(frozen=True)
class Diagnostic:
    """An LSP-shaped diagnostic for an equations validation error.

    ``severity`` is the LSP severity name as a lowercase string
    (``"error"``, ``"warning"``, ``"info"``, ``"hint"``).
    ``source`` defaults to ``"scadwright"`` so editors group these
    diagnostics together regardless of which language server
    emitted them.
    """
    range: DiagnosticRange
    severity: str
    message: str
    source: str = _SOURCE_NAME


def analyze_file(source_text: str) -> list[Diagnostic]:
    """Run equations validators against ``source_text``.

    Returns diagnostics in source order: one error per block that
    fails validation, plus any warning diagnostics produced by the
    LSP-only static checks (currently the undeclared-attribute-base
    check) for blocks that pass validation. A clean file returns
    ``[]``. A file whose Python syntax doesn't parse also returns
    ``[]`` (the analyzer cannot locate equations blocks in
    unparseable text; the editor's Python LSP — Pyright/Pylance —
    surfaces the syntax error).
    """
    out: list[Diagnostic] = []
    for block in find_equations_blocks(source_text):
        out.extend(_diagnose_block(block))
    return out


@dataclass(frozen=True)
class _LineOrigin:
    """Bookkeeping tying a flat eq-line index back to its host."""
    host: EquationsHostString
    line: LogicalLine


def _flatten_block(block: EquationsBlock) -> tuple[list[str], list[_LineOrigin]]:
    """Mirror the runtime's flattening of ``equations`` into one list.

    Returns parallel sequences: the cleaned equation-line strings
    that feed ``parse_equations_unified``, and per-line origin
    metadata used to map a ``source_index`` back to a file range.
    """
    lines: list[str] = []
    origins: list[_LineOrigin] = []
    for host in block.hosts:
        for line in _split_logical_lines(host.raw_text):
            lines.append(line.cleaned)
            origins.append(_LineOrigin(host=host, line=line))
    return lines, origins


def _diagnose_block(block: EquationsBlock) -> list[Diagnostic]:
    """Run validators on one block. Returns the error diagnostic when
    validation fails, or any warning diagnostics from the LSP-only
    static checks when validation succeeds. Empty for blocks with no
    equation lines (e.g., ``equations = ""``).
    """
    eq_lines, origins = _flatten_block(block)
    if not eq_lines:
        return []
    try:
        parsed = parse_equations_unified(
            eq_lines, class_name=block.class_name,
        )
    except ValidationError as err:
        return [_diagnostic_from_error(err, origins)]
    equations, constraints, _, _, adjustments = parsed
    # Deferred import: extra_checks imports back from this module
    # (reuses Diagnostic / DiagnosticRange / _LineOrigin), so a
    # module-level import here would cycle.
    from scadwright.lsp.extra_checks import find_undeclared_attribute_bases
    return find_undeclared_attribute_bases(
        block, equations, constraints, adjustments, origins,
    )


def _diagnostic_from_error(
    err: ValidationError, origins: list[_LineOrigin],
) -> Diagnostic:
    """Convert a raised ``ValidationError`` into an LSP diagnostic."""
    idx = err.equations_source_index
    if idx is None or not (0 <= idx < len(origins)):
        # Defensive fallback. Every equations-side raise sets the
        # source index; a zero-width diagnostic at the file origin
        # keeps the editor surface responsive even if a particular
        # raise site does not.
        return Diagnostic(
            range=DiagnosticRange(0, 0, 0, 0),
            severity="error",
            message=str(err),
        )
    origin = origins[idx]
    colmap = err.equations_colmap
    if colmap is None:
        # ``parse_equations_unified`` always populates ``equations_colmap``.
        # Recompute defensively if a future raise path skips it.
        _, _, _, colmap = _extract_name_annotations_with_colmap(
            origin.line.cleaned,
        )
    range_ = _node_range(err.equations_node, origin, colmap)
    if range_ is None:
        range_ = _whole_line_range(origin)
    return Diagnostic(
        range=range_,
        severity="error",
        message=str(err),
    )


def _node_range(
    node: ast.AST | None,
    origin: _LineOrigin,
    colmap: tuple[int, ...],
) -> DiagnosticRange | None:
    """File-position range covering a captured AST node, or ``None`` to
    fall back to whole-line.

    Reads ``col_offset`` and ``end_col_offset`` (in cleaned-line
    coordinates after :func:`_parse_expr`'s offset shift) and maps
    them through the annotation ``colmap`` plus the logical line's
    raw-offset map to a file range. Returns ``None`` when the node
    has no position info, when the columns are out of bounds for
    the cleaned line, or when any chained lookup raises — the
    caller substitutes a whole-line range so the user still sees a
    diagnostic. Bounds and chain failures are logged at WARNING so
    the fallback isn't silent.
    """
    if node is None:
        return None
    col = getattr(node, "col_offset", None)
    end_col = getattr(node, "end_col_offset", None)
    if col is None or end_col is None:
        return None
    if not colmap:
        return None
    if col < 0 or end_col < col or end_col > len(colmap):
        _log.warning(
            "scadwright LSP: AST node range out of bounds for "
            "cleaned line %r — col=%d end_col=%d colmap_len=%d. "
            "Falling back to whole-line.",
            origin.line.cleaned, col, end_col, len(colmap),
        )
        return None
    try:
        start_line, start_col = map_cleaned_col_to_file(
            col,
            annotation_colmap=colmap,
            line=origin.line,
            host_text=origin.host.raw_text,
            host_start_line=origin.host.content_start_line,
            host_start_col=origin.host.content_start_col,
        )
        end_line, end_col_file = map_cleaned_col_to_file(
            end_col,
            annotation_colmap=colmap,
            line=origin.line,
            host_text=origin.host.raw_text,
            host_start_line=origin.host.content_start_line,
            host_start_col=origin.host.content_start_col,
            is_exclusive_end=True,
        )
    except (ValueError, IndexError) as exc:
        _log.warning(
            "scadwright LSP: position chain failed for cleaned line "
            "%r at col=%d end_col=%d: %s. Falling back to whole-line.",
            origin.line.cleaned, col, end_col, exc,
        )
        return None
    return DiagnosticRange(start_line, start_col, end_line, end_col_file)


def _whole_line_range(origin: _LineOrigin) -> DiagnosticRange:
    """File-position range covering the whole logical line."""
    host = origin.host
    line = origin.line
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
    return DiagnosticRange(start_line, start_col, end_line, end_col)
