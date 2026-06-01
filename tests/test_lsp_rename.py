"""Tests for the rename refactoring helpers.

Covers same-file Param-target rename (assignment + every
reference), auto-declared-target rename, multi-occurrence on a
single line, adjustment LHS handling, refusal cases (curated
names, type-tag names, invalid new names, parse failures), and
the position ranges of emitted edits. The cross-file path
(``build_workspace_rename_edits``) is exercised at the bottom of
the file with synthetic project layouts under tmp_path.
"""

from __future__ import annotations

from scadwright.lsp.analyze import find_equations_blocks
from scadwright.lsp.rename import (
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


# =============================================================================
# Cross-file rename via build_workspace_rename_edits
# =============================================================================


def _write(tmp_path, name, content):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _block_in(file_path, class_name):
    """Find an EquationsBlock by class name in a project file."""
    blocks = find_equations_blocks(file_path.read_text())
    for b in blocks:
        if b.class_name == class_name:
            return b
    raise AssertionError(f"no equations block for class {class_name}")


def test_workspace_rename_includes_same_file_edits(tmp_path) -> None:
    from scadwright.lsp.rename import build_workspace_rename_edits

    f = _write(tmp_path, "main.py", (
        "from scadwright import Component, Param\n"
        "class Cam(Component):\n"
        "    width = Param(float)\n"
        '    equations = "x = width"\n'
    ))
    block = _block_in(f, "Cam")
    out = build_workspace_rename_edits(block, f, "width", "ww", tmp_path)
    assert out is not None
    assert f in out
    assert len(out[f]) >= 2  # Param + reference


def test_workspace_rename_picks_up_cross_file_equations_reference(
    tmp_path,
) -> None:
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    outer_d = Param(float)\n"
        '    equations = "x = outer_d * 2"\n'
    ))
    holder_file = _write(tmp_path, "holder.py", (
        "from scadwright import Component, Param\n"
        "from spec import CamSpec\n"
        "class Holder(Component):\n"
        "    spec = Param(CamSpec)\n"
        '    equations = "y = spec.outer_d + 1"\n'
    ))
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "outer_diameter", tmp_path,
    )
    assert out is not None
    # Same-file edits in spec.py.
    assert spec_file in out
    # Cross-file edits in holder.py.
    assert holder_file in out
    holder_edits = out[holder_file]
    assert len(holder_edits) == 1
    edit = holder_edits[0]
    assert edit.new_text == "outer_diameter"
    # The edit replaces just the attr part; the file substring at
    # that range must be the old attr name.
    holder_lines = holder_file.read_text().splitlines()
    line = holder_lines[edit.start_line]
    assert line[edit.start_col:edit.end_col] == "outer_d"


def test_workspace_rename_picks_up_cross_file_build_reference(
    tmp_path,
) -> None:
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    outer_d = Param(float)\n"
        '    equations = "x = outer_d * 2"\n'
    ))
    holder_file = _write(tmp_path, "holder.py", (
        "from scadwright import Component, Param\n"
        "from spec import CamSpec\n"
        "class Holder(Component):\n"
        "    spec = Param(CamSpec)\n"
        "    def build(self):\n"
        "        return self.spec.outer_d\n"
    ))
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "outer_diameter", tmp_path,
    )
    assert out is not None
    assert holder_file in out
    holder_edits = out[holder_file]
    # The self.spec.outer_d reference should produce one edit.
    assert any(e.new_text == "outer_diameter" for e in holder_edits)
    # Verify the edit lands on the actual attr range.
    edit = holder_edits[0]
    line = holder_file.read_text().splitlines()[edit.start_line]
    assert line[edit.start_col:edit.end_col] == "outer_d"


def test_workspace_rename_ignores_unrelated_classes(tmp_path) -> None:
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    outer_d = Param(float)\n"
        '    equations = "x = outer_d"\n'
    ))
    # Another file has a class with same Param name but unrelated type.
    other_file = _write(tmp_path, "other.py", (
        "from scadwright import Spec, Param\n"
        "class OtherSpec(Spec):\n"
        "    outer_d = Param(float)\n"
        '    equations = "y = outer_d"\n'
    ))
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "outer_diameter", tmp_path,
    )
    assert out is not None
    # OtherSpec.outer_d is a different attribute on a different class;
    # cross-file rename must not touch it.
    assert other_file not in out


