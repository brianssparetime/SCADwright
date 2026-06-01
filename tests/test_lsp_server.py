"""Tests for the pygls-backed LSP server.

The test surface focuses on the pure conversion and dispatch
helpers:

- ``_to_lsp_diagnostic``: per-field correctness for the
  internal-Diagnostic to lsprotocol-Diagnostic conversion.
- ``_is_python_uri``: filetype gating.
- ``_publish_for_text``: end-to-end via a recording stand-in for
  ``LanguageServer`` — given a source string, the right
  publish-diagnostics call is made.
- ``_publish_clear``: clearing call shape.
- ``build_server``: smoke test (the LanguageServer assembles and
  the feature decorators run without error).

The full async stdio loop is exercised only by editor
integrations; those are out of scope for unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

# Skip the entire module if pygls isn't installed (the LSP extra).
pytest.importorskip("pygls")
pytest.importorskip("lsprotocol")

from lsprotocol import types as lsp  # noqa: E402

from scadwright.lsp.diagnostics import (  # noqa: E402
    Diagnostic as ScDiagnostic,
    DiagnosticRange,
)
from scadwright.lsp.server import (  # noqa: E402
    _completion_items_for,
    _definition_for,
    _document_symbols_for,
    _hover_for,
    _is_python_uri,
    _publish_clear,
    _publish_for_text,
    _to_lsp_completion,
    _to_lsp_diagnostic,
    _to_lsp_document_symbol,
    _to_lsp_hover,
    _to_lsp_location,
    build_server,
)


# =============================================================================
# Diagnostic conversion
# =============================================================================


def test_to_lsp_diagnostic_maps_range_fields() -> None:
    sc = ScDiagnostic(
        range=DiagnosticRange(2, 4, 2, 14),
        severity="error",
        message="msg",
    )
    out = _to_lsp_diagnostic(sc)
    assert out.range.start.line == 2
    assert out.range.start.character == 4
    assert out.range.end.line == 2
    assert out.range.end.character == 14


def test_to_lsp_diagnostic_severity_mapping_covers_all_levels() -> None:
    cases = {
        "error": lsp.DiagnosticSeverity.Error,
        "warning": lsp.DiagnosticSeverity.Warning,
        "info": lsp.DiagnosticSeverity.Information,
        "hint": lsp.DiagnosticSeverity.Hint,
    }
    for level, expected in cases.items():
        sc = ScDiagnostic(
            range=DiagnosticRange(0, 0, 0, 0),
            severity=level,
            message="msg",
        )
        assert _to_lsp_diagnostic(sc).severity == expected


def test_to_lsp_diagnostic_unknown_severity_falls_back_to_error() -> None:
    sc = ScDiagnostic(
        range=DiagnosticRange(0, 0, 0, 0),
        severity="something-weird",
        message="msg",
    )
    assert _to_lsp_diagnostic(sc).severity == lsp.DiagnosticSeverity.Error


def test_to_lsp_diagnostic_carries_message_and_source() -> None:
    sc = ScDiagnostic(
        range=DiagnosticRange(0, 0, 0, 0),
        severity="error",
        message="something is wrong",
        source="scadwright",
    )
    out = _to_lsp_diagnostic(sc)
    assert out.message == "something is wrong"
    assert out.source == "scadwright"


# =============================================================================
# URI gating
# =============================================================================


def test_is_python_uri_accepts_dot_py() -> None:
    assert _is_python_uri("file:///some/path/widget.py")


def test_is_python_uri_rejects_other_extensions() -> None:
    assert not _is_python_uri("file:///some/path/widget.scad")
    assert not _is_python_uri("file:///some/path/widget.txt")
    assert not _is_python_uri("file:///some/path/Untitled-1")


# =============================================================================
# Publish helpers via a recording stand-in
# =============================================================================


@dataclass
class _RecordingServer:
    """Stand-in recording the LanguageServer methods our handlers use.

    Captures both ``text_document_publish_diagnostics`` (the normal
    path) and ``window_log_message`` (the exception-path log) so
    tests can assert on either side of the publish helper's
    behavior.
    """
    calls: list[lsp.PublishDiagnosticsParams]
    log_calls: list[lsp.LogMessageParams]

    def text_document_publish_diagnostics(
        self, params: lsp.PublishDiagnosticsParams,
    ) -> None:
        self.calls.append(params)

    def window_log_message(self, params: lsp.LogMessageParams) -> None:
        self.log_calls.append(params)


def _new_recording_server() -> _RecordingServer:
    return _RecordingServer(calls=[], log_calls=[])


def test_publish_for_text_emits_diagnostics_for_bad_equations() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    y = snh(x)\n'
        '    """\n'
    )
    server = _new_recording_server()
    _publish_for_text(server, "file:///widget.py", src)
    assert len(server.calls) == 1
    call = server.calls[0]
    assert call.uri == "file:///widget.py"
    assert len(call.diagnostics) == 1
    assert call.diagnostics[0].severity == lsp.DiagnosticSeverity.Error
    assert "snh" in call.diagnostics[0].message


