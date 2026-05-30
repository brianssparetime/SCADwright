"""scadwright LSP server entry point.

Holds the ``main`` function dispatched by ``scadwright lsp``. The
CLI guarantees pygls is importable before calling :func:`main`
(it errors with an install hint when the ``[lsp]`` extra is
missing), so any pygls usage inside this module may import
unconditionally.

The server constructs a pygls ``LanguageServer`` and registers:

- ``textDocument/didOpen`` / ``didChange`` / ``didClose`` —
  diagnostics publication on every change, cleared on close.
- ``textDocument/completion`` (with ``:`` as a trigger character)
  — curated, type-tag, and Param-aware items.
- ``textDocument/hover`` — curated names, Params, and auto-
  declared targets.
- ``textDocument/definition`` — Param assignment range for class-
  declared names; first-occurrence equation line for auto-declared
  bare-Name targets.
- ``textDocument/documentSymbol`` — outline tree: one Class symbol
  per equations-bearing class, with each Param declaration as a
  Variable child.
- ``textDocument/rename`` — same-file rename across the Param
  assignment and every occurrence inside the surrounding class's
  equations strings.

Each handler reads the current document text from the workspace,
runs the appropriate logic from :mod:`scadwright.lsp.diagnostics`,
:mod:`scadwright.lsp.completion`, or :mod:`scadwright.lsp.hover`,
and returns or publishes the LSP-shaped result.

The server only runs the analyzer on files whose URI ends with
``.py``; non-Python files are silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer

from scadwright.component.equations.lex import (
    LogicalLine,
    _split_logical_lines,
)
from scadwright.lsp.analyze import EquationsBlock, find_equations_blocks
from scadwright.lsp.completion import (
    CompletionItem as ScCompletionItem,
    build_completion_items,
)
from scadwright.lsp.context import (
    ContextKind,
    classify_context,
    extract_attribute_chain,
)
from scadwright.lsp.definition import (
    DefinitionLocation as ScDefinitionLocation,
    build_definition_location,
)
from scadwright.lsp.diagnostics import (
    Diagnostic as ScDiagnostic,
    analyze_file,
)
from scadwright.lsp.hover import (
    HoverContent as ScHoverContent,
    build_hover_content,
    build_python_attribute_hover,
    extract_word_at,
)
from scadwright.lsp.positions import CursorInBlock, find_cursor_in_block
from scadwright.lsp.python_attribute_cursor import (
    PythonAttributeCursor,
    find_python_attribute_at_cursor,
)
from scadwright.lsp.rename import (
    TextEdit as ScTextEdit,
    build_workspace_rename_edits,
)
from scadwright.project_index.registry import build_class_registry
from scadwright.project_index.walk import walk_project
from scadwright.lsp.symbols import (
    DocumentSymbol as ScDocumentSymbol,
    build_document_symbols,
)


_SERVER_NAME = "scadwright-ls"
_SERVER_VERSION = "0.1.0"


_SEVERITY_MAP: dict[str, lsp.DiagnosticSeverity] = {
    "error": lsp.DiagnosticSeverity.Error,
    "warning": lsp.DiagnosticSeverity.Warning,
    "info": lsp.DiagnosticSeverity.Information,
    "hint": lsp.DiagnosticSeverity.Hint,
}


_COMPLETION_KIND_MAP: dict[str, lsp.CompletionItemKind] = {
    "function": lsp.CompletionItemKind.Function,
    "constant": lsp.CompletionItemKind.Constant,
    "class": lsp.CompletionItemKind.Class,
    "variable": lsp.CompletionItemKind.Variable,
    "keyword": lsp.CompletionItemKind.Keyword,
}


_SYMBOL_KIND_MAP: dict[str, lsp.SymbolKind] = {
    "class": lsp.SymbolKind.Class,
    "variable": lsp.SymbolKind.Variable,
}


def _to_lsp_diagnostic(d: ScDiagnostic) -> lsp.Diagnostic:
    """Convert an internal :class:`Diagnostic` to ``lsprotocol`` shape."""
    return lsp.Diagnostic(
        range=lsp.Range(
            start=lsp.Position(
                line=d.range.start_line, character=d.range.start_col,
            ),
            end=lsp.Position(
                line=d.range.end_line, character=d.range.end_col,
            ),
        ),
        severity=_SEVERITY_MAP.get(d.severity, lsp.DiagnosticSeverity.Error),
        message=d.message,
        source=d.source,
    )


def _to_lsp_completion(item: ScCompletionItem) -> lsp.CompletionItem:
    """Convert an internal :class:`CompletionItem` to ``lsprotocol``
    shape, mapping the kind string to the LSP enum and translating
    snippet vs plain-text insert formats.
    """
    out = lsp.CompletionItem(
        label=item.label,
        kind=_COMPLETION_KIND_MAP.get(
            item.kind, lsp.CompletionItemKind.Variable,
        ),
    )
    if item.detail is not None:
        out.detail = item.detail
    if item.documentation is not None:
        out.documentation = item.documentation
    if item.insert_text is not None:
        out.insert_text = item.insert_text
        out.insert_text_format = (
            lsp.InsertTextFormat.Snippet
            if item.is_snippet
            else lsp.InsertTextFormat.PlainText
        )
    return out


def _to_lsp_hover(content: ScHoverContent) -> lsp.Hover:
    """Wrap a markdown body in :class:`lsprotocol.types.Hover`."""
    return lsp.Hover(
        contents=lsp.MarkupContent(
            kind=lsp.MarkupKind.Markdown,
            value=content.markdown,
        ),
    )


def _to_lsp_location(
    loc: ScDefinitionLocation, uri: str,
) -> lsp.Location:
    """Combine an internal definition range with the document URI to
    produce an :class:`lsprotocol.types.Location`."""
    return lsp.Location(
        uri=uri,
        range=lsp.Range(
            start=lsp.Position(
                line=loc.start_line, character=loc.start_col,
            ),
            end=lsp.Position(
                line=loc.end_line, character=loc.end_col,
            ),
        ),
    )


def _to_lsp_text_edit(edit: ScTextEdit) -> lsp.TextEdit:
    """Convert an internal :class:`TextEdit` to ``lsprotocol`` shape."""
    return lsp.TextEdit(
        range=lsp.Range(
            start=lsp.Position(
                line=edit.start_line, character=edit.start_col,
            ),
            end=lsp.Position(
                line=edit.end_line, character=edit.end_col,
            ),
        ),
        new_text=edit.new_text,
    )


def _to_lsp_workspace_edit(
    edits_by_uri: dict[str, list[ScTextEdit]],
) -> lsp.WorkspaceEdit:
    """Bundle per-URI TextEdit lists into an LSP WorkspaceEdit.

    Files with empty edit lists are kept (LSP clients ignore them);
    callers are free to prune beforehand if they prefer a tight
    payload.
    """
    return lsp.WorkspaceEdit(
        changes={
            uri: [_to_lsp_text_edit(e) for e in edits]
            for uri, edits in edits_by_uri.items()
        },
    )


def _to_lsp_document_symbol(
    sym: ScDocumentSymbol,
) -> lsp.DocumentSymbol:
    """Convert an internal :class:`DocumentSymbol` to ``lsprotocol``
    shape, recursing into children."""
    return lsp.DocumentSymbol(
        name=sym.name,
        kind=_SYMBOL_KIND_MAP.get(sym.kind, lsp.SymbolKind.Variable),
        range=lsp.Range(
            start=lsp.Position(
                line=sym.start_line, character=sym.start_col,
            ),
            end=lsp.Position(line=sym.end_line, character=sym.end_col),
        ),
        selection_range=lsp.Range(
            start=lsp.Position(
                line=sym.selection_start_line,
                character=sym.selection_start_col,
            ),
            end=lsp.Position(
                line=sym.selection_end_line,
                character=sym.selection_end_col,
            ),
        ),
        detail=sym.detail,
        children=(
            [_to_lsp_document_symbol(c) for c in sym.children]
            if sym.children else None
        ),
    )


def _is_python_uri(uri: str) -> bool:
    """True for URIs the analyzer should process.

    Permissive — relies on the editor's filetype filter for the
    main gate. This guard catches the case where an editor sends
    didOpen for unrelated documents (some send for every visible
    buffer regardless of language).
    """
    return uri.endswith(".py")


def _publish_for_text(server: LanguageServer, uri: str, source: str) -> None:
    """Run the analyzer on ``source`` and publish diagnostics for ``uri``.

    The LSP runs as a long-lived process across many user files; an
    unanticipated failure inside ``analyze_file`` should not silently
    leave the editor without diagnostics. On exception, log via the
    LSP ``window/logMessage`` channel (most editors expose this in
    a server-logs panel) and return without publishing — the user
    sees no squiggles for the failing file but the server keeps
    serving every other file.
    """
    if not _is_python_uri(uri):
        return
    try:
        sc_diagnostics = analyze_file(source)
    except Exception as exc:  # noqa: BLE001 - LSP boundary
        server.window_log_message(
            lsp.LogMessageParams(
                type=lsp.MessageType.Error,
                message=(
                    f"scadwright analyzer failed for {uri}: "
                    f"{type(exc).__name__}: {exc}"
                ),
            ),
        )
        return
    server.text_document_publish_diagnostics(
        lsp.PublishDiagnosticsParams(
            uri=uri,
            diagnostics=[_to_lsp_diagnostic(d) for d in sc_diagnostics],
        ),
    )


def _publish_clear(server: LanguageServer, uri: str) -> None:
    """Publish an empty diagnostic list to clear an editor's squiggles."""
    server.text_document_publish_diagnostics(
        lsp.PublishDiagnosticsParams(uri=uri, diagnostics=[]),
    )