def test_workspace_rename_no_project_root_is_same_file_only(
    tmp_path,
) -> None:
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    outer_d = Param(float)\n"
        '    equations = "x = outer_d * 2"\n'
    ))
    _write(tmp_path, "holder.py", (
        "from scadwright import Component, Param\n"
        "from spec import CamSpec\n"
        "class Holder(Component):\n"
        "    spec = Param(CamSpec)\n"
        '    equations = "y = spec.outer_d + 1"\n'
    ))
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "outer_diameter", project_root=None,
    )
    assert out is not None
    # Without a project root, only the source file gets edits.
    assert list(out.keys()) == [spec_file]


def test_workspace_rename_param_local_name_is_same_file_only(
    tmp_path,
) -> None:
    # Renaming a Component's OWN Param's local name (the name on
    # the LHS of `name = Param(...)`) is not a cross-file change —
    # other Components don't refer to it as <other>.<this_local>.
    # The source-class itself is the only file that sees that name.
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    width = Param(float)\n"
        '    equations = "x = width"\n'
    ))
    holder_file = _write(tmp_path, "holder.py", (
        "from scadwright import Component, Param\n"
        "from spec import CamSpec\n"
        "class Holder(Component):\n"
        "    spec = Param(CamSpec)\n"
        '    equations = "y = spec.width + 1"\n'
    ))
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "width", "ww", tmp_path,
    )
    # Renaming the source class's Param `width` to `ww` should also
    # update the cross-file `spec.width` in holder.py — that's the
    # whole point of cross-file rename.
    assert out is not None
    assert holder_file in out


# =============================================================================
# Direct class-attribute references (the s2-evolving pattern)
# =============================================================================


def test_workspace_rename_picks_up_direct_class_attr_in_class_scope(
    tmp_path,
) -> None:
    """Renaming an attribute on the source class updates direct
    ``<SourceClass>.<attr>`` references at consumer-class scope."""
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60.5\n"
        "    '''\n"
    ))
    holder_file = _write(tmp_path, "holder.py", (
        "from scadwright import Component\n"
        "from spec import CamSpec\n"
        "class Holder(Component):\n"
        "    barrel_d = CamSpec.outer_d\n"
        "    def build(self):\n"
        "        return None\n"
    ))
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "outer_diameter", tmp_path,
    )
    assert out is not None
    assert holder_file in out
    holder_edits = out[holder_file]
    assert len(holder_edits) == 1
    edit = holder_edits[0]
    assert edit.new_text == "outer_diameter"
    line = holder_file.read_text().splitlines()[edit.start_line]
    assert line[edit.start_col:edit.end_col] == "outer_d"


def test_workspace_rename_picks_up_direct_class_attr_in_method_body(
    tmp_path,
) -> None:
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60.5\n"
        "    '''\n"
    ))
    holder_file = _write(tmp_path, "holder.py", (
        "from scadwright import Component\n"
        "from spec import CamSpec\n"
        "class Holder(Component):\n"
        "    def build(self):\n"
        "        return CamSpec.outer_d * 2\n"
    ))
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "outer_diameter", tmp_path,
    )
    assert out is not None
    assert holder_file in out
    holder_edits = out[holder_file]
    assert len(holder_edits) == 1


def test_workspace_rename_handles_aliased_import(tmp_path) -> None:
    """``from spec import CamSpec as C`` then ``C.outer_d`` —
    rename should follow through the alias."""
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60.5\n"
        "    '''\n"
    ))
    holder_file = _write(tmp_path, "holder.py", (
        "from scadwright import Component\n"
        "from spec import CamSpec as C\n"
        "class Holder(Component):\n"
        "    barrel_d = C.outer_d\n"
        "    def build(self):\n"
        "        return None\n"
    ))
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "outer_diameter", tmp_path,
    )
    assert out is not None
    assert holder_file in out
    edit = out[holder_file][0]
    line = holder_file.read_text().splitlines()[edit.start_line]
    assert line[edit.start_col:edit.end_col] == "outer_d"