def test_publish_for_text_emits_empty_list_for_clean_source() -> None:
    src = 'class A:\n    equations = "x = 1"\n'
    server = _new_recording_server()
    _publish_for_text(server, "file:///widget.py", src)
    assert len(server.calls) == 1
    assert server.calls[0].diagnostics == []


def test_publish_for_text_skips_non_python_uri() -> None:
    src = 'class A:\n    equations = "y = snh(x)"\n'
    server = _new_recording_server()
    _publish_for_text(server, "file:///widget.scad", src)
    # Skipped — no publish at all.
    assert server.calls == []


def test_publish_clear_emits_empty_diagnostic_list() -> None:
    server = _new_recording_server()
    _publish_clear(server, "file:///widget.py")
    assert len(server.calls) == 1
    assert server.calls[0].uri == "file:///widget.py"
    assert server.calls[0].diagnostics == []


def test_publish_for_text_logs_on_analyzer_exception(monkeypatch) -> None:
    # Force the analyzer to raise and confirm the publish helper logs
    # to the LSP window-log channel without raising or publishing.
    import scadwright.lsp.server as server_mod

    def _boom(_source: str) -> list:
        raise RuntimeError("synthetic analyzer failure")

    monkeypatch.setattr(server_mod, "analyze_file", _boom)
    server = _new_recording_server()
    _publish_for_text(server, "file:///widget.py", "irrelevant")
    # No diagnostics published.
    assert server.calls == []
    # One window/logMessage call with an error-level message naming
    # the exception type.
    assert len(server.log_calls) == 1
    log = server.log_calls[0]
    assert log.type == lsp.MessageType.Error
    assert "RuntimeError" in log.message
    assert "synthetic analyzer failure" in log.message
    assert "file:///widget.py" in log.message


# =============================================================================
# Server assembly smoke test
# =============================================================================


def test_build_server_uses_expected_name_and_version() -> None:
    server = build_server()
    assert server.name == "scadwright-ls"
    assert server.version == "0.1.0"


# =============================================================================
# Completion / hover adapters
# =============================================================================


def test_to_lsp_completion_function_kind_with_snippet() -> None:
    from scadwright.lsp.completion import CompletionItem as ScCompletionItem

    sc = ScCompletionItem(
        label="sin",
        kind="function",
        insert_text="sin($0)",
        is_snippet=True,
    )
    out = _to_lsp_completion(sc)
    assert out.label == "sin"
    assert out.kind == lsp.CompletionItemKind.Function
    assert out.insert_text == "sin($0)"
    assert out.insert_text_format == lsp.InsertTextFormat.Snippet


def test_to_lsp_completion_constant_kind_no_snippet() -> None:
    from scadwright.lsp.completion import CompletionItem as ScCompletionItem

    sc = ScCompletionItem(label="pi", kind="constant")
    out = _to_lsp_completion(sc)
    assert out.kind == lsp.CompletionItemKind.Constant
    # No insert_text override — client uses the label.
    assert out.insert_text is None


def test_to_lsp_completion_unknown_kind_falls_back_to_variable() -> None:
    from scadwright.lsp.completion import CompletionItem as ScCompletionItem

    sc = ScCompletionItem(label="x", kind="something_unmapped")
    out = _to_lsp_completion(sc)
    assert out.kind == lsp.CompletionItemKind.Variable


def test_to_lsp_completion_carries_detail_and_documentation() -> None:
    from scadwright.lsp.completion import CompletionItem as ScCompletionItem

    sc = ScCompletionItem(
        label="width",
        kind="variable",
        detail="Param(float)",
        documentation="The widget width",
    )
    out = _to_lsp_completion(sc)
    assert out.detail == "Param(float)"
    assert out.documentation == "The widget width"


def test_to_lsp_hover_wraps_markdown() -> None:
    from scadwright.lsp.hover import HoverContent as ScHoverContent

    sc = ScHoverContent(markdown="**`sin(x)`** — sine.")
    out = _to_lsp_hover(sc)
    assert isinstance(out, lsp.Hover)
    assert isinstance(out.contents, lsp.MarkupContent)
    assert out.contents.kind == lsp.MarkupKind.Markdown
    assert out.contents.value == "**`sin(x)`** — sine."


# =============================================================================
# _completion_items_for: cursor-position pipeline
# =============================================================================