# =============================================================================
# Cursor-location pipeline shared by completion and hover
# =============================================================================


@dataclass(frozen=True)
class _CursorContext:
    """The shape both completion and hover need from a file cursor.

    ``block`` is the equations block containing the cursor.
    ``cursor`` carries the host/line indices and the splitter
    column. ``line`` is the matched logical line (its ``cleaned``
    field is the splitter-cleaned text, still with sigils and type
    tags). ``context_kind`` is the syntactic context at the cursor.
    ``sibling_blocks`` is every equations block in the source file
    (including the matched one) — handlers that need cross-class
    resolution (attribute completion, future cross-Component
    features) can read it without re-parsing.
    """
    block: EquationsBlock
    cursor: CursorInBlock
    line: LogicalLine
    context_kind: ContextKind
    sibling_blocks: tuple[EquationsBlock, ...]


def _locate_cursor(
    source: str, file_line: int, file_col: int,
) -> _CursorContext | None:
    """Find which equations block contains the cursor and classify
    its context. Returns ``None`` when the cursor isn't in any
    block, when the source can't be parsed, or when an unanticipated
    failure surfaces — callers treat ``None`` as "no completion /
    hover here".
    """
    try:
        blocks = find_equations_blocks(source)
    except Exception:  # noqa: BLE001 - LSP boundary
        return None
    blocks_tuple = tuple(blocks)
    for block in blocks:
        cursor = find_cursor_in_block(block, file_line, file_col)
        if cursor is None:
            continue
        host = block.hosts[cursor.host_index]
        lines = _split_logical_lines(host.raw_text)
        if cursor.line_index >= len(lines):
            return None
        line = lines[cursor.line_index]
        context_kind = classify_context(line.cleaned, cursor.splitter_col)
        return _CursorContext(
            block=block,
            cursor=cursor,
            line=line,
            context_kind=context_kind,
            sibling_blocks=blocks_tuple,
        )
    return None


