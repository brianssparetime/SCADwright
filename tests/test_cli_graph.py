"""Tests for the ``scadwright graph`` subcommand.

Covers help-output listing, end-to-end Mermaid generation on a
synthetic project, single-file inputs, and the
nonexistent-path error case.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scadwright import cli


def test_graph_subcommand_listed_in_help(capsys) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    assert "graph" in out


def test_graph_emits_mermaid_for_synthetic_project(
    tmp_path: Path, capsys,
) -> None:
    (tmp_path / "main.py").write_text(
        "from scadwright import Component, Spec, Param\n"
        "class BatterySpec(Spec):\n"
        "    pass\n"
        "class Holder(Component):\n"
        "    spec = Param(BatterySpec)\n"
        '    equations = "x = spec.outer_d"\n'
    )
    rc = cli.main(["graph", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("graph TD\n")
    assert "main_BatterySpec{BatterySpec}" in out
    assert "main_Holder(Holder)" in out
    assert 'main_Holder --"Param(spec)"--> main_BatterySpec' in out
    assert 'main_Holder --"outer_d"--> main_BatterySpec' in out


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
    assert "Bracket(Bracket)" in out


def test_graph_on_empty_project(tmp_path: Path, capsys) -> None:
    rc = cli.main(["graph", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip() == "graph TD"


def test_graph_nonexistent_path_returns_error(
    tmp_path: Path, capsys,
) -> None:
    rc = cli.main(["graph", str(tmp_path / "nope")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not found" in err


def test_graph_format_json(tmp_path: Path, capsys) -> None:
    import json

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
    node_ids = {n["id"] for n in payload["nodes"]}
    assert node_ids == {"main.BatterySpec", "main.Holder"}
    edge_kinds = {e["kind"] for e in payload["edges"]}
    assert edge_kinds == {"uses_param"}


def test_graph_default_format_is_mermaid(
    tmp_path: Path, capsys,
) -> None:
    (tmp_path / "main.py").write_text(
        "from scadwright import Component\n"
        "class Bracket(Component):\n"
        "    pass\n"
    )
    rc = cli.main(["graph", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("graph TD\n")


def test_graph_invalid_format_rejected(
    tmp_path: Path, capsys,
) -> None:
    import pytest

    (tmp_path / "main.py").write_text("")
    with pytest.raises(SystemExit):
        cli.main(["graph", str(tmp_path), "--format", "nonsense"])


def test_graph_format_dot(tmp_path: Path, capsys) -> None:
    (tmp_path / "main.py").write_text(
        "from scadwright import Component\n"
        "class Bracket(Component):\n"
        "    pass\n"
    )
    rc = cli.main(["graph", str(tmp_path), "--format", "dot"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("digraph SCADwright {\n")
    assert '"main.Bracket"' in out
    assert out.rstrip().endswith("}")


def test_graph_warns_on_parse_errors(tmp_path: Path, capsys) -> None:
    (tmp_path / "good.py").write_text(
        "from scadwright import Component\n"
        "class Bracket(Component):\n"
        "    pass\n"
    )
    (tmp_path / "broken.py").write_text(
        "def f(\n"  # unterminated paren
    )
    rc = cli.main(["graph", str(tmp_path)])
    out_err = capsys.readouterr()
    assert rc == 0
    # Warning surfaces on stderr; good file's class still in stdout.
    assert "warning" in out_err.err
    assert "broken.py" in out_err.err
    assert "good_Bracket" in out_err.out


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
    assert "main_A(A)" in out
    assert "main_B(B)" in out
    assert "main_C(C)" not in out


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
    assert "main_A(A)" in out
    assert "main_B(B)" not in out


def test_graph_filter_unknown_returns_error(
    tmp_path: Path, capsys,
) -> None:
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