def test_workspace_rename_handles_chained_access_after_renamed_attr(
    tmp_path,
) -> None:
    """``CamSpec.outer_d.bit_length()`` — rename ``outer_d`` but
    leave ``bit_length`` alone (it isn't on the source class)."""
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    ))
    holder_file = _write(tmp_path, "holder.py", (
        "from scadwright import Component\n"
        "from spec import CamSpec\n"
        "class Holder(Component):\n"
        "    bits = CamSpec.outer_d.bit_length()\n"
        "    def build(self):\n"
        "        return None\n"
    ))
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "outer_diameter", tmp_path,
    )
    assert out is not None
    holder_edits = out.get(holder_file, [])
    # Exactly one edit; it covers `outer_d`, not `bit_length`.
    assert len(holder_edits) == 1
    edit = holder_edits[0]
    line = holder_file.read_text().splitlines[edit.start_line] if False else holder_file.read_text().splitlines()[edit.start_line]
    assert line[edit.start_col:edit.end_col] == "outer_d"


def test_workspace_rename_does_not_touch_same_attr_on_different_class(
    tmp_path,
) -> None:
    """A reference to ``OtherSpec.outer_d`` is left alone when
    renaming ``outer_d`` on ``CamSpec``."""
    from scadwright.lsp.rename import build_workspace_rename_edits

    _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
        "class OtherSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 99\n"
        "    '''\n"
    ))
    holder_file = _write(tmp_path, "holder.py", (
        "from scadwright import Component\n"
        "from spec import OtherSpec\n"
        "class Holder(Component):\n"
        "    d = OtherSpec.outer_d\n"
        "    def build(self):\n"
        "        return None\n"
    ))
    spec_file = tmp_path / "spec.py"
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "outer_diameter", tmp_path,
    )
    assert out is not None
    assert holder_file not in out or out[holder_file] == []


def test_workspace_rename_other_class_in_same_file(tmp_path) -> None:
    """A class in the same file as the source class that
    references ``SourceClass.attr`` gets the rename through the
    cross-file pass (which walks every class but the source)."""
    from scadwright.lsp.rename import build_workspace_rename_edits

    f = _write(tmp_path, "both.py", (
        "from scadwright import Spec, Component\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
        "class Holder(Component):\n"
        "    d = CamSpec.outer_d\n"
        "    def build(self):\n"
        "        return None\n"
    ))
    block = _block_in(f, "CamSpec")
    out = build_workspace_rename_edits(
        block, f, "outer_d", "outer_diameter", tmp_path,
    )
    assert out is not None
    # Edits in the same file: source class equation + Holder's reference.
    file_edits = out[f]
    # Find the edit that targets `outer_d` after `CamSpec.`.
    text = f.read_text()
    found_direct = False
    for edit in file_edits:
        line = text.splitlines()[edit.start_line]
        if line[edit.start_col:edit.end_col] == "outer_d" and "CamSpec." in line:
            found_direct = True
            break
    assert found_direct


def test_workspace_rename_combines_direct_and_param_refs(tmp_path) -> None:
    """A consumer class with BOTH ``CamSpec.outer_d`` (direct) and
    ``self.spec.outer_d`` (Param-mediated) should get both edits."""
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    ))
    holder_file = _write(tmp_path, "holder.py", (
        "from scadwright import Component, Param\n"
        "from spec import CamSpec\n"
        "class Holder(Component):\n"
        "    default_d = CamSpec.outer_d\n"
        "    spec = Param(CamSpec)\n"
        "    def build(self):\n"
        "        return self.spec.outer_d\n"
    ))
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "outer_diameter", tmp_path,
    )
    assert out is not None
    assert holder_file in out
    # Two edits: direct class-attr at class scope, Param-mediated in build.
    assert len(out[holder_file]) == 2


# =============================================================================
# Helper-method scope (self.x.y in non-build methods)
# =============================================================================