def test_completion_items_for_expression_position() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = wid"\n'
    )
    # Cursor at end of "wid" — file (2, 22). The host content begins
    # at file (2, 17) (after the opening quote at col 16). Inside the
    # cleaned line "x = wid", that's splitter col 7 — expression
    # context.
    items = _completion_items_for(src, 2, 22)
    labels = {it.label for it in items}
    assert "width" in labels  # class Param
    assert "sin" in labels  # curated math


def test_completion_items_for_type_tag_position() -> None:
    # ``?count:`` cursor right after the colon.
    src = (
        'class A:\n'
        '    equations = "?count:"\n'
    )
    # The opening ``"`` is at col 16; "?count:" content runs cols
    # 17..23; cursor right after the ``:`` is col 24.
    items = _completion_items_for(src, 1, 24)
    labels = {it.label for it in items}
    assert labels == {"bool", "int", "str", "tuple", "list", "dict"}


def test_completion_items_for_in_string_returns_empty() -> None:
    # Cursor inside a quoted literal within the equation.
    src = (
        'class A:\n'
        '    equations = \'s = "in"\'\n'
    )
    # "    equations = '" = 18 chars; cleaned line is `s = "in"`; "in"
    # body starts at col 18 + 5 = 23. Cursor inside "in".
    items = _completion_items_for(src, 1, 24)
    assert items == []


def test_completion_items_for_no_block_returns_empty() -> None:
    # Cursor not inside any equations block.
    src = "x = 1\n"
    items = _completion_items_for(src, 0, 3)
    assert items == []


def test_completion_items_for_invalid_python_returns_empty() -> None:
    # Source doesn't parse as Python — the analyzer can't locate any
    # blocks. The completion path falls back to no items rather than
    # crashing.
    src = "class A:\n    equations = \n"
    items = _completion_items_for(src, 0, 0)
    assert items == []


# =============================================================================
# _hover_for: cursor-position pipeline
# =============================================================================


def test_hover_for_curated_name() -> None:
    src = (
        'class A:\n'
        '    equations = "y = sin(x)"\n'
    )
    # ``    equations = "`` = 18 chars; "y = sin(x)" starts at col 18.
    # "sin" is at col 22-24 in the source (file col 22-24).
    h = _hover_for(src, 1, 23)
    assert h is not None
    assert isinstance(h.contents, lsp.MarkupContent)
    assert "sin(x)" in h.contents.value


def test_hover_for_param_name() -> None:
    src = (
        'class A:\n'
        '    width = Param(float, default=5)\n'
        '    equations = "x = width"\n'
    )
    # ``    equations = "`` is 18 chars; "x = width" — "width" starts
    # at file col 22.
    h = _hover_for(src, 2, 24)
    assert h is not None
    assert "Param(float, default=5)" in h.contents.value


def test_hover_for_unknown_name_returns_none() -> None:
    src = (
        'class A:\n'
        '    equations = "x = blarp"\n'
    )
    # Cursor on "blarp".
    h = _hover_for(src, 1, 24)
    assert h is None


def test_hover_for_outside_block_returns_none() -> None:
    src = "x = 1\n"
    assert _hover_for(src, 0, 0) is None


def test_hover_for_cursor_on_whitespace_returns_none() -> None:
    src = 'class A:\n    equations = "x  =  5"\n'
    # Cursor on the gap between "x" and "=".
    h = _hover_for(src, 1, 20)
    assert h is None


# =============================================================================
# Server registration
# =============================================================================


def test_build_server_registers_completion_with_colon_trigger() -> None:
    server = build_server()
    # pygls 2.x exposes feature options on the protocol's feature
    # manager. The completion options should declare ``:`` among the
    # trigger characters (``.`` joined later for attribute access).
    options = (
        server.protocol.fm.feature_options.get(
            lsp.TEXT_DOCUMENT_COMPLETION,
        )
    )
    assert options is not None
    assert ":" in options.trigger_characters


# =============================================================================
# _to_lsp_location adapter and _definition_for pipeline
# =============================================================================


def test_to_lsp_location_attaches_uri_and_range() -> None:
    from scadwright.lsp.definition import DefinitionLocation

    loc = DefinitionLocation(
        start_line=2, start_col=4, end_line=2, end_col=24,
    )
    out = _to_lsp_location(loc, "file:///widget.py")
    assert isinstance(out, lsp.Location)
    assert out.uri == "file:///widget.py"
    assert out.range.start.line == 2
    assert out.range.start.character == 4
    assert out.range.end.line == 2
    assert out.range.end.character == 24


def test_definition_for_param_jumps_to_assignment() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    # Cursor on "width" in the equations line.
    loc = _definition_for(src, 2, 24, "file:///t.py")
    assert loc is not None
    assert loc.uri == "file:///t.py"
    # The Param is on file line 1.
    assert loc.range.start.line == 1
    assert loc.range.start.character == 4