@dataclass(frozen=True)
class _PythonAttributeContext:
    """Outcome of resolving a cursor on a direct ``ClassName.attr``
    access in Python code.

    Carries the resolved cursor info plus the source class's
    equations block (already located by parsing the source file),
    so hover / definition / rename handlers can route through the
    same machinery they use for in-block cursors.
    """
    cursor: PythonAttributeCursor
    source_block: EquationsBlock


def _resolve_python_attribute(
    uri: str | None,
    project_root: Path | None,
    file_line: int,
    file_col: int,
) -> _PythonAttributeContext | None:
    """Walk the project and resolve the cursor to a class+attribute.

    Returns ``None`` when the cursor isn't on a direct class-
    attribute access, when the LSP doesn't have a workspace folder
    (no project_root), when the URI is non-file, or when the
    source class's equations block can't be located.

    Walks the project on every call. The cost is acceptable because
    this only fires when the equations-cursor pipeline returns
    ``None`` — hovers and definitions inside equations blocks stay
    fast.
    """
    if uri is None or project_root is None:
        return None
    file_path = _uri_to_path(uri)
    if file_path is None:
        return None
    files = walk_project(project_root)
    registry = build_class_registry(files, project_root)
    files_by_path = {f.path: f for f in files}
    file_info = files_by_path.get(file_path)
    if file_info is None:
        return None
    cursor = find_python_attribute_at_cursor(
        file_info, file_line, file_col, registry, project_root,
    )
    if cursor is None:
        return None
    try:
        source_text = cursor.target.file_path.read_text()
    except OSError:
        return None
    try:
        blocks = find_equations_blocks(source_text)
    except Exception:  # noqa: BLE001 - LSP boundary
        return None
    source_block = next(
        (b for b in blocks if b.class_name == cursor.target.name),
        None,
    )
    if source_block is None:
        return None
    return _PythonAttributeContext(
        cursor=cursor, source_block=source_block,
    )


