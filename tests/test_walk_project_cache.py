"""Tests for the disk-read memoization in ``walk_project``.

The cache skips re-parsing unchanged files across calls (the LSP
rebuilds the index on every out-of-block hover / definition /
rename). Correctness is preserved by a ``(mtime_ns, size)`` version
stamp: a file changed on disk is re-read; editor buffers never
enter the cache.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scadwright.project_index import walk as walk_mod
from scadwright.project_index.walk import clear_walk_cache, walk_project


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_walk_cache()
    yield
    clear_walk_cache()


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _count_parses(monkeypatch) -> list[int]:
    calls: list[int] = []
    real_parse = ast.parse

    def counting_parse(*args, **kwargs):
        calls.append(1)
        return real_parse(*args, **kwargs)

    monkeypatch.setattr(walk_mod.ast, "parse", counting_parse)
    return calls


def test_unchanged_files_parsed_once_across_calls(tmp_path, monkeypatch) -> None:
    _write(tmp_path, "a.py", "class A:\n    pass\n")
    _write(tmp_path, "b.py", "class B:\n    pass\n")
    calls = _count_parses(monkeypatch)

    walk_project(tmp_path)
    assert len(calls) == 2  # both files parsed on the cold walk

    walk_project(tmp_path)
    assert len(calls) == 2  # warm walk: no re-parse


def test_changed_file_is_reparsed(tmp_path, monkeypatch) -> None:
    f = _write(tmp_path, "a.py", "class A:\n    pass\n")
    calls = _count_parses(monkeypatch)

    [info1] = walk_project(tmp_path)
    assert {c.name for c in info1.classes} == {"A"}
    assert len(calls) == 1

    # Rewrite with different content; the version stamp changes.
    f.write_text("class Renamed:\n    pass\n")
    [info2] = walk_project(tmp_path)
    assert {c.name for c in info2.classes} == {"Renamed"}
    assert len(calls) == 2  # re-parsed after the change


def test_clear_cache_forces_reparse(tmp_path, monkeypatch) -> None:
    _write(tmp_path, "a.py", "class A:\n    pass\n")
    calls = _count_parses(monkeypatch)

    walk_project(tmp_path)
    assert len(calls) == 1
    clear_walk_cache()
    walk_project(tmp_path)
    assert len(calls) == 2


def test_override_does_not_populate_cache(tmp_path, monkeypatch) -> None:
    f = _write(tmp_path, "a.py", "class OnDisk:\n    pass\n")
    calls = _count_parses(monkeypatch)

    # Walk with an override: the buffer is parsed, but it must not be
    # stored as this file's disk-cache entry.
    [info_ov] = walk_project(
        tmp_path, source_overrides={f: "class Buffer:\n    pass\n"},
    )
    assert {c.name for c in info_ov.classes} == {"Buffer"}

    # A subsequent plain walk must read disk, not serve the buffer.
    [info_disk] = walk_project(tmp_path)
    assert {c.name for c in info_disk.classes} == {"OnDisk"}


def test_override_buffer_change_is_always_fresh(tmp_path, monkeypatch) -> None:
    f = _write(tmp_path, "a.py", "class OnDisk:\n    pass\n")

    [first] = walk_project(
        tmp_path, source_overrides={f: "class V1:\n    pass\n"},
    )
    assert {c.name for c in first.classes} == {"V1"}

    # A different buffer for the same path on the next call is honored
    # (buffers are parsed fresh, never cached).
    [second] = walk_project(
        tmp_path, source_overrides={f: "class V2:\n    pass\n"},
    )
    assert {c.name for c in second.classes} == {"V2"}
