"""Tests for the ``scadwright lsp`` subcommand.

Covers the two dispatch branches (pygls missing vs present) plus
the help-output check. The "pygls present" branch monkey-patches
``scadwright.lsp.server.main`` so the subcommand's dispatch is
exercised without spinning up the actual stdio loop.
"""

from __future__ import annotations

import sys

import pytest

from scadwright import cli
from scadwright.lsp import server as lsp_server


def test_lsp_missing_pygls_prints_install_hint(capsys, monkeypatch) -> None:
    # Force the import to fail even if pygls happens to be installed.
    monkeypatch.setitem(sys.modules, "pygls", None)
    rc = cli.main(["lsp"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "pip install" in err
    assert "scadwright[lsp]" in err


def test_lsp_dispatches_to_server_main_when_pygls_present(
    monkeypatch,
) -> None:
    # Replace the stdio-blocking ``server.main`` with a stand-in so
    # the dispatch returns synchronously. Asserts the CLI handler
    # actually called into the server module.
    calls: list[int] = []

    def fake_main() -> int:
        calls.append(1)
        return 42

    monkeypatch.setattr(lsp_server, "main", fake_main)
    rc = cli.main(["lsp"])
    assert rc == 42
    assert calls == [1]


def test_lsp_subcommand_listed_in_help(capsys) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    assert "lsp" in out