def _completion_items_for(
    source: str, file_line: int, file_col: int,
) -> list[lsp.CompletionItem]:
    """Compute the LSP completion items for the cursor at
    ``(file_line, file_col)`` in ``source``. Returns ``[]`` when the
    cursor isn't in any equations block or its context produces no
    items.

    For ``ATTRIBUTE`` context, the base identifier is extracted from
    the cleaned line text and threaded through to
    :func:`build_completion_items` along with every sibling block so
    same-file cross-Component lookup can resolve the base's type.
    """
    located = _locate_cursor(source, file_line, file_col)
    if located is None:
        return []
    attribute_chain: list[str] | None = None
    if located.context_kind == ContextKind.ATTRIBUTE:
        attribute_chain = extract_attribute_chain(
            located.line.cleaned, located.cursor.splitter_col,
        )
    sc_items = build_completion_items(
        located.context_kind,
        block=located.block,
        host_index=located.cursor.host_index,
        line_index=located.cursor.line_index,
        attribute_chain=attribute_chain,
        sibling_blocks=located.sibling_blocks,
    )
    return [_to_lsp_completion(it) for it in sc_items]


def _hover_for(
    source: str,
    file_line: int,
    file_col: int,
    uri: str | None = None,
    project_root: Path | None = None,
) -> lsp.Hover | None:
    """Compute the LSP hover response for the cursor at
    ``(file_line, file_col)`` in ``source``.

    First tries equations-block resolution. If the cursor isn't in
    any equations block, falls through to direct class-attribute
    access in Python code: ``BronicaS2Bayonet.cam_barrel_od`` and
    similar patterns resolve through the project's class registry
    to the source class's equations block, and hover content for
    the attribute comes from that block. The fall-through requires
    both ``uri`` and ``project_root``; without them it returns
    ``None``.
    """
    located = _locate_cursor(source, file_line, file_col)
    if located is not None:
        word = extract_word_at(located.line.cleaned, located.cursor.splitter_col)
        if word is None:
            return None
        attribute_chain: list[str] | None = None
        if located.context_kind == ContextKind.ATTRIBUTE:
            attribute_chain = extract_attribute_chain(
                located.line.cleaned, located.cursor.splitter_col,
            )
        content = build_hover_content(
            word,
            located.context_kind,
            block=located.block,
            host_index=located.cursor.host_index,
            line_index=located.cursor.line_index,
            attribute_chain=attribute_chain,
            sibling_blocks=located.sibling_blocks,
        )
        if content is None:
            return None
        return _to_lsp_hover(content)

    ctx = _resolve_python_attribute(uri, project_root, file_line, file_col)
    if ctx is None:
        return None
    content = build_python_attribute_hover(ctx.cursor.attr_name, ctx.source_block)
    if content is None:
        return None
    return _to_lsp_hover(content)


def _definition_for(
    source: str,
    file_line: int,
    file_col: int,
    uri: str,
    project_root: Path | None = None,
) -> lsp.Location | None:
    """Compute the LSP definition location for the cursor at
    ``(file_line, file_col)`` in ``source``.

    First tries equations-block resolution. Falls through to
    direct class-attribute access in Python code, jumping to the
    line in the source class's equations block where the attribute
    is declared. The fall-through requires ``project_root``;
    without it the handler stays equations-only.
    """
    located = _locate_cursor(source, file_line, file_col)
    if located is not None:
        word = extract_word_at(located.line.cleaned, located.cursor.splitter_col)
        if word is None:
            return None
        attribute_chain: list[str] | None = None
        if located.context_kind == ContextKind.ATTRIBUTE:
            attribute_chain = extract_attribute_chain(
                located.line.cleaned, located.cursor.splitter_col,
            )
        sc_loc = build_definition_location(
            word, located.context_kind, located.block,
            attribute_chain=attribute_chain,
            sibling_blocks=located.sibling_blocks,
        )
        if sc_loc is None:
            return None
        return _to_lsp_location(sc_loc, uri)

    ctx = _resolve_python_attribute(uri, project_root, file_line, file_col)
    if ctx is None:
        return None
    sc_loc = build_definition_location(
        ctx.cursor.attr_name, ContextKind.EXPRESSION, ctx.source_block,
    )
    if sc_loc is None:
        return None
    source_uri = _path_to_uri(ctx.cursor.target.file_path)
    return _to_lsp_location(sc_loc, source_uri)


