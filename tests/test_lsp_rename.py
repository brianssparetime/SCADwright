"""Tests for the same-file rename refactoring helper.

Covers Param-target rename (assignment + every reference),
auto-declared-target rename, multi-occurrence on a single line,
adjustment LHS handling, refusal cases (curated names, type-tag
names, invalid new names, parse failures), and the position
ranges of emitted edits.
"""

from __future__ import annotations

from scadwright.lsp.analyze import find_equations_blocks
from scadwright.lsp.rename import (
    TextEdit,
    build_rename_edits,
    is_renameable_target,
    is_valid_new_name,
)


def _block(src: str):
    [block] = find_equations_blocks(src)
    return block


# =============================================================================
# is_valid_new_name
# =============================================================================


def test_valid_new_name_simple_identifier() -> None:
    assert is_valid_new_name("width")
    assert is_valid_new_name("_private")
    assert is_valid_new_name("widthX2")


def test_invalid_new_name_empty_or_starting_with_digit() -> None:
    assert not is_valid_new_name("")
    assert not is_valid_new_name("2width")
    assert not is_valid_new_name("with-dash")


def test_invalid_new_name_curated_collision() -> None:
    # Renaming TO a curated name is forbidden — the resolver's
    # reserved-name check would reject the result.
    assert not is_valid_new_name("sin")
    assert not is_valid_new_name("pi")
    assert not is_valid_new_name("len")


def test_invalid_new_name_type_tag_collision() -> None:
    assert not is_valid_new_name("bool")
    assert not is_valid_new_name("int")
    assert not is_valid_new_name("dict")


# =============================================================================
# is_renameable_target
# =============================================================================


def test_renameable_target_class_param() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    block = _block(src)
    assert is_renameable_target("width", block)


def test_renameable_target_auto_declared() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    a = 1\n'
        '    """\n'
    )
    block = _block(src)
    assert is_renameable_target("a", block)


def test_curated_name_not_renameable() -> None:
    src = (
        'class A:\n'
        '    equations = "x = sin(0)"\n'
    )
    block = _block(src)
    assert not is_renameable_target("sin", block)


def test_unknown_name_not_renameable() -> None:
    src = (
        'class A:\n'
        '    equations = "x = 1"\n'
    )
    block = _block(src)
    assert not is_renameable_target("nothing_here", block)


# =============================================================================
# build_rename_edits — Param target
# =============================================================================


def test_param_rename_emits_edit_per_occurrence() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = """\n'
        '    width > 0\n'
        '    h = width + 2\n'
        '    """\n'
    )
    block = _block(src)
    edits = build_rename_edits(block, "width", "ww")
    assert edits is not None
    # Three edits: Param assignment + two equation references.
    assert len(edits) == 3


def test_param_rename_assignment_edit_covers_just_the_name() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    block = _block(src)
    edits = build_rename_edits(block, "width", "ww")
    assert edits is not None
    # The Param assignment edit is on file line 1, cols 4..9.
    assignment_edit = next(
        e for e in edits if e.start_line == 1 and e.start_col == 4
    )
    assert assignment_edit.end_line == 1
    assert assignment_edit.end_col == 4 + len("width")
    assert assignment_edit.new_text == "ww"


def test_param_rename_equation_reference_edit() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    block = _block(src)
    edits = build_rename_edits(block, "width", "ww")
    assert edits is not None
    # Find the equation-side edit (line 2 in this file).
    eq_edits = [e for e in edits if e.start_line == 2]
    assert len(eq_edits) == 1
    src_line = src.splitlines()[2]
    assert (
        src_line[eq_edits[0].start_col:eq_edits[0].end_col] == "width"
    )


def test_param_rename_multiple_uses_one_line() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width + width"\n'
    )
    block = _block(src)
    edits = build_rename_edits(block, "width", "ww")
    assert edits is not None
    # Param + two equation references = 3 edits.
    assert len(edits) == 3


# =============================================================================
# build_rename_edits — auto-declared target
# =============================================================================


