"""SCAD emitter: AST -> OpenSCAD source.

``SCADEmitter`` aggregates per-category visitor mixins from ``.visitors``
and provides the emission core: output buffering/indent, source-location
comments, ``$fn``/``$fa``/``$fs`` hoisting, and the ``emit_root`` entry
point that writes the file preamble (banner, use/include, hoisted
globals, viewpoint, hoisted modules) before the body.
"""

from __future__ import annotations

import io
import time
from typing import Any, TextIO

from scadwright._logging import get_logger
from scadwright.ast.base import Node
from scadwright.emit.format import _fmt_num, _fmt_vec
from scadwright.emit.visitor import Emitter
from scadwright.emit.visitors import (
    _CSGVisitorMixin,
    _ExtrudeVisitorMixin,
    _PrimitiveVisitorMixin,
    _SpecialVisitorMixin,
    _TransformVisitorMixin,
)

_log = get_logger("scadwright.emit")


class SCADEmitter(
    _PrimitiveVisitorMixin,
    _TransformVisitorMixin,
    _CSGVisitorMixin,
    _ExtrudeVisitorMixin,
    _SpecialVisitorMixin,
    Emitter,
):
    """Stream-based SCAD emitter. Call ``emit_root(root)`` to write output.

    Per-node ``visit_X`` methods live in ``.visitors`` mixins; this class
    owns the output stream, indent state, and the cross-cutting concerns
    (hoisting, banners, preamble).
    """

    def __init__(
        self,
        out: TextIO,
        *,
        pretty: bool = True,
        debug: bool = False,
        banner: bool = True,
        section_labels: bool = True,
        glossary: bool = True,
        scad_use: list[str] | None = None,
        scad_include: list[str] | None = None,
    ):
        self.out = out
        self.pretty = pretty
        self.debug = debug
        self.banner = banner
        self.section_labels = section_labels
        self.glossary = glossary
        self.scad_use = list(scad_use) if scad_use else []
        self.scad_include = list(scad_include) if scad_include else []
        self.indent = 0
        # Module hoisting state for custom transforms.
        # _module_defs: hash -> "module name(params) { body }\n" SCAD source.
        # _module_call_names: hash -> module name string.
        self._module_defs: dict[str, str] = {}
        self._module_call_names: dict[str, str] = {}
        # Hoisted resolution values: if every primitive/extrude sets the same
        # $fn (resp. $fa/$fs), we emit it once as a file-top global and
        # suppress it at call sites. Populated by a pre-pass in emit_root.
        self._hoisted_fn: Any = None
        self._hoisted_fa: Any = None
        self._hoisted_fs: Any = None

    # --- output helpers ---

    def _prefix(self) -> str:
        return "    " * self.indent if self.pretty else ""

    def _nl(self) -> str:
        return "\n" if self.pretty else " "

    def _line(self, s: str) -> None:
        self.out.write(self._prefix() + s + self._nl())

    def _block(self, body) -> None:
        self.out.write(" {" + self._nl())
        self.indent += 1
        body()
        self.indent -= 1
        self.out.write(self._prefix() + "}" + self._nl())

    def _maybe_source_comment(self, node: Node) -> None:
        if self.debug and node.source_location is not None:
            self._line(f"// {node.source_location}")

    def _emit_wrap(self, n: Node, op: str, args: str, child: Node) -> None:
        """Emit `op(args) { visit(child) }`. Args may be empty."""
        self._maybe_source_comment(n)
        call = f"{op}({args})"
        self.out.write(self._prefix() + call)
        self._block(lambda: self.visit(child))

    def _dominant_value_for(self, node: Node, attr: str):
        """Walk the emitted tree collecting `node.<attr>` for every node
        that carries it. If every non-None value is the same, return that
        value (we'll hoist it). Otherwise return None (don't hoist)."""
        seen: set = set()
        stack: list[Node] = [node]
        while stack:
            n = stack.pop()
            # Resolve a Component to its built tree. Let build failures
            # propagate — hiding them here just defers the same crash to
            # the real emit walk with less context.
            from scadwright.component.base import Component
            if isinstance(n, Component):
                n = n._get_built_tree()
            # Resolve an inline Custom to its expansion (same as flattening).
            resolved = self._resolve_inline_custom(n)
            if resolved is not n:
                stack.append(resolved)
                continue
            v = getattr(n, attr, None)
            if v is not None:
                # Only hoist if hashable — skip symbolic expressions etc.
                try:
                    seen.add(v)
                except TypeError:
                    return None
                if len(seen) > 1:
                    return None
            # Descend into children the uniform way.
            for slot in ("child", "children"):
                if hasattr(n, slot):
                    c = getattr(n, slot)
                    if isinstance(c, (list, tuple)):
                        stack.extend(c)
                    elif c is not None:
                        stack.append(c)
        return next(iter(seen)) if len(seen) == 1 else None

    def _fmt_fn_kwargs(self, fn, fa, fs) -> str:
        """Format $fn/$fa/$fs kwargs. Values that match a hoisted file-top
        default are suppressed — they're set once as a global in the file
        preamble instead of repeated at every call site."""
        parts = []
        if fn is not None and fn != self._hoisted_fn:
            parts.append(f"$fn={_fmt_num(fn)}")
        if fa is not None and fa != self._hoisted_fa:
            parts.append(f"$fa={_fmt_num(fa)}")
        if fs is not None and fs != self._hoisted_fs:
            parts.append(f"$fs={_fmt_num(fs)}")
        return ", ".join(parts)

    # --- entry point ---

    def emit_root(self, node: Node) -> None:
        # Pre-pass: collect fn/fa/fs values across all primitives/extrudes. If
        # exactly one non-None value appears for any of them, we hoist it to
        # a file-top `$fn = N;` / `$fa = N;` / `$fs = N;` declaration and
        # suppress it at the call sites. If there's any disagreement (more
        # than one distinct value) we leave that field per-call.
        self._hoisted_fn = self._dominant_value_for(node, "fn")
        self._hoisted_fa = self._dominant_value_for(node, "fa")
        self._hoisted_fs = self._dominant_value_for(node, "fs")

        # Render the body to a buffer so we can collect any hoisted modules first,
        # then prepend them to the actual output.
        body_buf = io.StringIO()
        real_out = self.out
        self.out = body_buf
        try:
            self.visit(node)
        finally:
            self.out = real_out
        nl = "\n" if self.pretty else " "
        # File header banner: identify what produced this file and remind
        # anyone reading that it's generated.
        if self.pretty and self.banner:
            self.out.write("// Generated by scadwright. Do not hand-edit —\n")
            self.out.write("// edit the Python source and regenerate.\n\n")
        # File-level preamble: use/include declarations come first.
        for path in self.scad_use:
            self.out.write(f"use <{path}>{nl}")
        for path in self.scad_include:
            self.out.write(f"include <{path}>{nl}")
        if (self.scad_use or self.scad_include) and self.pretty:
            self.out.write("\n")
        # Hoisted resolution globals: if $fn/$fa/$fs is uniform across the
        # tree, declare it once here instead of repeating at every call site.
        hoisted_wrote = False
        for name, value in (
            ("$fn", self._hoisted_fn),
            ("$fa", self._hoisted_fa),
            ("$fs", self._hoisted_fs),
        ):
            if value is not None:
                self.out.write(f"{name} = {_fmt_num(value)};{nl}")
                hoisted_wrote = True
        if hoisted_wrote and self.pretty:
            self.out.write("\n")
        # Viewpoint assignments (set $vpr/$vpt/$vpd/$vpf if a viewpoint is active).
        from scadwright.animation import current_viewpoint
        vp = current_viewpoint()
        if vp is not None:
            wrote_any = False
            for var, value in (
                ("$vpr", vp.rotation),
                ("$vpt", vp.target),
                ("$vpd", vp.distance),
                ("$vpf", vp.fov),
            ):
                if value is None:
                    continue
                if isinstance(value, (list, tuple)):
                    rendered = _fmt_vec(value)
                else:
                    rendered = _fmt_num(value)
                self.out.write(f"{var} = {rendered};{nl}")
                wrote_any = True
            if wrote_any and self.pretty:
                self.out.write("\n")
        # Module preamble (in registration order).
        for module_def in self._module_defs.values():
            self.out.write(module_def)
            if self.pretty:
                self.out.write("\n")
        self.out.write(body_buf.getvalue())