def _document_symbols_for(source: str) -> list[lsp.DocumentSymbol]:
    """Compute the LSP document symbols for ``source``. Returns
    ``[]`` when the source has no equations-bearing classes or
    can't be parsed.
    """
    try:
        blocks = find_equations_blocks(source)
    except Exception:  # noqa: BLE001 - LSP boundary
        return []
    sc_symbols = build_document_symbols(blocks)
    return [_to_lsp_document_symbol(s) for s in sc_symbols]


def _rename_for(
    source: str,
    file_line: int,
    file_col: int,
    new_name: str,
    uri: str,
    project_root: Path | None = None,
) -> lsp.WorkspaceEdit | None:
    """Compute the LSP WorkspaceEdit for a rename request.

    Returns ``None`` when the cursor isn't on a renameable name —
    not in any equations block, on a curated/type-tag name, or on
    a name the LSP doesn't own. The client interprets ``None`` as
    "rename not available here".

    When ``project_root`` is supplied, the rename extends across
    every project file that holds a ``Param`` of the source class
    and references the target attribute, plus every file with
    direct ``SourceClass.<attr>`` references. Without a project
    root the rename stays same-file (the editor passes ``None``
    when no workspace folder applies).

    The handler accepts rename invocations from two cursor
    positions: inside the source class's equations block (the
    canonical case), and on a direct ``SourceClass.<attr>``
    reference in any Python file (a consumer file that reads the
    attribute via class-attribute access). The latter resolves
    the cursor to the source class first, then routes through the
    same workspace-rename machinery.
    """
    located = _locate_cursor(source, file_line, file_col)
    if located is not None:
        word = extract_word_at(located.line.cleaned, located.cursor.splitter_col)
        if word is None:
            return None
        file_path = _uri_to_path(uri)
        if file_path is None:
            return None
        edits_by_path = build_workspace_rename_edits(
            located.block, file_path, word, new_name, project_root,
        )
        if edits_by_path is None:
            return None
        edits_by_uri = {
            _path_to_uri(path): edits
            for path, edits in edits_by_path.items()
        }
        return _to_lsp_workspace_edit(edits_by_uri)

    ctx = _resolve_python_attribute(uri, project_root, file_line, file_col)
    if ctx is None:
        return None
    edits_by_path = build_workspace_rename_edits(
        ctx.source_block,
        ctx.cursor.target.file_path,
        ctx.cursor.attr_name,
        new_name,
        project_root,
    )
    if edits_by_path is None:
        return None
    edits_by_uri = {
        _path_to_uri(path): edits
        for path, edits in edits_by_path.items()
    }
    return _to_lsp_workspace_edit(edits_by_uri)


def _uri_to_path(uri: str) -> Path | None:
    """Convert a ``file://`` URI to an absolute :class:`Path`, or
    ``None`` for non-file schemes (e.g., the editor's untitled
    documents). Cross-file rename can't apply to non-file URIs.
    """
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path))


def _path_to_uri(path: Path) -> str:
    """Convert an absolute path back into a ``file://`` URI for
    the LSP WorkspaceEdit's ``changes`` map.
    """
    return path.as_uri()


def _workspace_root_for(
    ls: LanguageServer, uri: str,
) -> Path | None:
    """Resolve the workspace folder containing ``uri``, or ``None``
    when the editor opened the file outside any workspace folder
    (single-file mode). Cross-file rename uses the returned path as
    the project root; same-file rename is the fallback when this
    returns ``None``.

    Multi-root workspaces: the longest matching folder wins, so a
    nested project takes precedence over its parent.
    """
    file_path = _uri_to_path(uri)
    if file_path is None:
        return None
    best: Path | None = None
    best_len = -1
    folders = getattr(ls.workspace, "folders", None) or {}
    for folder in folders.values():
        folder_uri = getattr(folder, "uri", None)
        if folder_uri is None:
            continue
        folder_path = _uri_to_path(folder_uri)
        if folder_path is None:
            continue
        try:
            file_path.relative_to(folder_path)
        except ValueError:
            continue
        length = len(str(folder_path))
        if length > best_len:
            best = folder_path
            best_len = length
    return best