def test_auto_declared_rename_no_param_edit() -> None:
    src = (
        'class A:\n'
        '    equations = """\n'
        '    a = 1\n'
        '    b = a + 2\n'
        '    """\n'
    )
    block = _block(src)
    edits = build_rename_edits(block, "a", "alpha")
    assert edits is not None
    # No Param assignment to rename — just the two `a` occurrences.
    assert len(edits) == 2
    # All edits replace with "alpha".
    assert all(e.new_text == "alpha" for e in edits)


# =============================================================================
# Adjustment LHS handling
# =============================================================================


def test_rename_includes_adjustment_lhs() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = """\n'
        '    width > 0\n'
        '    width += 1  # bump\n'
        '    """\n'
    )
    block = _block(src)
    edits = build_rename_edits(block, "width", "ww")
    assert edits is not None
    # Param assignment + constraint reference + adjustment LHS = 3 edits.
    assert len(edits) == 3


def test_rename_dedupes_comma_broadcast_adjustment_lhs() -> None:
    # ``x, y += 1`` produces two ``ParsedAdjustment`` entries (one
    # per broadcast target) that share a source line. The LHS-walk
    # dedupe in ``build_rename_edits`` should run
    # ``_edits_from_adjustment_lhs`` once for that line, producing
    # a single edit for the target's LHS occurrence — not two.
    src = (
        'class A:\n'
        '    x = Param(float)\n'
        '    y = Param(float)\n'
        '    equations = """\n'
        '    x, y += 1  # bump both\n'
        '    """\n'
    )
    block = _block(src)
    edits = build_rename_edits(block, "x", "x_renamed")
    assert edits is not None
    # Param assignment + single LHS occurrence (dedupe wins).
    # The RHS (``1``) doesn't reference x.
    assert len(edits) == 2
    eq_edits = [e for e in edits if e.start_line == 4]
    assert len(eq_edits) == 1


# =============================================================================
# Refusal cases
# =============================================================================


def test_curated_target_returns_none() -> None:
    src = (
        'class A:\n'
        '    equations = "x = sin(0)"\n'
    )
    block = _block(src)
    assert build_rename_edits(block, "sin", "newname") is None


def test_invalid_new_name_returns_none() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = "x = width"\n'
    )
    block = _block(src)
    assert build_rename_edits(block, "width", "2bad") is None
    assert build_rename_edits(block, "width", "sin") is None
    assert build_rename_edits(block, "width", "") is None


def test_parse_failure_returns_none() -> None:
    # Equations don't validate (chained `=`); refuse to emit edits.
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = """\n'
        '    width = h = 5\n'
        '    """\n'
    )
    block = _block(src)
    assert build_rename_edits(block, "width", "ww") is None


# =============================================================================
# TextEdit shape
# =============================================================================


def test_text_edit_is_immutable() -> None:
    e = TextEdit(
        start_line=0, start_col=0, end_line=0, end_col=1, new_text="x",
    )
    try:
        e.new_text = "y"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("TextEdit should be frozen")


# =============================================================================
# Empty / degenerate cases
# =============================================================================


def test_empty_equations_param_only_rename() -> None:
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = ""\n'
    )
    block = _block(src)
    edits = build_rename_edits(block, "width", "ww")
    # Param assignment edit only; no equation references.
    assert edits is not None
    assert len(edits) == 1
    assert edits[0].start_line == 1


def test_no_occurrences_returns_empty_list() -> None:
    # A name that's auto-declared but only referenced once on its
    # declaring line; rename emits the single edit on that line.
    src = (
        'class A:\n'
        '    equations = "lonely = 5"\n'
    )
    block = _block(src)
    edits = build_rename_edits(block, "lonely", "renamed")
    assert edits is not None
    assert len(edits) == 1


def test_rename_target_across_multiple_hosts_in_same_class() -> None:
    # List-form equations with two separate string hosts both
    # referencing the target. The cross-host walk in the rename
    # helper has to visit every host's logical lines, not just the
    # first.
    src = (
        'class A:\n'
        '    width = Param(float)\n'
        '    equations = [\n'
        '        "x = width",\n'
        '        "y = width * 2",\n'
        '    ]\n'
    )
    block = _block(src)
    edits = build_rename_edits(block, "width", "ww")
    assert edits is not None
    # Param assignment + one reference per host = 3 edits.
    assert len(edits) == 3
    # Edits on three distinct file lines.
    assert {e.start_line for e in edits} == {1, 3, 4}
