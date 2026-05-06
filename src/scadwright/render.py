"""High-level render() entry point."""

from __future__ import annotations

from pathlib import Path

from scadwright.ast.base import Node
from scadwright.emit import emit


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
    dedup: bool = True,
    dedup_prim_threshold: int = 5,
) -> Path:
    """Write SCAD source for `node` to `path`. Returns the Path."""
    p = Path(path)
    with p.open("w", encoding="utf-8") as f:
        emit(node, f, pretty=pretty, debug=debug, banner=banner,
             glossary=glossary,
             scad_use=scad_use, scad_include=scad_include,
             dedup=dedup, dedup_prim_threshold=dedup_prim_threshold)
    return p