def emit(
    node: Node,
    out: TextIO,
    *,
    pretty: bool = True,
    debug: bool = False,
    banner: bool = True,
    section_labels: bool = True,
    glossary: bool = True,
    scad_use: list[str] | None = None,
    scad_include: list[str] | None = None,
) -> None:
    t0 = time.perf_counter()
    SCADEmitter(
        out, pretty=pretty, debug=debug, banner=banner,
        section_labels=section_labels, glossary=glossary,
        scad_use=scad_use, scad_include=scad_include,
    ).emit_root(node)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    # Attempt to measure output size if the stream supports tell(); otherwise skip.
    size = None
    try:
        size = out.tell()
    except (OSError, ValueError):
        # Best-effort size for logging; non-seekable streams (pipes, some
        # StringIO configurations) raise OSError or ValueError on tell().
        pass
    if size is not None:
        _log.info("emitted %d chars in %.2fms", size, elapsed_ms)
    else:
        _log.info("emitted in %.2fms", elapsed_ms)


def emit_str(
    node: Node,
    *,
    pretty: bool = True,
    debug: bool = False,
    banner: bool = True,
    section_labels: bool = True,
    glossary: bool = True,
    scad_use: list[str] | None = None,
    scad_include: list[str] | None = None,
) -> str:
    buf = io.StringIO()
    emit(node, buf, pretty=pretty, debug=debug, banner=banner,
         section_labels=section_labels, glossary=glossary,
         scad_use=scad_use, scad_include=scad_include)
    return buf.getvalue()
