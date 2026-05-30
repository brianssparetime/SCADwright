"""Tests for the ``exclude=`` parameter on ``walk_project``.

Covers segment-match (bare-name) and full-path-match (pattern
containing ``/``) semantics, repeated patterns, file-level
matches, and the no-exclude default.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.project_index.walk import walk_project


def _touch(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_default_no_exclude_keeps_everything(tmp_path: Path) -> None:
    _touch(tmp_path / "a.py")
    _touch(tmp_path / "sub" / "b.py")
    files = walk_project(tmp_path)
    paths = {f.path.name for f in files}
    assert paths == {"a.py", "b.py"}


def test_exclude_bare_name_matches_any_segment(tmp_path: Path) -> None:
    _touch(tmp_path / "keep.py")
    _touch(tmp_path / "OLD" / "drop.py")
    _touch(tmp_path / "OLD" / "deeper" / "still_drop.py")
    files = walk_project(tmp_path, exclude=["OLD"])
    paths = {f.path.name for f in files}
    assert paths == {"keep.py"}


def test_exclude_bare_name_with_glob(tmp_path: Path) -> None:
    _touch(tmp_path / "widget.py")
    _touch(tmp_path / "widget.test.py")
    _touch(tmp_path / "helper.test.py")
    files = walk_project(tmp_path, exclude=["*.test.py"])
    paths = {f.path.name for f in files}
    assert paths == {"widget.py"}


def test_exclude_with_slash_matches_relative_path(tmp_path: Path) -> None:
    _touch(tmp_path / "OLD" / "keep.py")
    _touch(tmp_path / "OLD" / "2026-05-13" / "drop.py")
    _touch(tmp_path / "OLD" / "2026-05-14" / "drop.py")
    files = walk_project(tmp_path, exclude=["OLD/2026-*"])
    rel_paths = {f.path.relative_to(tmp_path).as_posix() for f in files}
    assert rel_paths == {"OLD/keep.py"}


def test_multiple_exclude_patterns_union(tmp_path: Path) -> None:
    _touch(tmp_path / "keep.py")
    _touch(tmp_path / "OLD" / "drop.py")
    _touch(tmp_path / "scratch" / "drop.py")
    files = walk_project(tmp_path, exclude=["OLD", "scratch"])
    paths = {f.path.name for f in files}
    assert paths == {"keep.py"}


def test_exclude_does_not_affect_single_file_input(tmp_path: Path) -> None:
    f = tmp_path / "widget.py"
    _touch(f)
    files = walk_project(f, exclude=["widget*"])
    # Single-file input is taken as-is regardless of exclude.
    assert len(files) == 1
    assert files[0].path == f


def test_exclude_pattern_matching_no_files_is_noop(tmp_path: Path) -> None:
    _touch(tmp_path / "a.py")
    _touch(tmp_path / "b.py")
    files = walk_project(tmp_path, exclude=["nonexistent"])
    paths = {f.path.name for f in files}
    assert paths == {"a.py", "b.py"}


def test_builtin_skip_dirs_still_apply_with_exclude(tmp_path: Path) -> None:
    # __pycache__ should still drop regardless of exclude content.
    _touch(tmp_path / "keep.py")
    _touch(tmp_path / "__pycache__" / "cached.py")
    files = walk_project(tmp_path, exclude=["unrelated"])
    paths = {f.path.name for f in files}
    assert paths == {"keep.py"}


def test_exclude_patterns_are_case_sensitive(tmp_path: Path) -> None:
    """Patterns match by case exactly the same way on every OS,
    regardless of the underlying filesystem's case sensitivity.
    """
    _touch(tmp_path / "OLD" / "a.py")
    _touch(tmp_path / "live" / "b.py")
    files = walk_project(tmp_path, exclude=["old"])
    # Lowercase pattern doesn't match the uppercase directory; both
    # files survive.
    paths = {f.path.name for f in files}
    assert paths == {"a.py", "b.py"}