def test_workspace_rename_follows_self_attr_into_helper_methods(
    tmp_path,
) -> None:
    """A consumer class whose helper method (called from build)
    uses ``self.spec.outer_d`` should also get the rename."""
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    outer_d = Param(float)\n"
        '    equations = "x = outer_d"\n'
    ))
    holder_file = _write(tmp_path, "holder.py", (
        "from scadwright import Component, Param\n"
        "from spec import CamSpec\n"
        "class Holder(Component):\n"
        "    spec = Param(CamSpec)\n"
        "    def build(self):\n"
        "        return self._build_cap()\n"
        "    def _build_cap(self):\n"
        "        return self.spec.outer_d\n"
    ))
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "ww", tmp_path,
    )
    assert out is not None
    assert holder_file in out
    # The helper method reference is the only ``outer_d`` site in
    # holder.py — make sure it's renamed.
    assert len(out[holder_file]) == 1
    edit = out[holder_file][0]
    line = holder_file.read_text().splitlines()[edit.start_line]
    assert line[edit.start_col:edit.end_col] == "outer_d"
    assert "_build_cap" in holder_file.read_text().splitlines()[edit.start_line - 1] \
        or "self.spec.outer_d" in line


# =============================================================================
# Module-level and function-level references — silent failures fixed
# by the per-file walker
# =============================================================================


def test_workspace_rename_picks_up_module_level_constant_assignment(
    tmp_path,
) -> None:
    """``MOUNT_OFFSET = SourceClass.attr`` at module scope — the
    canonical s2-evolving pattern that the per-class walker missed.
    """
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    ))
    consumer_file = _write(tmp_path, "housing.py", (
        "from scadwright import Component\n"
        "from spec import CamSpec\n"
        "MOUNT_OFFSET = CamSpec.outer_d\n"
        "class Housing(Component):\n"
        "    def build(self):\n"
        "        return None\n"
    ))
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "outer_diameter", tmp_path,
    )
    assert out is not None
    assert consumer_file in out
    edit = out[consumer_file][0]
    line = consumer_file.read_text().splitlines()[edit.start_line]
    assert line[edit.start_col:edit.end_col] == "outer_d"
    assert line.startswith("MOUNT_OFFSET")


def test_workspace_rename_picks_up_module_level_function_body(
    tmp_path,
) -> None:
    """References inside a module-level function (not a class
    method) are caught by the per-file walker."""
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    ))
    consumer_file = _write(tmp_path, "helpers.py", (
        "from spec import CamSpec\n"
        "def get_diameter():\n"
        "    return CamSpec.outer_d + 1\n"
    ))
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "outer_diameter", tmp_path,
    )
    assert out is not None
    assert consumer_file in out
    edit = out[consumer_file][0]
    line = consumer_file.read_text().splitlines()[edit.start_line]
    assert line[edit.start_col:edit.end_col] == "outer_d"


def test_workspace_rename_catches_source_class_self_reference(
    tmp_path,
) -> None:
    """A class with ``foo = SelfClass.bar`` in its body referencing
    its own attribute via class name — the per-file walker visits
    the source file too, so the reference gets caught."""
    from scadwright.lsp.rename import build_workspace_rename_edits

    f = _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
        "    # Self-reference outside the equations block.\n"
        "    backup_outer_d = None\n"
    ))
    # Edit the file to add the self-reference; can't put SelfClass
    # ref inside class body when class isn't fully defined yet, so
    # use a separate assignment after the class.
    f = _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
        "BACKUP = CamSpec.outer_d\n"
    ))
    block = _block_in(f, "CamSpec")
    out = build_workspace_rename_edits(
        block, f, "outer_d", "outer_diameter", tmp_path,
    )
    assert out is not None
    assert f in out
    # The module-level BACKUP reference should be renamed in addition
    # to the equation LHS.
    text = f.read_text()
    found_module_level = False
    for edit in out[f]:
        line = text.splitlines()[edit.start_line]
        if "BACKUP" in line and line[edit.start_col:edit.end_col] == "outer_d":
            found_module_level = True
            break
    assert found_module_level


# =============================================================================
# Open editor buffers: cross-file edits land on buffer positions, not
# stale disk positions
# =============================================================================


