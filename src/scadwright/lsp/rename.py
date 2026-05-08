"""Same-file rename refactoring for names inside equations blocks.

Computes the list of :class:`TextEdit` operations needed to rename
a target name to a new name within the surrounding class:

- The class-level ``name = Param(...)`` assignment (when the target
  is a declared Param) — just the name part of the assignment is
  replaced, not the full statement.
- Every occurrence of the target name as a bare ``ast.Name`` inside
  any ``equations = ...`` string in the same class. Equation, rule,
  and adjustment bodies are all walked. The LHS of an adjustment
  is re-derived from the cleaned line text since adjustments don't
  preserve their LHS as a separate AST node.

Same-file only — cross-file renames would need workspace
import-graph resolution that's deferred per the design doc. The
helper validates that both the target and the new name are
renameable (the target must be a Param or auto-declared bare-Name
target; both names must avoid the curated namespace and the
inline-type allowlist) and returns ``None`` when the rename is
unsafe.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from scadwright.component.equations import (
    LogicalLine,
    _CURATED_BUILTINS,
    _CURATED_MATH,
    _INLINE_TYPE_ALLOWLIST,
    _extract_name_annotations_with_colmap,
)
from scadwright.component.equations.lex import _split_logical_lines
from scadwright.component.resolver import parse_equations_unified
from scadwright.component.resolver.parsing import (
    _peel_trailing_comment,
    _split_top_level_adjustment,
)
from scadwright.component.resolver.types import _PREDICATE_CALL_NAMES
from scadwright.errors import ValidationError
from scadwright.lsp.analyze import (
    EquationsBlock,
    EquationsHostString,
    auto_declared_origins_in_block,
)
from scadwright.lsp.positions import map_cleaned_col_to_file


_RESERVED_NAMES = (
    frozenset(_CURATED_BUILTINS)
    | frozenset(_CURATED_MATH)
    | frozenset(_INLINE_TYPE_ALLOWLIST)
    | _PREDICATE_CALL_NAMES
)


@dataclass(frozen=True)
class TextEdit:
    """A single edit operation: replace the file range with ``new_text``.

    All four position fields are 0-based per LSP convention.
    """
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    new_text: str


def is_valid_new_name(name: str) -> bool:
    """True if ``name`` is a syntactically valid Python identifier
    that doesn't collide with a curated namespace name, type-tag,
    or predicate-call name. The resolver's class-define-time check
    would otherwise reject the rename via
    ``_check_reserved_collisions``.
    """
    if not name:
        return False
    if not (name[0].isalpha() or name[0] == "_"):
        return False
    if not all(c.isalnum() or c == "_" for c in name):
        return False
    if name in _RESERVED_NAMES:
        return False
    return True


def is_renameable_target(name: str, block: EquationsBlock) -> bool:
    """True if ``name`` is something this LSP can rename within
    ``block``: a class-declared Param, or a bare-Name target
    declared anywhere in the block. Curated and type-tag names are
    refused since the LSP doesn't own them.
    """
    if name in _RESERVED_NAMES:
        return False
    if name in block.param_names:
        return True
    return name in auto_declared_origins_in_block(block)


def build_rename_edits(
    block: EquationsBlock,
    target_name: str,
    new_name: str,
) -> list[TextEdit] | None:
    """Compute the TextEdits needed to rename ``target_name`` to
    ``new_name`` inside ``block``.

    Returns ``None`` when the rename is unsafe — the target isn't
    renameable, the new name isn't valid, or the equations block
    fails to parse (in which case any edits we emit could be
    misaligned). Returns ``[]`` when the rename is allowed but the
    name has no occurrences (degenerate but not an error).
    """
    if not is_renameable_target(target_name, block):
        return None
    if not is_valid_new_name(new_name):
        return None

    eq_lines, line_origins = _flatten_for_rename(block)
    if not eq_lines:
        return _maybe_param_edit_only(block, target_name, new_name)
    try:
        parsed = parse_equations_unified(
            eq_lines, class_name=block.class_name,
        )
    except ValidationError:
        return None
    equations, constraints, _, _, adjustments = parsed

    edits: list[TextEdit] = []

    # 1. Param assignment.
    param_edit = _param_assignment_edit(block, target_name, new_name)
    if param_edit is not None:
        edits.append(param_edit)

    # 2. Per-line annotation colmaps (memoized to avoid recomputation
    # while walking many AST nodes per line).
    colmaps = [
        _extract_name_annotations_with_colmap(line.cleaned)[3]
        for _, line in line_origins
    ]

    def edits_in(node: ast.AST, source_index: int) -> list[TextEdit]:
        return _edits_from_node(
            node, source_index, target_name, new_name,
            block, line_origins, colmaps,
        )

    for eq in equations:
        edits.extend(edits_in(eq.lhs, eq.source_line_index))
        edits.extend(edits_in(eq.rhs, eq.source_line_index))
    for c in constraints:
        edits.extend(edits_in(c.expr, c.source_line_index))
    seen_adj_lines: set[int] = set()
    for adj in adjustments:
        edits.extend(edits_in(adj.rhs, adj.source_line_index))
        # Adjustment LHS isn't preserved as an AST node; re-derive
        # it from the cleaned text once per source line. Comma-
        # broadcast siblings share a source line and would
        # otherwise produce duplicate edits.
        if adj.source_line_index in seen_adj_lines:
            continue
        seen_adj_lines.add(adj.source_line_index)
        edits.extend(_edits_from_adjustment_lhs(
            adj.source_line_index, target_name, new_name,
            block, line_origins,
        ))

    return edits


# =============================================================================
# Internals
# =============================================================================


def _flatten_for_rename(
    block: EquationsBlock,
) -> tuple[list[str], list[tuple[int, LogicalLine]]]:
    """Return per-line cleaned strings paired with
    ``(host_index, LogicalLine)`` for each.
    """
    lines: list[str] = []
    origins: list[tuple[int, LogicalLine]] = []
    for h_idx, host in enumerate(block.hosts):
        for line in _split_logical_lines(host.raw_text):
            lines.append(line.cleaned)
            origins.append((h_idx, line))
    return lines, origins


def _maybe_param_edit_only(
    block: EquationsBlock, target_name: str, new_name: str,
) -> list[TextEdit]:
    """For blocks with no equation lines (``equations = ""``), the
    only possible edit is on a Param assignment if the target is a
    Param.
    """
    edit = _param_assignment_edit(block, target_name, new_name)
    return [edit] if edit is not None else []


def _param_assignment_edit(
    block: EquationsBlock, target_name: str, new_name: str,
) -> TextEdit | None:
    """Edit covering just the name token of
    ``target_name = Param(...)``. Returns ``None`` if the target
    isn't a Param or its position info is missing.
    """
    for p in block.params:
        if p.name != target_name:
            continue
        if p.assign_start_line is None or p.assign_start_col is None:
            return None
        return TextEdit(
            start_line=p.assign_start_line,
            start_col=p.assign_start_col,
            end_line=p.assign_start_line,
            end_col=p.assign_start_col + len(target_name),
            new_text=new_name,
        )
    return None


def _edits_from_node(
    node: ast.AST,
    source_index: int,
    target_name: str,
    new_name: str,
    block: EquationsBlock,
    line_origins: list[tuple[int, LogicalLine]],
    colmaps: list[tuple[int, ...]],
) -> list[TextEdit]:
    """Walk ``node`` for ``Name(target_name)`` occurrences and emit
    a TextEdit per occurrence.
    """
    if source_index < 0 or source_index >= len(line_origins):
        return []
    host_index, line = line_origins[source_index]
    host = block.hosts[host_index]
    colmap = colmaps[source_index]
    out: list[TextEdit] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == target_name:
            edit = _edit_from_name(
                sub.col_offset, sub.end_col_offset,
                line, host, colmap, new_name,
            )
            if edit is not None:
                out.append(edit)
    return out


def _edits_from_adjustment_lhs(
    source_index: int,
    target_name: str,
    new_name: str,
    block: EquationsBlock,
    line_origins: list[tuple[int, LogicalLine]],
) -> list[TextEdit]:
    """Find ``Name(target_name)`` on the LHS of an adjustment.

    Adjustments don't carry their LHS as an AST node, so we run the
    trailing-comment peel and adjustment splitter on the post-
    annotation-strip text to recover the LHS substring and its
    start column. That LHS is then parsed as a Python expression
    and walked for ``Name`` nodes whose ``id`` matches the target.
    Sigils and type tags don't affect adjustment-vs-not
    classification, so a single peel-and-split on the stripped
    text is enough.
    """
    if source_index < 0 or source_index >= len(line_origins):
        return []
    host_index, line = line_origins[source_index]
    host = block.hosts[host_index]
    cleaned, _, _, line_colmap = _extract_name_annotations_with_colmap(
        line.cleaned,
    )
    body, _ = _peel_trailing_comment(cleaned)
    split = _split_top_level_adjustment(body)
    if split is None:
        return []
    lhs_text, _, _, lhs_start, _ = split
    try:
        lhs_node = ast.parse(lhs_text, mode="eval").body
    except SyntaxError:
        return []
    out: list[TextEdit] = []
    for sub in ast.walk(lhs_node):
        if isinstance(sub, ast.Name) and sub.id == target_name:
            edit = _edit_from_name(
                sub.col_offset + lhs_start,
                sub.end_col_offset + lhs_start,
                line, host, line_colmap, new_name,
            )
            if edit is not None:
                out.append(edit)
    return out


def _edit_from_name(
    col: int,
    end_col: int,
    line: LogicalLine,
    host: EquationsHostString,
    colmap: tuple[int, ...],
    new_name: str,
) -> TextEdit | None:
    """Convert a column range in cleaned-stripped coordinates to a
    file-position TextEdit. Returns ``None`` on out-of-bounds
    inputs — the caller skips such occurrences rather than fail
    the rename.
    """
    if col < 0 or end_col < col or end_col > len(colmap):
        return None
    try:
        start_line, start_col = map_cleaned_col_to_file(
            col,
            annotation_colmap=colmap, line=line,
            host_text=host.raw_text,
            host_start_line=host.content_start_line,
            host_start_col=host.content_start_col,
        )
        end_line, end_col_file = map_cleaned_col_to_file(
            end_col,
            annotation_colmap=colmap, line=line,
            host_text=host.raw_text,
            host_start_line=host.content_start_line,
            host_start_col=host.content_start_col,
            is_exclusive_end=True,
        )
    except (ValueError, IndexError):
        return None
    return TextEdit(
        start_line=start_line,
        start_col=start_col,
        end_line=end_line,
        end_col=end_col_file,
        new_text=new_name,
    )