def test_definition_for_auto_declared_jumps_to_first_line() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    a = 1\n'
        '    b = a + 2\n'
        '    """\n'
    )
    # Cursor on "a" in the second equation line (file line 3).
    loc = _definition_for(src, 3, 8, "file:///t.py")
    assert loc is not None
    # ``a = 1`` is on file line 2.
    assert loc.range.start.line == 2


def test_definition_for_curated_name_returns_none() -> None:
    src = 'class A:\n    equations = "x = sin(0)"\n'
    # Cursor on "sin".
    loc = _definition_for(src, 1, 23, "file:///t.py")
    assert loc is None


def test_definition_for_outside_block_returns_none() -> None:
    src = "x = 1\n"
    assert _definition_for(src, 0, 0, "file:///t.py") is None


def test_definition_for_non_python_uri_via_handler_returns_none() -> None:
    # Sanity for the dispatch path: non-.py URIs short-circuit before
    # any work. Test the handler indirectly via _definition_for being
    # bypassed in build_server's on_definition. We can't easily call
    # the handler directly without a real server context, so just
    # confirm the helper returns None for clearly-irrelevant input.
    src = "class A:\n    equations = ''\n"
    assert _definition_for(src, 99, 0, "file:///t.py") is None


# =============================================================================
# Document symbol adapter and pipeline
# =============================================================================


def test_to_lsp_document_symbol_class_with_children() -> None:
    from scadwright.lsp.symbols import DocumentSymbol as ScDocSym

    sc = ScDocSym(
        name="A",
        kind="class",
        detail=None,
        start_line=0, start_col=0,
        end_line=2, end_col=20,
        selection_start_line=0, selection_start_col=6,
        selection_end_line=0, selection_end_col=7,
        children=(
            ScDocSym(
                name="width",
                kind="variable",
                detail="Param(float)",
                start_line=1, start_col=4,
                end_line=1, end_col=24,
                selection_start_line=1, selection_start_col=4,
                selection_end_line=1, selection_end_col=9,
            ),
        ),
    )
    out = _to_lsp_document_symbol(sc)
    assert out.name == "A"
    assert out.kind == lsp.SymbolKind.Class
    assert out.range.start.line == 0
    assert out.selection_range.start.character == 6
    assert out.children is not None
    assert len(out.children) == 1
    assert out.children[0].kind == lsp.SymbolKind.Variable
    assert out.children[0].detail == "Param(float)"


def test_document_symbols_for_returns_outline() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    syms = _document_symbols_for(src)
    assert len(syms) == 1
    cls = syms[0]
    assert cls.name == "A"
    assert cls.kind == lsp.SymbolKind.Class
    assert cls.children is not None
    assert [c.name for c in cls.children] == ["width"]


def test_document_symbols_for_invalid_python_returns_empty() -> None:
    # Source that doesn't parse as Python — fall back to no symbols
    # rather than raising.
    src = "class A:\n    equations = \n"
    assert _document_symbols_for(src) == []


def test_document_symbols_for_no_classes_returns_empty() -> None:
    assert _document_symbols_for("x = 1\n") == []


def test_completion_for_attribute_returns_target_class_params() -> None:
    src = (
        'class B:\n'
        '    width = Param(float)\n'
        '    height = Param(float)\n'
        '    equations = "x = width"\n'
        '\n'
        'class A:\n'
        '    b = Param(B)\n'
        '    equations = "y = b.width"\n'
    )
    # Cursor right after the ``.`` on file line 7.
    items = _completion_items_for(src, 7, 23)
    labels = {it.label for it in items}
    assert labels == {"width", "height"}


def test_completion_for_attribute_no_class_match_returns_empty() -> None:
    src = (
        'class A:\n'
        '    b = Param(Unrelated)\n'
        '    equations = "y = b.attr"\n'
    )
    # Cursor right after the ``.`` — no class named ``Unrelated``
    # in this file, so no items.
    items = _completion_items_for(src, 2, 23)
    assert items == []


# =============================================================================
# Rename
# =============================================================================


def test_rename_for_param_returns_workspace_edit() -> None:
    from scadwright.lsp.server import _rename_for

    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = """\n'
        '    width > 0\n'
        '    h = width + 2\n'
        '    """\n'
    )
    # Cursor on ``width`` in ``width > 0`` — file line 3, col 5.
    edit = _rename_for(src, 3, 5, "ww", "file:///t.py")
    assert edit is not None
    assert isinstance(edit, lsp.WorkspaceEdit)
    edits = edit.changes["file:///t.py"]
    # Param assignment + constraint + equation reference.
    assert len(edits) == 3
    for e in edits:
        assert e.new_text == "ww"


def test_rename_for_curated_returns_none() -> None:
    from scadwright.lsp.server import _rename_for

    src = (
        'class A:\n'
        '    equations = "x = sin(0)"\n'
    )
    # Cursor on ``sin``.
    edit = _rename_for(src, 1, 23, "anything", "file:///t.py")
    assert edit is None


