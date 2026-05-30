"""Tests for the ``source_overrides=`` parameter on ``walk_project``.

The override map lets a caller (the LSP) substitute the editor's
live buffer text for a file's on-disk contents, so analysis runs
against unsaved edits.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.project_index.walk import walk_project


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def test_override_replaces_disk_content(tmp_path: Path) -> None:
    f = _write(tmp_path, "widget.py", "class OnDisk:\n    pass\n")
    [info] = walk_project(
        tmp_path,
        source_overrides={f: "class FromBuffer:\n    pass\n"},
    )
    names = {c.name for c in info.classes}
    assert names == {"FromBuffer"}
    assert "OnDisk" not in names


def test_override_only_affects_listed_file(tmp_path: Path) -> None:
    a = _write(tmp_path, "a.py", "class A:\n    pass\n")
    _write(tmp_path, "b.py", "class B:\n    pass\n")
    files = walk_project(
        tmp_path,
        source_overrides={a: "class ABuffer:\n    pass\n"},
    )
    by_name = {c.name for f in files for c in f.classes}
    # a.py overridden, b.py from disk.
    assert "ABuffer" in by_name
    assert "B" in by_name
    assert "A" not in by_name


def test_override_for_undiscovered_file_is_ignored(tmp_path: Path) -> None:
    """A buffer for a path that doesn't exist on disk isn't injected;
    overrides only swap content of files the walk already finds."""
    _write(tmp_path, "a.py", "class A:\n    pass\n")
    ghost = tmp_path / "ghost.py"  # never written to disk
    files = walk_project(
        tmp_path,
        source_overrides={ghost: "class Ghost:\n    pass\n"},
    )
    names = {c.name for f in files for c in f.classes}
    assert names == {"A"}


def test_override_on_single_file_input(tmp_path: Path) -> None:
    f = _write(tmp_path, "widget.py", "class OnDisk:\n    pass\n")
    [info] = walk_project(
        f,
        source_overrides={f: "class FromBuffer:\n    pass\n"},
    )
    assert {c.name for c in info.classes} == {"FromBuffer"}


def test_no_overrides_reads_disk(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", "class OnDisk:\n    pass\n")
    [info] = walk_project(tmp_path)
    assert {c.name for c in info.classes} == {"OnDisk"}