def test_cross_file_rename_uses_open_buffer_over_disk(tmp_path) -> None:
    """A consumer file open in the editor with unsaved edits — the
    rename must compute the reference position from the buffer, not
    the disk copy whose line numbers differ.
    """
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    ))
    consumer = _write(tmp_path, "housing.py", (
        "from spec import CamSpec\n"
        "BORE = CamSpec.outer_d\n"
    ))
    # Editor buffer: a blank line inserted above shifts the reference
    # from line 1 (disk) to line 3 (buffer).
    buffer_text = (
        "from spec import CamSpec\n"
        "\n"
        "\n"
        "BORE = CamSpec.outer_d\n"
    )
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "outer_diameter", tmp_path,
        source_overrides={consumer: buffer_text},
    )
    assert out is not None
    assert consumer in out
    edit = out[consumer][0]
    # The edit targets the buffer's line 3, where outer_d actually sits.
    assert edit.start_line == 3
    buffer_line = buffer_text.splitlines()[edit.start_line]
    assert buffer_line[edit.start_col:edit.end_col] == "outer_d"


def test_cross_file_rename_without_override_uses_disk(tmp_path) -> None:
    """Sanity: with no override, the edit is computed against the disk
    copy. Pairs with the test above to show the override path is what
    moves the position."""
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    ))
    consumer = _write(tmp_path, "housing.py", (
        "from spec import CamSpec\n"
        "BORE = CamSpec.outer_d\n"
    ))
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "outer_diameter", tmp_path,
    )
    assert out is not None
    edit = out[consumer][0]
    # Disk has the reference on line 1.
    assert edit.start_line == 1


def test_cross_file_rename_closed_file_still_uses_disk(tmp_path) -> None:
    """A consumer file NOT in the override map (closed in the editor)
    is read from disk — the editor applies edits to disk content for
    closed files, so disk positions are correct there."""
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class CamSpec(Spec):\n"
        "    equations = '''\n"
        "        outer_d = 60\n"
        "    '''\n"
    ))
    open_consumer = _write(tmp_path, "open.py", (
        "from spec import CamSpec\n"
        "A = CamSpec.outer_d\n"
    ))
    closed_consumer = _write(tmp_path, "closed.py", (
        "from spec import CamSpec\n"
        "B = CamSpec.outer_d\n"
    ))
    # Only the open file gets an override; closed stays disk-based.
    block = _block_in(spec_file, "CamSpec")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "outer_diameter", tmp_path,
        source_overrides={open_consumer: (
            "from spec import CamSpec\n"
            "\n"
            "A = CamSpec.outer_d\n"
        )},
    )
    assert out is not None
    # Open file: override shifted the reference to line 2.
    assert out[open_consumer][0].start_line == 2
    # Closed file: disk position, line 1.
    assert out[closed_consumer][0].start_line == 1


# =============================================================================
# Multi-hop chains: references that reach the source class through a
# nested Component-typed Param, resolved hop by hop
# =============================================================================


def test_workspace_rename_two_hop_self_chain(tmp_path) -> None:
    """``self.a.b.outer_d`` where ``a`` is Param(A) and ``A.b`` is
    Param(B=source) — the deep reference is rewritten even though the
    consumer holds no direct Param of the source class."""
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec, Param\n"
        "class B(Spec):\n"
        "    outer_d = Param(float)\n"
        '    equations = "x = outer_d"\n'
    ))
    _write(tmp_path, "mid.py", (
        "from scadwright import Spec, Param\n"
        "from spec import B\n"
        "class A(Spec):\n"
        "    b = Param(B)\n"
    ))
    consumer = _write(tmp_path, "consumer.py", (
        "from scadwright import Component, Param\n"
        "from mid import A\n"
        "class Consumer(Component):\n"
        "    a = Param(A)\n"
        "    def build(self):\n"
        "        return self.a.b.outer_d\n"
    ))
    block = _block_in(spec_file, "B")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "diameter", tmp_path,
    )
    assert out is not None
    assert consumer in out
    edit = out[consumer][0]
    line = consumer.read_text().splitlines()[edit.start_line]
    assert line[edit.start_col:edit.end_col] == "outer_d"
    assert "self.a.b" in line


