"""Tests for ``build_graph(exclude=...)``.

Covers exclusion at the build-graph level — both that excluded
files don't contribute nodes or edges to the result, and that
patterns thread correctly from the CLI through to ``walk_project``.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.graph.build import build_graph


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def test_excluded_files_drop_from_graph(tmp_path: Path) -> None:
    _write(tmp_path, "current.py", (
        "from scadwright import Component\n"
        "class Current(Component):\n"
        "    pass\n"
    ))
    _write(tmp_path, "OLD/snapshot.py", (
        "from scadwright import Component\n"
        "class Snapshot(Component):\n"
        "    pass\n"
    ))
    graph = build_graph(tmp_path, exclude=["OLD"])
    labels = {n.label for n in graph.nodes}
    assert labels == {"Current"}


def test_no_exclude_keeps_everything(tmp_path: Path) -> None:
    _write(tmp_path, "a.py", (
        "from scadwright import Component\n"
        "class A(Component):\n"
        "    pass\n"
    ))
    _write(tmp_path, "OLD/b.py", (
        "from scadwright import Component\n"
        "class B(Component):\n"
        "    pass\n"
    ))
    graph = build_graph(tmp_path)
    labels = {n.label for n in graph.nodes}
    assert labels == {"A", "B"}


def test_exclude_silences_transform_collision_warnings(tmp_path: Path) -> None:
    """Duplicate transform definitions in excluded snapshots don't
    produce warnings, since the files never enter the registry."""
    _write(tmp_path, "verbs.py", (
        "from scadwright.transforms import transform\n"
        "@transform('foo')\n"
        "def foo(node):\n"
        "    return node\n"
    ))
    _write(tmp_path, "OLD/snapshot/verbs.py", (
        "from scadwright.transforms import transform\n"
        "@transform('foo')\n"
        "def foo(node):\n"
        "    return node\n"
    ))
    # Without exclude: duplicate 'foo' registration triggers a warning.
    g_all = build_graph(tmp_path)
    assert any("foo" in msg for _path, msg in g_all.warnings)
    # With exclude: snapshot drops out, no warning.
    g_filtered = build_graph(tmp_path, exclude=["OLD"])
    assert g_filtered.warnings == ()


def test_cli_passes_exclude_through(tmp_path: Path, capsys) -> None:
    from scadwright import cli
    _write(tmp_path, "current.py", (
        "from scadwright import Component\n"
        "class Current(Component):\n"
        "    pass\n"
    ))
    _write(tmp_path, "OLD/snapshot.py", (
        "from scadwright import Component\n"
        "class Snapshot(Component):\n"
        "    pass\n"
    ))
    rc = cli.main([
        "graph", str(tmp_path), "--exclude", "OLD",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "component  current.Current" in out
    assert "Snapshot" not in out


def test_cli_repeatable_exclude(tmp_path: Path, capsys) -> None:
    from scadwright import cli
    _write(tmp_path, "current.py", (
        "from scadwright import Component\n"
        "class Current(Component):\n"
        "    pass\n"
    ))
    _write(tmp_path, "OLD/a.py", (
        "from scadwright import Component\n"
        "class A(Component):\n"
        "    pass\n"
    ))
    _write(tmp_path, "scratch/b.py", (
        "from scadwright import Component\n"
        "class B(Component):\n"
        "    pass\n"
    ))
    rc = cli.main([
        "graph", str(tmp_path),
        "--exclude", "OLD",
        "--exclude", "scratch",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Current" in out
    assert "A" not in out
    assert "B" not in out
