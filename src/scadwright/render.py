"""High-level render() entry point."""

from __future__ import annotations

from pathlib import Path

from scadwright.ast.base import Node
from scadwright.emit import emit


def _capture_unsnapshotted_components(node: Node) -> None:
    """Walk the AST; for any Component with a vacuous resolution snapshot
    (every axis ``None``) and a non-empty ambient context active, capture
    render-time context onto the Component.

    Forgiving fallback for the user pattern of ``with resolution(): render(...)``
    rather than ``with resolution(): construct/wrap()``. Components whose
    snapshot already has values (set during construction or wrap inside
    a meaningful context) are left alone — their wrap-time context wins.
    Recursing into ``children`` and ``child`` covers the AST conventions.
    """
    from scadwright.api.resolution import current as _current_resolution
    from scadwright.component.base import Component

    ambient = _current_resolution()
    if all(v is None for v in ambient):
        # No render-time context to contribute; nothing to do.
        return

    def _walk(n):
        if isinstance(n, Component):
            snap = n._ctx_resolution
            if snap is None or all(v is None for v in snap):
                n._capture_resolution_context()
            # Don't recurse into n's already-built tree (if any) — its
            # nested Components will be handled when their parent frames
            # walk them, or via this Component's own snapshot at build.
            return
        children = getattr(n, "children", None)
        if children:
            for c in children:
                _walk(c)
        c = getattr(n, "child", None)
        if c is not None:
            _walk(c)

    _walk(node)


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
    # Snapshot any Components whose resolution context wasn't captured at
    # construction or wrap time — typically the user wrote
    # ``with resolution(...): render(...)`` rather than wrapping
    # construction. See ``Component._capture_resolution_context``.
    _capture_unsnapshotted_components(node)

    p = Path(path)
    with p.open("w", encoding="utf-8") as f:
        emit(node, f, pretty=pretty, debug=debug, banner=banner,
             glossary=glossary,
             scad_use=scad_use, scad_include=scad_include)
    return p