def build_server() -> LanguageServer:
    """Construct the LanguageServer with all handlers registered.

    Factored out of :func:`main` so tests can exercise the handler
    behavior without starting a stdio loop.

    Document sync is forced to ``Full``: equations files are tiny
    (a class body, never an entire codebase) and full sync sidesteps
    the per-client quirks several editors have around incremental
    sync (Helix in particular). The cost — re-sending the whole
    document on each change — is invisible at the file sizes the
    LSP processes.
    """
    server = LanguageServer(
        _SERVER_NAME,
        _SERVER_VERSION,
        text_document_sync_kind=lsp.TextDocumentSyncKind.Full,
    )

    @server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
    def on_did_open(
        ls: LanguageServer, params: lsp.DidOpenTextDocumentParams,
    ) -> None:
        _publish_for_text(
            ls, params.text_document.uri, params.text_document.text,
        )

    @server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
    def on_did_change(
        ls: LanguageServer, params: lsp.DidChangeTextDocumentParams,
    ) -> None:
        uri = params.text_document.uri
        if not _is_python_uri(uri):
            return
        # The workspace applies incremental edits internally; reading
        # ``source`` here returns the current full text regardless of
        # whether the client sent full or incremental sync.
        document = ls.workspace.get_text_document(uri)
        _publish_for_text(ls, uri, document.source)

    @server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
    def on_did_close(
        ls: LanguageServer, params: lsp.DidCloseTextDocumentParams,
    ) -> None:
        if not _is_python_uri(params.text_document.uri):
            return
        _publish_clear(ls, params.text_document.uri)

    @server.feature(
        lsp.TEXT_DOCUMENT_COMPLETION,
        lsp.CompletionOptions(trigger_characters=[":", "."]),
    )
    def on_completion(
        ls: LanguageServer, params: lsp.CompletionParams,
    ) -> lsp.CompletionList:
        uri = params.text_document.uri
        if not _is_python_uri(uri):
            return lsp.CompletionList(is_incomplete=False, items=[])
        document = ls.workspace.get_text_document(uri)
        items = _completion_items_for(
            document.source,
            params.position.line,
            params.position.character,
        )
        return lsp.CompletionList(is_incomplete=False, items=items)

    @server.feature(lsp.TEXT_DOCUMENT_HOVER)
    def on_hover(
        ls: LanguageServer, params: lsp.HoverParams,
    ) -> lsp.Hover | None:
        uri = params.text_document.uri
        if not _is_python_uri(uri):
            return None
        document = ls.workspace.get_text_document(uri)
        return _hover_for(
            document.source,
            params.position.line,
            params.position.character,
            uri=uri,
            project_root=_workspace_root_for(ls, uri),
        )

    @server.feature(lsp.TEXT_DOCUMENT_DEFINITION)
    def on_definition(
        ls: LanguageServer, params: lsp.DefinitionParams,
    ) -> lsp.Location | None:
        uri = params.text_document.uri
        if not _is_python_uri(uri):
            return None
        document = ls.workspace.get_text_document(uri)
        return _definition_for(
            document.source,
            params.position.line,
            params.position.character,
            uri,
            project_root=_workspace_root_for(ls, uri),
        )

    @server.feature(lsp.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
    def on_document_symbol(
        ls: LanguageServer, params: lsp.DocumentSymbolParams,
    ) -> list[lsp.DocumentSymbol]:
        uri = params.text_document.uri
        if not _is_python_uri(uri):
            return []
        document = ls.workspace.get_text_document(uri)
        return _document_symbols_for(document.source)

    @server.feature(lsp.TEXT_DOCUMENT_RENAME)
    def on_rename(
        ls: LanguageServer, params: lsp.RenameParams,
    ) -> lsp.WorkspaceEdit | None:
        uri = params.text_document.uri
        if not _is_python_uri(uri):
            return None
        document = ls.workspace.get_text_document(uri)
        return _rename_for(
            document.source,
            params.position.line,
            params.position.character,
            params.new_name,
            uri,
            project_root=_workspace_root_for(ls, uri),
        )

    return server


def main() -> int:
    """Run the language server. Returns the process exit code.

    Builds the server, then enters the blocking stdio loop. The
    loop returns when the client closes the connection (typically
    on editor shutdown). Returns 0 on a clean exit.
    """
    server = build_server()
    server.start_io()
    return 0
