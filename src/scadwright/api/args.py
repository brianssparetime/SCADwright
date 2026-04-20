"""Script parameter registration via argparse.

`sc.arg(name, default=..., type=...)` registers a parameter and returns its
parsed value. The first call to any `arg()` triggers a lazy `parse_known_args`
against `sys.argv`, so the order of calls doesn't matter. Unknown args are
tolerated — the CLI wrapper can inject its own flags alongside script args.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Callable

from scadwright.errors import SCADwrightError


_parser: argparse.ArgumentParser | None = None
_parsed: argparse.Namespace | None = None
_registered: dict[str, dict[str, Any]] = {}
_argv_override: list[str] | None = None


class _ArgparseNoExit(argparse.ArgumentParser):
    """argparse that raises instead of calling sys.exit (test-friendly)."""

    def error(self, message: str) -> None:
        raise SCADwrightError(f"argparse error: {message}")


def _get_parser() -> argparse.ArgumentParser:
    global _parser
    if _parser is None:
        _parser = _ArgparseNoExit(add_help=True, description="scadwright script parameters")
    return _parser


def _flush_parse() -> None:
    """Force a re-parse on next access (internal; used by tests and the CLI)."""
    global _parsed
    _parsed = None


def _reset_for_testing() -> None:
    """Nuke the parser and all registered args. Test use only."""
    global _parser, _parsed, _registered, _argv_override
    _parser = None
    _parsed = None
    _registered = {}
    _argv_override = None


def set_argv(argv: list[str] | None) -> None:
    """Override sys.argv for parsing. Used by the CLI. Pass None to restore default."""
    global _argv_override
    _argv_override = argv
    _flush_parse()


def _ensure_parsed() -> argparse.Namespace:
    global _parsed
    if _parsed is None:
        argv = _argv_override if _argv_override is not None else sys.argv[1:]
        ns, _unknown = _get_parser().parse_known_args(argv)
        _parsed = ns
    return _parsed


def arg(
    name: str,
    *,
    default: Any = None,
    type: Callable[[str], Any] = str,
    help: str | None = None,
) -> Any:
    """Register a script parameter. Returns the parsed value (or default).

    Calling `sc.arg("width", default=10, type=float)` registers `--width` and
    returns `10` if no `--width=NN` argv is present. Returns the parsed value
    otherwise. Safe to call multiple times with the same name; must use
    identical parameters or a `SCADwrightError` is raised.
    """
    global _parsed
    if name in _registered:
        existing = _registered[name]
        if existing["default"] != default or existing["type"] != type or existing["help"] != help:
            raise SCADwrightError(
                f"arg {name!r} re-registered with different parameters"
            )
    else:
        parser = _get_parser()
        parser.add_argument(
            f"--{name}",
            dest=name,
            default=default,
            type=type,
            help=help,
        )
        _registered[name] = {"default": default, "type": type, "help": help}
        _flush_parse()
    ns = _ensure_parsed()
    return getattr(ns, name, default)


def parse_args() -> argparse.Namespace:
    """Explicitly trigger parsing. Returns the parsed namespace."""
    return _ensure_parsed()
