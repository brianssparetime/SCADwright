"""Tests for the ``scadwright graph`` subcommand.

Covers help listing, end-to-end output on a synthetic project for the
two formats (ascii default, json), single-file inputs, filtering, and
the error cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scadwright import cli


def test_graph_subcommand_listed_in_help(capsys) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    assert "graph" in out


def test_graph_default_format_is_ascii(tmp_path: Path, capsys) -> None:
    (tmp_path / "main.py").write_text(
        "from scadwright import Component\n"
        "class Bracket(Component):\n"
        "    pass\n"
    )
    rc = cli.main(["graph", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("scadwright project:")
    assert "Components" in out
    assert "Bracket [" in out


def test_graph_on_single_file(tmp_path: Path, capsys) -> None:
    f = tmp_path / "widget.py"
    f.write_text(
        "from scadwright import Component\n"
        "class Bracket(Component):\n"
        "    pass\n"
    )
    rc = cli.main(["graph", str(f)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Bracket [" in out


def test_graph_on_empty_project(tmp_path: Path, capsys) -> None:
    rc = cli.main(["graph", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("scadwright project:")
    assert "(empty project)" in out


def test_graph_nonexistent_path_returns_error(tmp_path: Path, capsys) -> None:
    rc = cli.main(["graph", str(tmp_path / "nope")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not found" in err


def test_graph_format_json(tmp_path: Path, capsys) -> None:
    (tmp_path / "main.py").write_text(
        "from scadwright import Component, Spec, Param\n"
        "class BatterySpec(Spec):\n"
        "    pass\n"
        "class Holder(Component):\n"
        "    spec = Param(BatterySpec)\n"
    )
    rc = cli.main(["graph", str(tmp_path), "--format", "json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert set(payload["components"]) == {"Holder"}
    assert set(payload["specs"]) == {"BatterySpec"}
    assert payload["components"]["Holder"]["uses_spec"][0]["spec"] == (
        "BatterySpec"
    )


def test_graph_invalid_format_rejected(tmp_path: Path, capsys) -> None:
    (tmp_path / "main.py").write_text("")
    with pytest.raises(SystemExit):
        cli.main(["graph", str(tmp_path), "--format", "nonsense"])


def test_graph_mermaid_and_dot_no_longer_accepted(
    tmp_path: Path, capsys,
) -> None:
    (tmp_path / "main.py").write_text("")
    for fmt in ("mermaid", "dot"):
        with pytest.raises(SystemExit):
            cli.main(["graph", str(tmp_path), "--format", fmt])


def test_graph_warns_on_parse_errors(tmp_path: Path, capsys) -> None:
    (tmp_path / "good.py").write_text(
        "from scadwright import Component\n"
        "class Bracket(Component):\n"
        "    pass\n"
    )
    (tmp_path / "broken.py").write_text("def f(\n")  # unterminated paren
    rc = cli.main(["graph", str(tmp_path)])
    out_err = capsys.readouterr()
    assert rc == 0
    # Warning surfaces on stderr; good file's class still in stdout.
    assert "warning" in out_err.err
    assert "broken.py" in out_err.err
    assert "Bracket [" in out_err.out


def test_graph_filter_focuses_subgraph(tmp_path: Path, capsys) -> None:
    (tmp_path / "main.py").write_text(
        "from scadwright import Component\n"
        "class A(Component):\n"
        "    pass\n"
        "class B(Component):\n"
        "    def build(self):\n"
        "        return A()\n"
        "class C(Component):\n"
        "    pass\n"
    )
    rc = cli.main(["graph", str(tmp_path), "--filter", "A"])
    out = capsys.readouterr().out
    assert rc == 0
    # A and B (direct relationship) survive; C is disconnected and drops.
    assert "A [" in out
    assert "B [" in out
    assert "C [" not in out


def test_graph_filter_with_depth_zero(tmp_path: Path, capsys) -> None:
    (tmp_path / "main.py").write_text(
        "from scadwright import Component\n"
        "class A(Component):\n"
        "    pass\n"
        "class B(Component):\n"
        "    def build(self):\n"
        "        return A()\n"
    )
    rc = cli.main([
        "graph", str(tmp_path), "--filter", "A", "--depth", "0",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "A [" in out
    assert "B [" not in out


def test_graph_filter_unknown_returns_error(tmp_path: Path, capsys) -> None:
    (tmp_path / "main.py").write_text(
        "from scadwright import Component\n"
        "class A(Component):\n"
        "    pass\n"
    )
    rc = cli.main(["graph", str(tmp_path), "--filter", "Nope"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "Nope" in err


def test_graph_depth_without_filter_returns_error(
    tmp_path: Path, capsys,
) -> None:
    (tmp_path / "main.py").write_text("")
    rc = cli.main(["graph", str(tmp_path), "--depth", "1"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "--depth" in err and "--filter" in err