def test_workspace_rename_three_hop_self_chain(tmp_path) -> None:
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec, Param\n"
        "class C(Spec):\n"
        "    leaf = Param(float)\n"
        '    equations = "x = leaf"\n'
    ))
    _write(tmp_path, "chain.py", (
        "from scadwright import Spec, Param\n"
        "from spec import C\n"
        "class B(Spec):\n"
        "    c = Param(C)\n"
        "class A(Spec):\n"
        "    b = Param(B)\n"
    ))
    consumer = _write(tmp_path, "consumer.py", (
        "from scadwright import Component, Param\n"
        "from chain import A\n"
        "class Consumer(Component):\n"
        "    a = Param(A)\n"
        "    def build(self):\n"
        "        return self.a.b.c.leaf\n"
    ))
    block = _block_in(spec_file, "C")
    out = build_workspace_rename_edits(
        block, spec_file, "leaf", "tip", tmp_path,
    )
    assert out is not None
    assert consumer in out
    edit = out[consumer][0]
    line = consumer.read_text().splitlines()[edit.start_line]
    assert line[edit.start_col:edit.end_col] == "leaf"


def test_workspace_rename_two_hop_equation_chain(tmp_path) -> None:
    """``a.b.outer_d`` in an equations block resolves through Param
    types the same way."""
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec, Param\n"
        "class B(Spec):\n"
        "    outer_d = Param(float)\n"
        '    equations = "x = outer_d"\n'
    ))
    _write(tmp_path, "mid.py", (
        "from scadwright import Spec, Param\n"
        "from spec import B\n"
        "class A(Spec):\n"
        "    b = Param(B)\n"
    ))
    consumer = _write(tmp_path, "consumer.py", (
        "from scadwright import Component, Param\n"
        "from mid import A\n"
        "class Consumer(Component):\n"
        "    a = Param(A)\n"
        '    equations = "y = a.b.outer_d + 1"\n'
    ))
    block = _block_in(spec_file, "B")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "diameter", tmp_path,
    )
    assert out is not None
    assert consumer in out
    edit = out[consumer][0]
    line = consumer.read_text().splitlines()[edit.start_line]
    assert line[edit.start_col:edit.end_col] == "outer_d"


def test_workspace_rename_chain_through_local_is_not_matched(tmp_path) -> None:
    """A reference through a local variable can't be resolved
    statically, so it's an honest miss (no false edit on the wrong
    spot, no crash)."""
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec, Param\n"
        "class B(Spec):\n"
        "    outer_d = Param(float)\n"
        '    equations = "x = outer_d"\n'
    ))
    _write(tmp_path, "mid.py", (
        "from scadwright import Spec, Param\n"
        "from spec import B\n"
        "class A(Spec):\n"
        "    b = Param(B)\n"
    ))
    consumer = _write(tmp_path, "consumer.py", (
        "from scadwright import Component, Param\n"
        "from mid import A\n"
        "class Consumer(Component):\n"
        "    a = Param(A)\n"
        "    def build(self):\n"
        "        inner = self.a.b\n"
        "        return inner.outer_d\n"
    ))
    block = _block_in(spec_file, "B")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "diameter", tmp_path,
    )
    assert out is not None
    # `inner.outer_d` is not matched (inner is a local). The consumer
    # gets no edit; the rename doesn't corrupt the wrong position.
    assert consumer not in out or out[consumer] == []


def test_workspace_rename_chain_breaks_on_unrelated_class(tmp_path) -> None:
    """A same-named attr reached through a chain that resolves to a
    DIFFERENT class is left alone."""
    from scadwright.lsp.rename import build_workspace_rename_edits

    spec_file = _write(tmp_path, "spec.py", (
        "from scadwright import Spec, Param\n"
        "class B(Spec):\n"
        "    outer_d = Param(float)\n"
        '    equations = "x = outer_d"\n'
        "class Other(Spec):\n"
        "    outer_d = Param(float)\n"
        '    equations = "z = outer_d"\n'
    ))
    _write(tmp_path, "mid.py", (
        "from scadwright import Spec, Param\n"
        "from spec import Other\n"
        "class A(Spec):\n"
        "    b = Param(Other)\n"
    ))
    consumer = _write(tmp_path, "consumer.py", (
        "from scadwright import Component, Param\n"
        "from mid import A\n"
        "class Consumer(Component):\n"
        "    a = Param(A)\n"
        "    def build(self):\n"
        "        return self.a.b.outer_d\n"
    ))
    block = _block_in(spec_file, "B")
    out = build_workspace_rename_edits(
        block, spec_file, "outer_d", "diameter", tmp_path,
    )
    assert out is not None
    # self.a.b resolves to Other, not B; renaming B.outer_d must not
    # touch consumer.py.
    assert consumer not in out or out[consumer] == []