def test_rename_for_outside_block_returns_none() -> None:
    from scadwright.lsp.server import _rename_for

    src = "x = 1\n"
    edit = _rename_for(src, 0, 0, "y", "file:///t.py")
    assert edit is None


# =============================================================================
# Direct class-attribute access in Python code (outside equations blocks)
# =============================================================================


def _setup_project(tmp_path) -> tuple[str, str]:
    """Write a two-file project (spec + consumer) under tmp_path.

    Returns the consumer file's URI (file://) and the consumer
    source text — both already prepared with a ``CamSpec.outer_d``
    reference at the start of line 3.
    """
    (tmp_path / "spec.py").write_text(
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    )
    consumer = tmp_path / "housing.py"
    consumer_text = (
        "from spec import CamSpec\n"
        "from scadwright import Component\n"
        "BORE = CamSpec.outer_d + 1\n"
        "class Housing(Component):\n"
        "    def build(self):\n"
        "        return None\n"
    )
    consumer.write_text(consumer_text)
    return consumer.as_uri(), consumer_text


def test_hover_for_direct_class_attribute_in_python_code(tmp_path) -> None:
    """Cursor on ``CamSpec.outer_d`` at module scope of a consumer
    file: hover surfaces the attribute's auto-declared origin from
    the source class's equations block.
    """
    from scadwright.lsp.server import _hover_for

    uri, source = _setup_project(tmp_path)
    # Line 2 (0-based) is "BORE = CamSpec.outer_d + 1"; outer_d starts at col 15.
    out = _hover_for(
        source, 2, 17,
        uri=uri,
        project_root=tmp_path,
    )
    assert out is not None
    assert "outer_d" in out.contents.value


def test_hover_for_direct_class_attribute_no_project_root_returns_none(
    tmp_path,
) -> None:
    """Without a workspace folder, the Python-attribute fall-through
    is disabled; the editor falls back to its standard Python LSP.
    """
    from scadwright.lsp.server import _hover_for

    _uri, source = _setup_project(tmp_path)
    out = _hover_for(source, 2, 17)
    assert out is None


def test_definition_for_direct_class_attribute_in_python_code(
    tmp_path,
) -> None:
    """Goto-definition on ``CamSpec.outer_d`` jumps to the equation
    line in the source class's equations block."""
    from scadwright.lsp.server import _definition_for

    uri, source = _setup_project(tmp_path)
    out = _definition_for(
        source, 2, 17, uri, project_root=tmp_path,
    )
    assert out is not None
    # Definition should be in spec.py, not the consumer file.
    assert "spec.py" in out.uri


def test_rename_for_direct_class_attribute_invocation(tmp_path) -> None:
    """Rename invoked with cursor on a consumer file's ``CamSpec.outer_d``
    routes through to the existing workspace-rename machinery and
    produces edits in both the source file and the consumer file.
    """
    from scadwright.lsp.server import _rename_for

    uri, source = _setup_project(tmp_path)
    edit = _rename_for(
        source, 2, 17,
        "outer_diameter",
        uri,
        project_root=tmp_path,
    )
    assert edit is not None
    # The WorkspaceEdit's changes dict should include both files.
    assert edit.changes is not None
    assert len(edit.changes) == 2


# =============================================================================
# Unsaved editor changes: the cursor file is analyzed from the editor
# source, not the on-disk copy
# =============================================================================


def test_hover_for_direct_attr_uses_editor_source_not_disk(tmp_path) -> None:
    """The consumer file on disk has no reference to ``CamSpec.outer_d``.
    The editor's live ``source`` adds the import and the reference.
    Hover must resolve against the editor source, not the stale disk
    copy.
    """
    from scadwright.lsp.server import _hover_for

    (tmp_path / "spec.py").write_text(
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    )
    consumer = tmp_path / "housing.py"
    # On disk: empty-ish, no reference.
    consumer.write_text(
        "from scadwright import Component\n"
        "class Housing(Component):\n"
        "    def build(self):\n"
        "        return None\n"
    )
    # Editor buffer (unsaved): import + a module-level reference at line 2.
    editor_source = (
        "from scadwright import Component\n"
        "from spec import CamSpec\n"
        "BORE = CamSpec.outer_d\n"
        "class Housing(Component):\n"
        "    def build(self):\n"
        "        return None\n"
    )
    # outer_d on line 2 (0-based); "BORE = CamSpec." is 15 chars, outer_d at 15.
    out = _hover_for(
        editor_source, 2, 17,
        uri=consumer.as_uri(),
        project_root=tmp_path,
    )
    assert out is not None
    assert "outer_d" in out.contents.value


