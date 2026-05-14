"""Tests for ``print_stamp()`` git-derived part stamp helper."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from scadwright import print_stamp
from scadwright.errors import SCADwrightError


def _git(*args: str, cwd: Path) -> None:
    """Run a git command in ``cwd``, raising on non-zero exit."""
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A fresh git repo with one commit and identity set locally."""
    _git("init", "-q", "-b", "main", cwd=tmp_path)
    # Local config so the test doesn't depend on the developer's global git
    # identity (and doesn't write to it).
    _git("config", "user.email", "test@example.com", cwd=tmp_path)
    _git("config", "user.name", "Test", cwd=tmp_path)
    (tmp_path / "a.txt").write_text("hello\n")
    _git("add", "a.txt", cwd=tmp_path)
    _git("commit", "-q", "-m", "init", cwd=tmp_path)
    return tmp_path


def test_clean_tree_returns_short_sha(repo: Path) -> None:
    stamp = print_stamp(cwd=repo)
    assert re.fullmatch(r"[0-9a-f]{7}", stamp), stamp


def test_custom_length(repo: Path) -> None:
    stamp = print_stamp(cwd=repo, length=10)
    assert re.fullmatch(r"[0-9a-f]{10}", stamp), stamp


def test_invalid_length_raises(repo: Path) -> None:
    with pytest.raises(SCADwrightError, match="length must be"):
        print_stamp(cwd=repo, length=3)
    with pytest.raises(SCADwrightError, match="length must be"):
        print_stamp(cwd=repo, length=41)


def test_dirty_tracked_change_raises(repo: Path) -> None:
    (repo / "a.txt").write_text("modified\n")
    with pytest.raises(SCADwrightError, match="uncommitted changes"):
        print_stamp(cwd=repo)


def test_dirty_with_allow_dirty_appends_suffix(repo: Path) -> None:
    (repo / "a.txt").write_text("modified\n")
    stamp = print_stamp(cwd=repo, allow_dirty=True)
    assert stamp.endswith("-dirty")
    assert re.fullmatch(r"[0-9a-f]{7}-dirty", stamp), stamp


def test_staged_change_counts_as_dirty(repo: Path) -> None:
    (repo / "b.txt").write_text("new tracked\n")
    _git("add", "b.txt", cwd=repo)
    with pytest.raises(SCADwrightError, match="uncommitted changes"):
        print_stamp(cwd=repo)


def test_untracked_files_do_not_count_as_dirty(repo: Path) -> None:
    (repo / "scratch.scad").write_text("// build output\n")
    stamp = print_stamp(cwd=repo)
    assert re.fullmatch(r"[0-9a-f]{7}", stamp), stamp


def test_not_a_git_repo_raises(tmp_path: Path) -> None:
    with pytest.raises(SCADwrightError, match="not a git"):
        print_stamp(cwd=tmp_path)


def test_stamp_matches_rev_parse(repo: Path) -> None:
    expected = subprocess.run(
        ["git", "rev-parse", "--short=7", "HEAD"],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert print_stamp(cwd=repo) == expected
