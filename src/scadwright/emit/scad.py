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


def _capture_unsnapshotted_components(node) -> None:
    """Walk the AST; for any Component with a vacuous resolution snapshot
    (every axis ``None``) and a non-empty ambient context active, capture
    the context active here onto the Component.

    Forgiving fallback for the user who writes ``with resolution(): render(...)``
    rather than ``with resolution(): construct/wrap()``. Components whose
    snapshot already has values (set during construction or wrap inside
    a meaningful context) are left alone — their wrap-time context wins.
    Recursing into ``children`` and ``child`` covers the AST conventions.

    This runs from ``emit`` rather than from ``render`` so that the two
    agree: a resolution block around ``emit_str(model)`` means what a
    resolution block around ``render(model, path)`` means.
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


def _collect_tree_viewpoints(node) -> list:
    """Every camera carried by a ``WithViewpoint`` anywhere in ``node``.

    A ``@variant`` that declares a camera attaches it to the scene it
    returns, so the camera survives whatever the caller does with that
    scene next — rendering it directly, or composing it into a larger
    one. Built Component subtrees are walked too, so a camera can't hide
    behind a Component that happens to wrap a variant's scene.
    """
    from scadwright.ast.transforms import WithViewpoint
    from scadwright.component.base import Component

    found = []
    seen: set[int] = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if id(n) in seen:
            continue
        seen.add(id(n))
        if isinstance(n, WithViewpoint):
            found.append(n.viewpoint)
        if isinstance(n, Component):
            stack.append(n._get_built_tree())
            continue
        for slot in ("child", "children"):
            c = getattr(n, slot, None)
            if isinstance(c, (list, tuple)):
                stack.extend(c)
            elif c is not None:
                stack.append(c)
    return found


def _camera_key(vp) -> tuple:
    """A key that matches for two cameras saying the same thing.

    Plain numbers and sequences of them compare by value. Anything else
    — a ``$t`` expression, say, which answers every comparison with
    another expression rather than a yes or no — is keyed by identity,
    so two of those count as one camera only when they are the same
    object. That way an unreadable value makes two cameras look
    different, which is reported, rather than alike, which is not.
    """
    def key(v):
        if v is None or isinstance(v, (int, float, str, bool)):
            return v
        if isinstance(v, (list, tuple)):
            return tuple(key(x) for x in v)
        return ("id", id(v))

    return (key(vp.rotation), key(vp.target), key(vp.distance), key(vp.fov))


def _effective_viewpoint(node):
    """The camera to write at the top of the file, or None for none.

    Two sources can name one: a camera declared by a ``@variant``, which
    rides on the tree, and an enclosing ``with viewpoint(...)`` block,
    which is also how the CLI's ``--vpr`` and friends arrive. The block
    is the more immediate instruction, so it wins field by field, the
    same way an explicit ``fn=`` beats the value a ``resolution()``
    block supplies.

    Two variants' cameras in one scene have no such tiebreak, so that
    raises rather than quietly picking one.
    """
    from scadwright.animation import Viewpoint, current_viewpoint
    from scadwright.errors import ValidationError

    ambient = current_viewpoint()
    distinct = {}
    for vp in _collect_tree_viewpoints(node):
        distinct.setdefault(_camera_key(vp), vp)
    if len(distinct) > 1:
        rendered = "\n".join(f"  {vp}" for vp in distinct.values())
        raise ValidationError(
            f"this scene sets the camera {len(distinct)} different ways:\n"
            f"{rendered}\n"
            f"Each comes from a @variant that declares rotation, target, "
            f"distance or fov, and a file has room for one camera. Take "
            f"the camera off all but one of those variants, or put "
            f"`with viewpoint(...):` around the render to name the one "
            f"you want, which overrides every camera in the scene."
        )
    tree_vp = next(iter(distinct.values()), None)
    if tree_vp is None:
        return ambient
    if ambient is None:
        return tree_vp
    return Viewpoint(
        rotation=ambient.rotation if ambient.rotation is not None else tree_vp.rotation,
        target=ambient.target if ambient.target is not None else tree_vp.target,
        distance=ambient.distance if ambient.distance is not None else tree_vp.distance,
        fov=ambient.fov if ambient.fov is not None else tree_vp.fov,
    )


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
        # Module hoisting state for custom transforms and hoisted Components.
        # _module_defs: opaque key -> "module name(params) { body }\n" SCAD source.
        #   Custom uses a bare 8-char hex hash; Component dedup uses a
        #   "comp:<8-char-hex>" prefix to namespace the two cleanly.
        # _module_call_names: same key -> module name string.
        self._module_defs: dict[str, str] = {}
        self._module_call_names: dict[str, str] = {}
        # Component-dedup dispatch: id(component) -> module name. Populated
        # by the pre-pass in emit_root when dedup is enabled. visit_component
        # checks membership and emits a module call instead of inlining.
        self._hoisted_components: dict[int, str] = {}
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

    def _prerender_dedup_modules(self, node: Node) -> None:
        """Identify hoist-eligible Components and pre-render each as a module.

        Populates ``self._hoisted_components`` (id → module name) and
        ``self._module_defs`` / ``self._module_call_names`` (key → SCAD
        source / name). Two Component instances that canonicalize to the
        same tree_hash share one module def; both ids point at the same
        module name.
        """
        from scadwright.emit.dedup import collect_component_dedup_plan, select_hoists
        from scadwright.hashing import tree_hash

        plan = collect_component_dedup_plan(node)
        hoist_ids = select_hoists(plan)
        if not hoist_ids:
            return
        nl = "\n" if self.pretty else " "
        # Sort for deterministic module-emission order: by class name, then
        # by tree_hash. id() is process-local and would jitter goldens.
        ordered = sorted(
            (plan[cid].component for cid in hoist_ids),
            key=lambda c: (type(c).__name__, tree_hash(c)),
        )
        # Pass 1: register every hoist target's id → module name BEFORE any
        # body is rendered. A parent Component whose build tree references
        # a sibling Component that sorts later in `ordered` would otherwise
        # render its body with the inner reference still unregistered, and
        # `visit_component` would inline the inner subtree — exactly the
        # bloat this pre-pass is meant to remove.
        for component in ordered:
            h = tree_hash(component)[:8]
            self._hoisted_components[id(component)] = f"{type(component).__name__}_{h}"
        # Pass 2: render each module body. Nested hoisted Components that
        # appear inside a body now resolve through `_hoisted_components` to
        # a module call, regardless of iteration order.
        for component in ordered:
            cls_name = type(component).__name__
            h = tree_hash(component)[:8]
            module_name = f"{cls_name}_{h}"
            key = f"comp:{h}"
            if key in self._module_defs:
                # Another instance with the same canonical form already
                # registered this module; reuse the existing definition.
                continue
            module_buf = io.StringIO()
            saved_out = self.out
            saved_indent = self.indent
            self.out = module_buf
            self.indent = 1
            try:
                # Header + glossary go inside the module body so the human
                # reader sees them once, attached to the geometry.
                if self.pretty and self.section_labels:
                    self._line(f"// {cls_name}")
                    if self.glossary:
                        from scadwright.component.glossary import format_glossary
                        for line in format_glossary(component):
                            self._line(f"//{line}")
                self.visit(component._get_built_tree())
            finally:
                self.out = saved_out
                self.indent = saved_indent
            self._module_defs[key] = (
                f"module {module_name}() {{{nl}"
                f"{module_buf.getvalue()}"
                f"}}{nl}"
            )
            self._module_call_names[key] = module_name

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

        # Component-dedup pre-pass: identify Component instances referenced
        # multiple times and pre-render each one as a top-level module. The
        # body walk below will see them via _hoisted_components and emit a
        # module call instead of inlining the cached subtree. Dedup keys on
        # `id(component)` and content-addresses module names by tree_hash,
        # so two distinct instances that happen to canonicalize identically
        # share one module def.
        self._prerender_dedup_modules(node)

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
        vp = _effective_viewpoint(node)
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
    # Snapshot any Components whose resolution context wasn't captured at
    # construction or wrap time — typically the user wrote
    # ``with resolution(...): emit_str(...)`` rather than wrapping
    # construction. See ``Component._capture_resolution_context``.
    _capture_unsnapshotted_components(node)
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