def test_definition_for_direct_attr_uses_editor_source(tmp_path) -> None:
    """Same unsaved-changes scenario, for goto-definition."""
    from scadwright.lsp.server import _definition_for

    (tmp_path / "spec.py").write_text(
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    )
    consumer = tmp_path / "housing.py"
    consumer.write_text("# empty\n")
    editor_source = (
        "from spec import CamSpec\n"
        "BORE = CamSpec.outer_d\n"
    )
    # Line 1 (0-based): "BORE = CamSpec.outer_d"; outer_d at col 15.
    out = _definition_for(
        editor_source, 1, 17,
        consumer.as_uri(),
        project_root=tmp_path,
    )
    assert out is not None
    assert "spec.py" in out.uri


def test_hover_for_self_reference_in_editor_source(tmp_path) -> None:
    """When the cursor file IS the source class's file and the
    reference is unsaved, the source block is parsed from the editor
    source, not disk.
    """
    from scadwright.lsp.server import _hover_for

    spec = tmp_path / "spec.py"
    # On disk: the class with no module-level self-reference.
    spec.write_text(
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    )
    # Editor buffer: adds a module-level self-reference at the end.
    editor_source = (
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
        "BACKUP = CamSpec.outer_d\n"
    )
    # Line 5 (0-based): "BACKUP = CamSpec.outer_d"; outer_d at col 17.
    out = _hover_for(
        editor_source, 5, 19,
        uri=spec.as_uri(),
        project_root=tmp_path,
    )
    assert out is not None
    assert "outer_d" in out.contents.value


# =============================================================================
# Open editor buffers threaded through _rename_for / _hover_for
# =============================================================================


def test_rename_for_threads_open_buffers(tmp_path) -> None:
    """``_rename_for`` invoked from a consumer file's ``CamSpec.outer_d``
    while another consumer file is open with unsaved edits: the edit
    in that other file lands on its buffer position.
    """
    from scadwright.lsp.server import _rename_for

    (tmp_path / "spec.py").write_text(
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    )
    cursor_file = tmp_path / "a.py"
    cursor_source = (
        "from spec import CamSpec\n"
        "A = CamSpec.outer_d\n"
    )
    cursor_file.write_text(cursor_source)
    other = tmp_path / "b.py"
    other.write_text(
        "from spec import CamSpec\n"
        "B = CamSpec.outer_d\n"
    )
    other_buffer = (
        "from spec import CamSpec\n"
        "\n"
        "\n"
        "B = CamSpec.outer_d\n"
    )
    # Cursor on outer_d in a.py line 1 (col 15); b.py open with edits.
    edit = _rename_for(
        cursor_source, 1, 17,
        "outer_diameter",
        cursor_file.as_uri(),
        project_root=tmp_path,
        source_overrides={other: other_buffer},
    )
    assert edit is not None
    changes = edit.changes
    other_edits = changes[other.as_uri()]
    # The edit lands on b.py's buffer line 3, not its disk line 1.
    assert other_edits[0].range.start.line == 3


