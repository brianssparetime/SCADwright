"""Script parameter registration via argparse.

`sc.arg(name, default=..., type=...)` registers a parameter and returns its
parsed value. The first call to any `arg()` triggers a lazy `parse_known_args`
against `sys.argv`, so the order of calls doesn't matter. Unknown args are
tolerated — the CLI wrapper can inject its own flags alongside script args.

`sc.from_json()` registers a `--from-json <path>` flag and returns the parsed
JSON content. One or more `--from-json` flags are accepted; payloads are
disambiguated by basename when more than one is supplied.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Callable

from scadwright.errors import SCADwrightError


_parser: argparse.ArgumentParser | None = None
_parsed: argparse.Namespace | None = None
_registered: dict[str, dict[str, Any]] = {}
_argv_override: list[str] | None = None
_json_registered: bool = False
_json_payloads: dict[str, Any] | None = None


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
    global _json_registered, _json_payloads
    _parser = None
    _parsed = None
    _registered = {}
    _argv_override = None
    _json_registered = False
    _json_payloads = None


def set_argv(argv: list[str] | None) -> None:
    """Override sys.argv for parsing. Used by the CLI. Pass None to restore default."""
    global _argv_override, _json_payloads
    _argv_override = argv
    _json_payloads = None
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


# =============================================================================
# `--from-json`: pass complex / nested data to a script via a JSON file.
# =============================================================================
#
# The CLI accepts one or more ``--from-json <path>`` flags. The script reads
# the parsed payload via ``from_json()`` (single-payload mode) or
# ``from_json("name.json")`` (named mode, basename-disambiguated). Multiple
# payloads with the same basename collide and surface as an error at parse
# time; a single payload satisfies both call shapes if the basename matches.


def _register_from_json() -> None:
    """Lazy-register the ``--from-json`` flag with the parser.

    Mirrors the lazy-registration pattern used by :func:`arg` so a script
    that never calls :func:`from_json` doesn't pollute its ``--help`` with
    an unused flag.
    """
    global _json_registered
    if _json_registered:
        return
    parser = _get_parser()
    parser.add_argument(
        "--from-json",
        dest="from_json",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "path to a JSON file whose parsed content the script reads via "
            "from_json() or from_json(name). May be supplied multiple times; "
            "payloads are disambiguated by basename."
        ),
    )
    _json_registered = True
    _flush_parse()


def _load_json_payloads() -> dict[str, Any]:
    """Parse every ``--from-json`` argv path; cache the result.

    Returns a dict mapping basename → parsed JSON content. Raises
    ``SCADwrightError`` on malformed input (file missing, invalid JSON,
    or basename collision across paths).
    """
    global _json_payloads
    if _json_payloads is not None:
        return _json_payloads
    ns = _ensure_parsed()
    paths: list[str] = list(getattr(ns, "from_json", []) or [])
    payloads: dict[str, Any] = {}
    for path in paths:
        basename = os.path.basename(path)
        if basename in payloads:
            raise SCADwrightError(
                f"--from-json basename collision: {basename!r} supplied "
                f"more than once. Disambiguate by passing files with "
                f"distinct names."
            )
        try:
            with open(path) as f:
                payloads[basename] = json.load(f)
        except FileNotFoundError:
            raise SCADwrightError(
                f"--from-json {path!r}: file not found"
            ) from None
        except json.JSONDecodeError as e:
            raise SCADwrightError(
                f"--from-json {path!r}: invalid JSON: {e}"
            ) from None
        except OSError as e:
            raise SCADwrightError(
                f"--from-json {path!r}: {e}"
            ) from None
    _json_payloads = payloads
    return payloads


def from_json(name: str | None = None, *, required: bool = False) -> Any:
    """Return the parsed content of a ``--from-json`` payload.

    Two call shapes:

    - ``from_json()`` — single-payload mode. Returns the lone payload's
      parsed content, or ``None`` if no ``--from-json`` was supplied. If
      multiple ``--from-json`` flags were given, raises with a hint to
      disambiguate by name.
    - ``from_json("design.json")`` — named mode. Returns the payload whose
      file basename matches ``name``, or ``None`` if no such payload was
      supplied. Matching is by basename only (a workflow that hands the
      script ``/tmp/long/path/design.json`` is selected by the script's
      ``from_json("design.json")`` regardless of the directory the runner
      chose).

    ``required=True`` turns a missing payload into a parse-time error
    (``sys.exit(2)`` via the parser's error path), surfaced in the same
    place a missing required ``arg()`` would.
    """
    _register_from_json()
    payloads = _load_json_payloads()

    if name is None:
        if not payloads:
            if required:
                _get_parser().error(
                    "--from-json is required (no payload supplied)"
                )
            return None
        if len(payloads) > 1:
            names = sorted(payloads)
            raise SCADwrightError(
                f"from_json() called without a name but {len(payloads)} "
                f"--from-json payloads supplied: {names!r}. Disambiguate "
                f"with from_json(\"<basename>\")."
            )
        # Single payload — return its content directly.
        return next(iter(payloads.values()))

    # Named mode: basename match.
    if name in payloads:
        return payloads[name]
    if required:
        supplied = sorted(payloads) or "none"
        _get_parser().error(
            f"--from-json {name!r} is required but was not supplied "
            f"(supplied: {supplied})"
        )
    return None
