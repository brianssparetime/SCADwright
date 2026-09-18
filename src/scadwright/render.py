"""High-level render() entry point."""

from __future__ import annotations

from pathlib import Path

from scadwright.ast.base import Node
from scadwright.emit import emit


# Most recent path passed to ``render()``. The CLI's preview/render
# subcommands read this so a script that does its own ``render(model,
# "out.scad")`` at module level (rather than exposing a top-level
# ``MODEL = …`` for the CLI to render) still works with
# ``scadwright preview script.py``: import the script, observe what it
# wrote, hand that to OpenSCAD. Reset to None on each fresh import via
# ``_reset_last_rendered_for_testing``.
_last_rendered_path: Path | None = None


def last_rendered_path() -> Path | None:
    """Return the path most recently passed to ``render()``, or None.

    Set as a side effect of every ``render()`` call. Cleared by the CLI
    between script imports.
    """
    return _last_rendered_path


def _reset_last_rendered_for_testing() -> None:
    """Test/CLI helper. Clears ``_last_rendered_path`` so the next
    ``render()`` call's value is observable in isolation."""
    global _last_rendered_path
    _last_rendered_path = None


def render(
    node: Node,
    path: str | Path,
    *,
    pretty: bool = True,
    debug: bool = False,
    banner: bool = True,
    glossary: bool = True,
    scad_use: list[str] | None = None,
    scad_include: list[str] | None = None,
) -> Path:
    """Write SCAD source for `node` to `path`. Returns the Path."""
    p = Path(path)
    # Make the directory the caller named. Writing into `build/` should
    # not require creating `build/` first; the "wrote ..." line names the
    # full path, so a mistyped directory shows up immediately.
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        emit(node, f, pretty=pretty, debug=debug, banner=banner,
             glossary=glossary,
             scad_use=scad_use, scad_include=scad_include)
    global _last_rendered_path
    _last_rendered_path = p
    return p
