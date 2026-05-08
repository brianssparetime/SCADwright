"""Tests for the LSP goto-definition resolver.

Covers Param-declaration resolution (using assign-position info
captured by the analyzer), auto-declared bare-Name resolution
(using whole-block first-occurrence lookup), and the cases where
goto-definition correctly returns ``None`` (curated names,
unknown names, non-expression contexts).
"""

from __future__ import annotations

from scadwright.lsp.analyze import find_equations_blocks
from scadwright.lsp.context import ContextKind
from scadwright.lsp.definition import (
    DefinitionLocation,
    build_definition_location,
)


def _block(src: str):
    [block] = find_equations_blocks(src)
    return block


# =============================================================================
# Param resolution
# =============================================================================


def test_param_definition_returns_assignment_range() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    block = _block(src)
    loc = build_definition_location("width", ContextKind.EXPRESSION, block)
    assert loc is not None
    # Source line 1, cols 4..24 cover ``width = Param(float)``.
    assert loc.start_line == 1
    assert loc.start_col == 4
    src_line = src.splitlines()[loc.start_line]
    assert (
        src_line[loc.start_col:loc.end_col]
        == "width = Param(float)"
    )


def test_param_definition_for_ann_assign() -> None:
    src = (
        'class A:\n'
        '    width: float = Param(float, default=5)\n'
        '    equations = "x = width"\n'
    )
    block = _block(src)
    loc = build_definition_location("width", ContextKind.EXPRESSION, block)
    assert loc is not None
    src_line = src.splitlines()[loc.start_line]
    assert (
        src_line[loc.start_col:loc.end_col]
        == "width: float = Param(float, default=5)"
    )


# =============================================================================
# Auto-declared resolution
# =============================================================================


def test_auto_declared_definition_returns_first_line() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    a = 1\n'
        '    b = a + 2\n'
        '    """\n'
    )
    block = _block(src)
    loc = build_definition_location("a", ContextKind.EXPRESSION, block)
    assert loc is not None
    # ``a = 1`` lives on file line 2 (the ``"""`` is line 1).
    assert loc.start_line == 2


def test_auto_declared_resolves_from_anywhere_in_block() -> None:
    # The cursor's position doesn't matter for goto-def (unlike
    # auto_declared_origins_before which is cursor-relative).
    src = (
        'class A:\n'
        '    equations = """\n'
        '    a = 1\n'
        '    b = c + 2\n'   # references c BEFORE c is declared
        '    c = 3\n'        # c first declared here
        '    """\n'
    )
    block = _block(src)
    loc = build_definition_location("c", ContextKind.EXPRESSION, block)
    assert loc is not None
    # ``c = 3`` is on file line 4.
    assert loc.start_line == 4


def test_auto_declared_definition_first_occurrence_wins() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    x = 1\n'
        '    x = 2\n'
        '    """\n'
    )
    block = _block(src)
    loc = build_definition_location("x", ContextKind.EXPRESSION, block)
    assert loc is not None
    # First occurrence on file line 2.
    assert loc.start_line == 2


def test_auto_declared_definition_across_hosts() -> None:
    src = (
        'class A:\n'
        '    equations = [\n'
        '        "a = 1",\n'
        '        "b = a + 2",\n'
        '    ]\n'
    )
    block = _block(src)
    loc = build_definition_location("a", ContextKind.EXPRESSION, block)
    assert loc is not None
    # ``a = 1`` is the content of the first list element on file line 2.
    assert loc.start_line == 2


# =============================================================================
# Resolution priority and edge cases
# =============================================================================


def test_param_takes_precedence_over_auto_declared() -> None:
    # ``width`` is a Param AND appears as a bare-Name target inside
    # the equations. Goto-def should return the Param assignment, not
    # the equation line.
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = """\n'
        '    width = 5\n'
        '    h = width + 1\n'
        '    """\n'
    )
    block = _block(src)
    loc = build_definition_location("width", ContextKind.EXPRESSION, block)
    assert loc is not None
    # Line 1 (the Param assignment), not line 3 (the equation).
    assert loc.start_line == 1


def test_curated_name_returns_none() -> None:
    src = (
        'class A:\n'
        '    equations = "x = sin(0)"\n'
    )
    block = _block(src)
    assert build_definition_location(
        "sin", ContextKind.EXPRESSION, block,
    ) is None


def test_unknown_name_returns_none() -> None:
    src = (
        'class A:\n'
        '    equations = "x = 1"\n'
    )
    block = _block(src)
    assert build_definition_location(
        "completely_unknown", ContextKind.EXPRESSION, block,
    ) is None


def test_non_expression_context_returns_none() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    block = _block(src)
    # Even with a real Param, goto-def doesn't fire in TYPE_TAG /
    # STRING / COMMENT contexts.
    for ctx in (
        ContextKind.TYPE_TAG, ContextKind.STRING, ContextKind.COMMENT,
    ):
        assert build_definition_location("width", ctx, block) is None


# =============================================================================
# DefinitionLocation shape
# =============================================================================


def test_definition_location_is_immutable() -> None:
    loc = DefinitionLocation(
        start_line=0, start_col=0, end_line=0, end_col=1,
    )
    try:
        loc.start_line = 9  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("DefinitionLocation should be frozen")