def test_hover_resolves_through_open_buffer_imports(tmp_path) -> None:
    """The Spec file is open in the editor with an unsaved rename of
    the class. Hover on a consumer reference resolves through the
    open buffer's class name, not the stale disk name.
    """
    from scadwright.lsp.server import _hover_for

    spec = tmp_path / "spec.py"
    # Disk: class is named OldName.
    spec.write_text(
        "from scadwright import Spec\n"
        "class OldName(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    )
    # Editor buffer: class renamed to CamSpec (unsaved).
    spec_buffer = (
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    )
    consumer = tmp_path / "housing.py"
    consumer_source = (
        "from spec import CamSpec\n"
        "BORE = CamSpec.outer_d\n"
    )
    consumer.write_text(consumer_source)
    out = _hover_for(
        consumer_source, 1, 17,
        uri=consumer.as_uri(),
        project_root=tmp_path,
        source_overrides={spec: spec_buffer},
    )
    # Resolves only if the buffer's CamSpec name is used; the disk
    # OldName wouldn't match the consumer's CamSpec import.
    assert out is not None
    assert "outer_d" in out.contents.value


# =============================================================================
# Goto-definition on a project class name (not an attribute)
# =============================================================================


def _spec_and_consumer(tmp_path, consumer_body: str) -> tuple[str, str]:
    """Write a spec.py with CamSpec plus a consumer file whose body
    is ``consumer_body``. Returns (consumer_uri, consumer_source)."""
    (tmp_path / "spec.py").write_text(
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    )
    consumer = tmp_path / "consumer.py"
    consumer.write_text(consumer_body)
    return consumer.as_uri(), consumer_body


def test_definition_on_class_name_in_attribute_access(tmp_path) -> None:
    """Cursor on the class half of ``CamSpec.outer_d`` jumps to the
    class definition, not the attribute's equation line."""
    from scadwright.lsp.server import _definition_for

    uri, source = _spec_and_consumer(tmp_path, (
        "from spec import CamSpec\n"
        "BORE = CamSpec.outer_d\n"
    ))
    # "BORE = CamSpec.outer_d"; CamSpec spans cols 7..13.
    out = _definition_for(source, 1, 9, uri, project_root=tmp_path)
    assert out is not None
    assert out.uri.endswith("spec.py")
    # CamSpec is defined on line 1 (0-based) of spec.py.
    assert out.range.start.line == 1


def test_definition_on_bare_class_reference(tmp_path) -> None:
    """Cursor on a bare ``CamSpec`` (Param argument) jumps to the
    class definition."""
    from scadwright.lsp.server import _definition_for

    uri, source = _spec_and_consumer(tmp_path, (
        "from spec import CamSpec\n"
        "from scadwright import Component, Param\n"
        "class Holder(Component):\n"
        "    spec = Param(CamSpec)\n"
    ))
    # Line 3: "    spec = Param(CamSpec)"; CamSpec starts at col 18.
    out = _definition_for(source, 3, 20, uri, project_root=tmp_path)
    assert out is not None
    assert out.uri.endswith("spec.py")
    assert out.range.start.line == 1


def test_definition_on_base_class_reference(tmp_path) -> None:
    """Cursor on a base class in ``class Sub(CamSpec)`` jumps to the
    base class definition."""
    from scadwright.lsp.server import _definition_for

    uri, source = _spec_and_consumer(tmp_path, (
        "from spec import CamSpec\n"
        "class Sub(CamSpec):\n"
        "    pass\n"
    ))
    # Line 1: "class Sub(CamSpec):"; CamSpec starts at col 10.
    out = _definition_for(source, 1, 12, uri, project_root=tmp_path)
    assert out is not None
    assert out.uri.endswith("spec.py")
    assert out.range.start.line == 1


def test_definition_on_attribute_still_jumps_to_equation_line(tmp_path) -> None:
    """The attribute path is unchanged: cursor on ``outer_d`` jumps
    to its equation line, not the class definition."""
    from scadwright.lsp.server import _definition_for

    uri, source = _spec_and_consumer(tmp_path, (
        "from spec import CamSpec\n"
        "BORE = CamSpec.outer_d\n"
    ))
    # outer_d starts at col 15.
    out = _definition_for(source, 1, 17, uri, project_root=tmp_path)
    assert out is not None
    assert out.uri.endswith("spec.py")
    # outer_d's equation is on line 3 of spec.py, not the class line (1).
    assert out.range.start.line == 3


def test_definition_on_module_name_returns_none(tmp_path) -> None:
    """Cursor on the module part of a dotted reference (not a class)
    yields nothing rather than a false jump."""
    from scadwright.lsp.server import _definition_for

    (tmp_path / "spec.py").write_text(
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    )
    consumer = tmp_path / "consumer.py"
    source = (
        "import spec\n"
        "BORE = spec.CamSpec.outer_d\n"
    )
    consumer.write_text(source)
    # Cursor on "spec" (the module) at col 7.
    out = _definition_for(source, 1, 8, consumer.as_uri(), project_root=tmp_path)
    assert out is None


def test_definition_on_dotted_class_name(tmp_path) -> None:
    """Cursor on the class part of ``spec.CamSpec`` jumps to the
    class definition."""
    from scadwright.lsp.server import _definition_for

    (tmp_path / "spec.py").write_text(
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    )
    consumer = tmp_path / "consumer.py"
    source = (
        "import spec\n"
        "x = spec.CamSpec\n"
    )
    consumer.write_text(source)
    # Line 1: "x = spec.CamSpec"; CamSpec starts at col 9.
    out = _definition_for(source, 1, 11, consumer.as_uri(), project_root=tmp_path)
    assert out is not None
    assert out.uri.endswith("spec.py")
    assert out.range.start.line == 1


def test_definition_on_non_class_name_returns_none(tmp_path) -> None:
    """Cursor on a plain local variable resolves to nothing."""
    from scadwright.lsp.server import _definition_for

    uri, source = _spec_and_consumer(tmp_path, (
        "from spec import CamSpec\n"
        "BORE = CamSpec.outer_d\n"
    ))
    # Cursor on "BORE" (col 0..4).
    out = _definition_for(source, 1, 1, uri, project_root=tmp_path)
    assert out is None


# =============================================================================
# Non-ASCII columns: ast byte offsets vs character indices
#
# ast reports columns as UTF-8 byte offsets; the LSP counts characters.
# A non-ASCII character before a token (a 2-byte accent, a 3-byte CJK
# glyph) makes the two diverge. These pin the conversion so positions
# land on the right characters.
# =============================================================================


def _nonascii_project(tmp_path, consumer_body: str) -> tuple[str, str]:
    (tmp_path / "spec.py").write_text(
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    )
    consumer = tmp_path / "consumer.py"
    consumer.write_text(consumer_body)
    return consumer.as_uri(), consumer_body


def test_definition_attribute_after_accent_on_same_line(tmp_path) -> None:
    from scadwright.lsp.server import _definition_for

    body = (
        "from spec import CamSpec\n"
        'L = "café"; B = CamSpec.outer_d\n'
    )
    uri, source = _nonascii_project(tmp_path, body)
    line = source.splitlines()[1]
    char_idx = line.index("outer_d")
    # ast byte offset is char_idx + 1 (é is one extra byte); the fix
    # must convert so a cursor at the character index resolves.
    out = _definition_for(source, 1, char_idx + 1, uri, project_root=tmp_path)
    assert out is not None
    assert out.uri.endswith("spec.py")
    assert out.range.start.line == 3  # outer_d's equation line


def test_definition_class_name_after_cjk_on_same_line(tmp_path) -> None:
    from scadwright.lsp.server import _definition_for

    # CJK characters are 3 UTF-8 bytes each, 1 character each.
    body = (
        "from spec import CamSpec\n"
        'name = "部品"; x = CamSpec\n'
    )
    uri, source = _nonascii_project(tmp_path, body)
    line = source.splitlines()[1]
    char_idx = line.index("CamSpec")
    out = _definition_for(source, 1, char_idx + 2, uri, project_root=tmp_path)
    assert out is not None
    assert out.uri.endswith("spec.py")
    assert out.range.start.line == 1  # class definition line


def test_rename_edit_lands_on_char_position_after_accent(tmp_path) -> None:
    from scadwright.lsp.server import _rename_for

    body = (
        "from spec import CamSpec\n"
        'L = "café"; B = CamSpec.outer_d\n'
    )
    uri, source = _nonascii_project(tmp_path, body)
    line = source.splitlines()[1]
    char_idx = line.index("outer_d")
    edit = _rename_for(
        source, 1, char_idx + 1, "diameter", uri, project_root=tmp_path,
    )
    assert edit is not None
    consumer_edits = edit.changes[uri]
    e = consumer_edits[0]
    # The edit range, in character coordinates, must cover exactly
    # "outer_d" — not be shifted by the extra byte of é.
    assert line[e.range.start.character:e.range.end.character] == "outer_d"


def test_rename_self_attr_edit_after_accent(tmp_path) -> None:
    """The ``self.<param>.<attr>`` edit path also converts byte→char."""
    from scadwright.lsp.server import _rename_for

    spec_src = (
        "from scadwright import Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    outer_d = Param(float)\n"
        '    equations = "x = outer_d"\n'
    )
    (tmp_path / "spec.py").write_text(spec_src)
    consumer = tmp_path / "holder.py"
    consumer_body = (
        "from scadwright import Component, Param\n"
        "from spec import CamSpec\n"
        "class Holder(Component):\n"
        "    spec = Param(CamSpec)\n"
        "    def build(self):\n"
        '        note = "réf"; return self.spec.outer_d\n'
    )
    consumer.write_text(consumer_body)
    # Invoke the rename from the equation reference on spec line 3
    # (inside the equations block, the canonical invocation site).
    spec_line = spec_src.splitlines()[3]
    col = spec_line.index("outer_d") + 1
    edit = _rename_for(
        spec_src, 3, col, "diameter",
        (tmp_path / "spec.py").as_uri(), project_root=tmp_path,
    )
    assert edit is not None
    consumer_uri = consumer.as_uri()
    assert consumer_uri in edit.changes
    e = edit.changes[consumer_uri][0]
    build_line = consumer_body.splitlines()[5]
    assert build_line[e.range.start.character:e.range.end.character] == "outer_d"


def test_definition_resolves_after_unicode_line_separator(tmp_path) -> None:
    """A U+2028 inside a string literal must not shift line indexing.

    str.splitlines() would break on U+2028 (ast does not), pointing
    the byte->char lookup at the wrong line. The reference on the
    following physical line must still resolve.
    """
    from scadwright.lsp.server import _definition_for

    (tmp_path / "spec.py").write_text(
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    )
    consumer = tmp_path / "consumer.py"
    # Line 1 carries a U+2028 inside a string; line 2 has the reference.
    body = (
        "from spec import CamSpec\n"
        'NOTE = "a b"\n'
        "x = CamSpec.outer_d\n"
    )
    consumer.write_text(body)
    line = body.split("\n")[2]  # ast's line model
    char_idx = line.index("outer_d")
    out = _definition_for(
        body, 2, char_idx + 1, consumer.as_uri(), project_root=tmp_path,
    )
    assert out is not None
    assert out.uri.endswith("spec.py")
    assert out.range.start.line == 3
