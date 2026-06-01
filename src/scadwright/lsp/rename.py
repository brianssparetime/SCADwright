"""Rename refactoring for names inside equations blocks, with
optional cross-file rename via the project index.

The same-file path computes :class:`TextEdit` operations for the
surrounding class:

- The class-level ``name = Param(...)`` assignment (when the target
  is a declared Param) — just the name part of the assignment is
  replaced, not the full statement.
- Every occurrence of the target name as a bare ``ast.Name`` inside
  any ``equations = ...`` string in the same class. Equation, rule,
  and adjustment bodies are all walked. The LHS of an adjustment
  is re-derived from the cleaned line text since adjustments don't
  preserve their LHS as a separate AST node.

When called with a ``project_root``,
:func:`build_workspace_rename_edits` extends the rename to other
project files. Every class across the project is walked for
references to the source attribute. Direct
``<SourceClass>.<old_name>`` references at class scope or in any
method body are rewritten via import-aware name resolution;
aliased and dotted imports both surface. Param-mediated
references (``<param_name>.<old_name>`` in equations,
``self.<param_name>.<old_name>`` anywhere in a method body) are
rewritten in classes that hold a ``Param`` whose type resolves
to the source class.

Both names must avoid the curated namespace and the inline-type
allowlist; the helper returns ``None`` when the rename is unsafe.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

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
from scadwright.lsp.positions import (
    byte_col_to_char_col,
    map_cleaned_col_to_file,
    split_source_lines,
)
from scadwright.project_index.analyze import _block_from_classdef
from scadwright.project_index.extract import (
    build_params_by_class,
    resolve_chain_type,
)
from scadwright.project_index.registry import (
    ResolvedClass,
    build_class_registry,
    resolve_name_in_file,
)
from scadwright.project_index.walk import walk_project


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


# =============================================================================
# Cross-file rename
# =============================================================================


def build_workspace_rename_edits(
    block: EquationsBlock,
    file_path: Path,
    target_name: str,
    new_name: str,
    project_root: Path | None,
    *,
    source_overrides: Mapping[Path, str] = MappingProxyType({}),
) -> dict[Path, list[TextEdit]] | None:
    """Compute per-file TextEdits for a rename across the project.

    The same-file edits come from :func:`build_rename_edits`. When
    ``project_root`` is provided, the project index is walked for
    other classes that hold a ``Param`` of the source class's type
    and read ``<param_name>.<target_name>`` in their equations or
    ``self.<param_name>.<target_name>`` in their ``build()``
    methods. Each such reference becomes a TextEdit in that file.

    ``project_root=None`` degrades to same-file behavior — the
    LSP uses this when the editor hasn't supplied a workspace
    folder for the document being edited.

    ``source_overrides`` maps file paths to the editor's live
    buffer text. Cross-file edits are computed against these
    buffers for any open file, so a rename lands on the exact
    positions the editor will apply it to. Closed files (absent
    from the map) are read from disk. See :func:`walk_project`.

    Returns ``None`` when same-file rename is unsafe (target not
    renameable, new name invalid, parser failure). Returns a dict
    keyed by file path otherwise; the source file is always
    present, even when its edit list is empty.
    """
    same_file = build_rename_edits(block, target_name, new_name)
    if same_file is None:
        return None
    out: dict[Path, list[TextEdit]] = {file_path: same_file}
    if project_root is None:
        return out
    cross = build_cross_file_attr_rename_edits(
        source_file_path=file_path,
        source_class_name=block.class_name,
        old_attr_name=target_name,
        new_attr_name=new_name,
        project_root=project_root,
        source_overrides=source_overrides,
    )
    for path, edits in cross.items():
        out.setdefault(path, []).extend(edits)
    return out


def build_cross_file_attr_rename_edits(
    source_file_path: Path,
    source_class_name: str,
    old_attr_name: str,
    new_attr_name: str,
    project_root: Path,
    *,
    source_overrides: Mapping[Path, str] = MappingProxyType({}),
) -> dict[Path, list[TextEdit]]:
    """Find references to ``<source_class_name>.<old_attr_name>``
    in other project files and emit TextEdits for each.

    Three reference shapes are caught, all resolving to the source
    class:

    - Direct ``SourceClass.<old_attr>`` at class scope, in any
      method, at module scope, or in a module-level function.
    - ``self.<chain>.<old_attr>`` in any method body, where the
      chain resolves through declared Param types to the source
      class (one hop ``self.spec.x``, or deeper ``self.a.b.x``).
    - ``<chain>.<old_attr>`` in an equations block, same chain
      resolution from a Param base.

    The chain resolution walks declared Param types hop by hop, so
    a consumer that reaches the source class transitively (its
    Param's type holds a Param of the source class) is caught even
    though it has no direct Param of the source class. References
    through a local variable, ``getattr``, or a function return
    can't be resolved statically and are not rewritten; that broken
    reference surfaces on the next solve or run.

    The source file's own equations references are the caller's job
    (``build_rename_edits``); this pass excludes the source class
    from the chain walks but still rewrites direct ``SourceClass.x``
    self-references in the source file's Python body.

    ``source_overrides`` routes open editor buffers into the walk
    so edits land on buffer positions rather than stale disk ones.

    Returns a (possibly empty) dict of path → edits, with empty
    edit lists pruned. Order within each list reflects source order.
    """
    files = walk_project(project_root, source_overrides=source_overrides)
    registry = build_class_registry(files, project_root)
    files_by_path = {f.path: f for f in files}
    params_by_class = build_params_by_class(
        registry, files_by_path, project_root,
    )
    source_class = registry.classes.get(
        (source_file_path, source_class_name),
    )

    # A file that doesn't contain the attribute token anywhere can't
    # hold a reference; skipping it bounds the per-class chain walk
    # on large projects without affecting the result.
    files_with_token = {
        f.path for f in files if old_attr_name in f.source
    }

    out: dict[Path, list[TextEdit]] = {}

    # Pass 1 — direct ``ClassName.attr`` references, per file.
    for file_info in files:
        if file_info.path not in files_with_token:
            continue
        direct = _direct_class_attr_edits(
            file_info.tree, file_info, registry, project_root,
            source_file_path, source_class_name,
            old_attr_name, new_attr_name,
        )
        if direct:
            out.setdefault(file_info.path, []).extend(direct)

    # Pass 2 — chained references through declared Param types
    # (``self.<chain>.attr`` in methods, ``<chain>.attr`` in
    # equations). Visits every class except the source class; the
    # chain resolver determines whether each chain reaches the
    # source class, so transitively-reaching classes are covered
    # without a direct-Param gate.
    if source_class is not None:
        for cls in registry.classes.values():
            if cls is source_class:
                continue
            if cls.file_path not in files_with_token:
                continue
            file_info = files_by_path.get(cls.file_path)
            if file_info is None:
                continue
            chain_edits: list[TextEdit] = []
            chain_edits.extend(_cross_file_method_edits(
                cls, file_info, source_class,
                old_attr_name, new_attr_name, params_by_class,
            ))
            chain_edits.extend(_cross_file_equation_edits(
                cls, file_info, source_class,
                old_attr_name, new_attr_name, params_by_class,
            ))
            if chain_edits:
                out.setdefault(cls.file_path, []).extend(chain_edits)

    return out


def _cross_file_equation_edits(
    cls,
    file_info,
    source_class,
    old_attr_name: str,
    new_attr_name: str,
    params_by_class,
) -> list[TextEdit]:
    """Find ``<chain>.<old_attr>`` references inside ``cls``'s
    equations block whose chain resolves to ``source_class``, and
    emit TextEdits replacing the attr name.

    The base chain is resolved through declared Param types, so a
    one-hop ``spec.x`` and a deeper ``a.b.x`` are both handled. The
    Attribute AST nodes from ``parse_equations_unified`` carry
    cleaned-line column offsets; the colmap maps cleaned to raw, and
    ``map_cleaned_col_to_file`` projects raw columns back into
    file-line / file-column space.
    """
    block = _block_from_classdef(cls.ast_node, file_info.source)
    if block is None:
        return []
    eq_lines: list[str] = []
    line_origins: list[tuple[int, LogicalLine]] = []
    for h_idx, host in enumerate(block.hosts):
        for line in _split_logical_lines(host.raw_text):
            eq_lines.append(line.cleaned)
            line_origins.append((h_idx, line))
    if not eq_lines:
        return []
    try:
        parsed = parse_equations_unified(
            eq_lines, class_name=block.class_name,
        )
    except (ValidationError, ImportError):
        return []
    equations, constraints, _, _, adjustments = parsed
    colmaps = [
        _extract_name_annotations_with_colmap(line.cleaned)[3]
        for _, line in line_origins
    ]
    out: list[TextEdit] = []

    def emit(node: ast.AST, source_index: int) -> None:
        if source_index < 0 or source_index >= len(line_origins):
            return
        host_index, line = line_origins[source_index]
        host = block.hosts[host_index]
        colmap = colmaps[source_index]
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Attribute):
                continue
            if sub.attr != old_attr_name:
                continue
            owner = resolve_chain_type(sub.value, cls, params_by_class)
            if not _is_source_class(owner, source_class):
                continue
            attr_start = sub.value.end_col_offset + 1  # skip the dot
            attr_end = sub.end_col_offset
            edit = _edit_from_name(
                attr_start, attr_end,
                line, host, colmap, new_attr_name,
            )
            if edit is not None:
                out.append(edit)

    for eq in equations:
        emit(eq.lhs, eq.source_line_index)
        emit(eq.rhs, eq.source_line_index)
    for c in constraints:
        emit(c.expr, c.source_line_index)
    for adj in adjustments:
        emit(adj.rhs, adj.source_line_index)
    return out


def _cross_file_method_edits(
    cls,
    file_info,
    source_class,
    old_attr_name: str,
    new_attr_name: str,
    params_by_class,
) -> list[TextEdit]:
    """Find ``self.<chain>.<old_attr>`` references inside any method
    on ``cls`` whose chain resolves to ``source_class``, and emit
    TextEdits replacing the attr name.

    Walks the entire class body via ``ast.walk``, which descends
    into every method body — ``build``, helper methods, properties,
    anything else. For each ``Attribute(attr=old_attr)`` node, the
    value chain (``self.p1.p2…``) is resolved through declared Param
    types; the edit fires when it resolves to ``source_class``. This
    handles one hop (``self.spec.x``) and deeper (``self.a.b.x``)
    uniformly.

    Method-body AST nodes come from ``ast.parse(file_source)``, so
    their ``lineno`` / ``col_offset`` are file-relative. ast columns
    are UTF-8 byte offsets, converted to character indices against
    ``file_info``'s source lines so edits land correctly on
    non-ASCII lines. Lines are 1-based in the AST and 0-based in LSP.
    """
    source_lines = split_source_lines(file_info.source)
    out: list[TextEdit] = []
    for sub in ast.walk(cls.ast_node):
        if not isinstance(sub, ast.Attribute):
            continue
        if sub.attr != old_attr_name:
            continue
        owner = resolve_chain_type(sub.value, cls, params_by_class)
        if not _is_source_class(owner, source_class):
            continue
        # The attr part starts right after the value's end + 1
        # (the dot before the attr name).
        attr_start_line = (sub.lineno or 1) - 1
        attr_end_line = (sub.end_lineno or sub.lineno) - 1
        attr_start_col = byte_col_to_char_col(
            _line_at(source_lines, attr_start_line),
            (sub.value.end_col_offset or 0) + 1,
        )
        attr_end_col = byte_col_to_char_col(
            _line_at(source_lines, attr_end_line),
            sub.end_col_offset if sub.end_col_offset is not None else 0,
        )
        out.append(TextEdit(
            start_line=attr_start_line,
            start_col=attr_start_col,
            end_line=attr_end_line,
            end_col=attr_end_col,
            new_text=new_attr_name,
        ))
    return out


def _direct_class_attr_edits(
    scope_node,
    file_info,
    registry,
    project_root: Path,
    source_file_path: Path,
    source_class_name: str,
    old_attr_name: str,
    new_attr_name: str,
) -> list[TextEdit]:
    """Find direct ``<SourceClass>.<old_attr>`` references inside
    ``scope_node`` and emit TextEdits replacing the attr name.

    ``scope_node`` is typically a file's module AST
    (``file_info.tree``), making the walker cover class bodies,
    method bodies, module-scope statements, and module-level
    function bodies in one pass.

    Matches ``Attribute`` nodes whose ``attr == old_attr`` and
    whose value chain reduces to a dotted name resolving (through
    the file's imports) to the source class. Catches class-scope
    assignments like ``lower_outer_d = BronicaS2Bayonet.outer_d``,
    method-body expressions like ``return BronicaS2Bayonet.outer_d * 2``,
    module-level constants like ``MOUNT_OFFSET = SourceClass.attr``,
    and references through aliased or dotted imports.

    Chained access on the renamed attribute is handled correctly:
    ``BronicaS2Bayonet.outer_d.bit_length()`` renames only the
    inner ``outer_d``. The outer ``Attribute`` (``attr =
    bit_length``) has a base that doesn't resolve to the source
    class — its value is the inner Attribute, not a Name chain
    ending in the source class.

    AST positions come from ``ast.parse(file_source)`` and are
    file-relative. ast columns are UTF-8 byte offsets; they're
    converted to character indices against ``file_info``'s source
    lines so edits land correctly on non-ASCII lines.
    """
    if scope_node is None:
        return []
    source_lines = split_source_lines(file_info.source)
    out: list[TextEdit] = []
    for sub in ast.walk(scope_node):
        if not isinstance(sub, ast.Attribute):
            continue
        if sub.attr != old_attr_name:
            continue
        dotted = _value_chain_to_dotted_name(sub.value)
        if dotted is None:
            continue
        target = resolve_name_in_file(
            dotted, file_info, registry, project_root,
        )
        if target is None:
            continue
        if target.file_path != source_file_path:
            continue
        if target.name != source_class_name:
            continue
        # The attr part starts right after the base's end + 1
        # (the dot before the attr name).
        attr_start_line = (sub.lineno or 1) - 1
        attr_end_line = (sub.end_lineno or sub.lineno) - 1
        attr_start_col = byte_col_to_char_col(
            _line_at(source_lines, attr_start_line),
            (sub.value.end_col_offset or 0) + 1,
        )
        attr_end_col = byte_col_to_char_col(
            _line_at(source_lines, attr_end_line),
            sub.end_col_offset if sub.end_col_offset is not None else 0,
        )
        out.append(TextEdit(
            start_line=attr_start_line,
            start_col=attr_start_col,
            end_line=attr_end_line,
            end_col=attr_end_col,
            new_text=new_attr_name,
        ))
    return out


def _line_at(source_lines: list[str], index: int) -> str:
    """Return ``source_lines[index]`` or ``""`` when out of range."""
    if 0 <= index < len(source_lines):
        return source_lines[index]
    return ""


def _is_source_class(owner, source_class) -> bool:
    """True when a chain-resolution result ``owner`` is the source
    class. The ``_SELF`` sentinel and ``None`` (unresolvable) both
    fail the ``ResolvedClass`` check, so only a resolved class that
    matches the source by ``(file_path, name)`` qualifies."""
    return (
        isinstance(owner, ResolvedClass)
        and owner.file_path == source_class.file_path
        and owner.name == source_class.name
    )


def _value_chain_to_dotted_name(node: ast.AST) -> str | None:
    """Reduce a ``Name`` or chained ``Attribute`` expression to its
    dotted string form, or return ``None`` for other shapes.

    Handles bare ``Name(X)`` → ``"X"``, single ``Attribute(value=
    Name(X), attr=Y)`` → ``"X.Y"``, and deeper chains like
    ``Attribute(value=Attribute(value=Name(X), attr=Y), attr=Z)``
    → ``"X.Y.Z"``. Calls, subscripts, or other non-name shapes in
    the chain produce ``None``.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        cur: ast.AST = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if not isinstance(cur, ast.Name):
            return None
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None
