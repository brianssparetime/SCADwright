"""SCAD emitter: AST -> OpenSCAD source."""

from __future__ import annotations

import io
import time
from typing import TextIO

from scadwright._logging import get_logger

_log = get_logger("scadwright.emit")

from scadwright.ast.base import Node
from scadwright.ast.csg import Difference, Hull, Intersection, Minkowski, Union
from scadwright.ast.custom import CHILDREN, ChildrenMarker, Custom
from scadwright.ast.extrude import LinearExtrude, RotateExtrude
from scadwright.ast.primitives import (
    Circle,
    Cube,
    Cylinder,
    Polygon,
    Polyhedron,
    ScadImport,
    Sphere,
    Square,
    Surface,
    Text,
)
from scadwright.ast.transforms import (
    Color,
    Echo,
    ForceRender,
    Mirror,
    MultMatrix,
    Offset,
    PreviewModifier,
    Projection,
    Resize,
    Rotate,
    Scale,
    Translate,
)
from scadwright.emit.format import _fmt_bool, _fmt_color, _fmt_matrix, _fmt_num, _fmt_str, _fmt_value, _fmt_vec
from scadwright.emit.visitor import Emitter


class SCADEmitter(Emitter):
    """Stream-based SCAD emitter. Call visit(root) to write output."""

    def __init__(
        self,
        out: TextIO,
        *,
        pretty: bool = True,
        debug: bool = False,
        banner: bool = True,
        section_labels: bool = True,
        scad_use: list[str] | None = None,
        scad_include: list[str] | None = None,
    ):
        self.out = out
        self.pretty = pretty
        self.debug = debug
        self.banner = banner
        self.section_labels = section_labels
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

    # --- components ---

    def visit_component(self, n) -> None:
        # Emit a leading comment naming the Component class so a reader can
        # find where each part starts in the generated file.
        if self.pretty and self.section_labels:
            self._line(f"// {type(n).__name__}")
        self._maybe_source_comment(n)
        self.visit(n._get_built_tree())

    # --- custom transforms ---

    def visit_Custom(self, n: Custom) -> None:
        from scadwright.errors import EmitError
        from scadwright._custom_transforms.base import get_transform

        t = get_transform(n.name)
        if t is None:
            raise EmitError(
                f"unregistered transform: {n.name!r}",
                source_location=n.source_location,
            )
        kwargs = n.kwargs_dict()
        self._maybe_source_comment(n)

        if t.inline:
            # Inline expansion: call expand with the actual child, recurse.
            expanded = t.expand(n.child, **kwargs)
            self.visit(expanded)
            return

        # Hoisted form: render the module body once with the CHILDREN placeholder,
        # then emit a module call at the use site.
        h = self._hash_custom(n.name, n.kwargs)
        if h not in self._module_defs:
            module_name = f"{n.name}_{h}"
            body_tree = t.expand(CHILDREN, **kwargs)

            # Render the body into its own buffer with indent reset for the module body.
            module_buf = io.StringIO()
            saved_out = self.out
            saved_indent = self.indent
            self.out = module_buf
            self.indent = 1
            try:
                self.visit(body_tree)
            finally:
                self.out = saved_out
                self.indent = saved_indent

            # Module signature uses parameter names.
            sig_params = ", ".join(name for name, _ in n.kwargs)
            nl = "\n" if self.pretty else " "
            self._module_defs[h] = (
                f"module {module_name}({sig_params}) {{{nl}"
                f"{module_buf.getvalue()}"
                f"}}{nl}"
            )
            self._module_call_names[h] = module_name

        module_name = self._module_call_names[h]
        call_args = ", ".join(f"{name}={_fmt_value(val)}" for name, val in n.kwargs)
        # The source comment was already written at the top of visit_Custom;
        # use a raw wrap here to avoid duplicating it.
        self.out.write(self._prefix() + f"{module_name}({call_args})")
        self._block(lambda: self.visit(n.child))

    def visit_ChildrenMarker(self, n: ChildrenMarker) -> None:
        self._line("children();")

    @staticmethod
    def _hash_custom(name: str, kwargs: tuple) -> str:
        """Stable 8-char hex hash of (name, sorted kwargs)."""
        import hashlib

        key = repr((name, kwargs)).encode("utf-8")
        return hashlib.sha1(key).hexdigest()[:8]

    # --- primitives ---

    def visit_Cube(self, n: Cube) -> None:
        self._maybe_source_comment(n)
        size_txt = _fmt_vec(n.size)
        if all(n.center):
            self._line(f"cube({size_txt}, center=true);")
        elif not any(n.center):
            self._line(f"cube({size_txt}, center=false);")
        else:
            offsets = tuple(-s / 2.0 if c else 0.0 for s, c in zip(n.size, n.center))
            self.out.write(self._prefix() + f"translate({_fmt_vec(offsets)})")
            self._block(lambda: self._line(f"cube({size_txt}, center=false);"))

    def visit_Sphere(self, n: Sphere) -> None:
        self._maybe_source_comment(n)
        args = [f"r={_fmt_num(n.r)}"]
        extra = self._fmt_fn_kwargs(n.fn, n.fa, n.fs)
        if extra:
            args.append(extra)
        self._line(f"sphere({', '.join(args)});")

    def visit_Cylinder(self, n: Cylinder) -> None:
        self._maybe_source_comment(n)
        if n.r1 == n.r2:
            args = [f"h={_fmt_num(n.h)}", f"r={_fmt_num(n.r1)}"]
        else:
            args = [f"h={_fmt_num(n.h)}", f"r1={_fmt_num(n.r1)}", f"r2={_fmt_num(n.r2)}"]
        args.append(f"center={_fmt_bool(n.center)}")
        extra = self._fmt_fn_kwargs(n.fn, n.fa, n.fs)
        if extra:
            args.append(extra)
        self._line(f"cylinder({', '.join(args)});")

    def visit_Polyhedron(self, n: Polyhedron) -> None:
        self._maybe_source_comment(n)
        points_txt = "[" + ", ".join(_fmt_vec(p) for p in n.points) + "]"
        faces_txt = "[" + ", ".join(
            "[" + ", ".join(str(i) for i in face) + "]" for face in n.faces
        ) + "]"
        args = [f"points={points_txt}", f"faces={faces_txt}"]
        if n.convexity is not None:
            args.append(f"convexity={int(n.convexity)}")
        self._line(f"polyhedron({', '.join(args)});")

    # --- 2D primitives ---

    def visit_Square(self, n: Square) -> None:
        self._maybe_source_comment(n)
        size_txt = _fmt_vec(n.size)
        if all(n.center):
            self._line(f"square({size_txt}, center=true);")
        elif not any(n.center):
            self._line(f"square({size_txt}, center=false);")
        else:
            offsets = tuple(-s / 2.0 if c else 0.0 for s, c in zip(n.size, n.center))
            # 2D translate takes a 2D vector in SCAD.
            self.out.write(self._prefix() + f"translate({_fmt_vec(offsets)})")
            self._block(lambda: self._line(f"square({size_txt}, center=false);"))

    def visit_Circle(self, n: Circle) -> None:
        self._maybe_source_comment(n)
        args = [f"r={_fmt_num(n.r)}"]
        extra = self._fmt_fn_kwargs(n.fn, n.fa, n.fs)
        if extra:
            args.append(extra)
        self._line(f"circle({', '.join(args)});")

    def visit_Polygon(self, n: Polygon) -> None:
        self._maybe_source_comment(n)
        points_txt = "[" + ", ".join(_fmt_vec(p) for p in n.points) + "]"
        args = [f"points={points_txt}"]
        if n.paths is not None:
            paths_txt = "[" + ", ".join(
                "[" + ", ".join(str(i) for i in p) + "]" for p in n.paths
            ) + "]"
            args.append(f"paths={paths_txt}")
        if n.convexity is not None:
            args.append(f"convexity={int(n.convexity)}")
        self._line(f"polygon({', '.join(args)});")

    def visit_ScadImport(self, n: ScadImport) -> None:
        self._maybe_source_comment(n)
        args = [f"file={_fmt_str(n.file)}"]
        if n.convexity is not None:
            args.append(f"convexity={int(n.convexity)}")
        if n.layer is not None:
            args.append(f"layer={_fmt_str(n.layer)}")
        if n.origin is not None:
            args.append(f"origin={_fmt_vec(n.origin)}")
        if n.scale is not None:
            args.append(f"scale={_fmt_num(n.scale)}")
        extra = self._fmt_fn_kwargs(n.fn, n.fa, n.fs)
        if extra:
            args.append(extra)
        self._line(f"import({', '.join(args)});")

    def visit_Surface(self, n: Surface) -> None:
        self._maybe_source_comment(n)
        args = [f"file={_fmt_str(n.file)}"]
        if n.center:
            args.append("center=true")
        if n.invert:
            args.append("invert=true")
        if n.convexity is not None:
            args.append(f"convexity={int(n.convexity)}")
        self._line(f"surface({', '.join(args)});")

    def visit_Text(self, n: Text) -> None:
        self._maybe_source_comment(n)
        args = [_fmt_str(n.text)]
        if n.size != 10.0:
            args.append(f"size={_fmt_num(n.size)}")
        if n.font is not None:
            args.append(f"font={_fmt_str(n.font)}")
        if n.halign != "left":
            args.append(f"halign={_fmt_str(n.halign)}")
        if n.valign != "baseline":
            args.append(f"valign={_fmt_str(n.valign)}")
        if n.spacing != 1.0:
            args.append(f"spacing={_fmt_num(n.spacing)}")
        if n.direction != "ltr":
            args.append(f"direction={_fmt_str(n.direction)}")
        if n.language != "en":
            args.append(f"language={_fmt_str(n.language)}")
        if n.script != "latin":
            args.append(f"script={_fmt_str(n.script)}")
        extra = self._fmt_fn_kwargs(n.fn, n.fa, n.fs)
        if extra:
            args.append(extra)
        self._line(f"text({', '.join(args)});")

    # --- extrudes ---

    def visit_LinearExtrude(self, n: LinearExtrude) -> None:
        args = [f"height={_fmt_num(n.height)}", f"center={_fmt_bool(n.center)}"]
        if n.twist != 0.0:
            args.append(f"twist={_fmt_num(n.twist)}")
        if n.slices is not None:
            args.append(f"slices={int(n.slices)}")
        if isinstance(n.scale, tuple):
            args.append(f"scale={_fmt_vec(n.scale)}")
        elif n.scale != 1.0:
            args.append(f"scale={_fmt_num(n.scale)}")
        if n.convexity is not None:
            args.append(f"convexity={int(n.convexity)}")
        extra = self._fmt_fn_kwargs(n.fn, n.fa, n.fs)
        if extra:
            args.append(extra)
        self._emit_wrap(n, "linear_extrude", ", ".join(args), n.child)

    def visit_RotateExtrude(self, n: RotateExtrude) -> None:
        args = []
        if n.angle != 360.0:
            args.append(f"angle={_fmt_num(n.angle)}")
        if n.convexity is not None:
            args.append(f"convexity={int(n.convexity)}")
        extra = self._fmt_fn_kwargs(n.fn, n.fa, n.fs)
        if extra:
            args.append(extra)
        self._emit_wrap(n, "rotate_extrude", ", ".join(args), n.child)

    # --- CSG ---

    def _emit_csg(self, op: str, children: tuple[Node, ...]) -> None:
        self.out.write(self._prefix() + f"{op}()")
        def body():
            for c in children:
                self.visit(c)
        self._block(body)

    def _resolve_inline_custom(self, node: Node) -> Node:
        """If `node` is an inline Custom transform, return its expansion;
        otherwise return `node` unchanged. Flattening recurses through
        these so chained inline transforms that produce CSG (e.g. a
        `.finger_scoop()` that expands to a `difference()`) get pulled up
        into the enclosing op instead of stacking as nested one-argument
        ops."""
        from scadwright.ast.custom import Custom
        from scadwright._custom_transforms.base import get_transform

        if isinstance(node, Custom):
            t = get_transform(node.name)
            if t is not None and t.inline:
                return t.expand(node.child, **node.kwargs_dict())
        return node

    def _flatten_csg(self, op_type: type, children: tuple[Node, ...]) -> tuple[Node, ...]:
        """Pull children of same-type descendants into a flat list. Valid
        for commutative+associative operations (union, intersection, hull).
        Recurses through inline Custom transforms that resolve to op_type.
        """
        flat: list[Node] = []
        for c in children:
            resolved = self._resolve_inline_custom(c)
            if isinstance(resolved, op_type):
                flat.extend(self._flatten_csg(op_type, resolved.children))
            else:
                flat.append(c)
        return tuple(flat)

    def visit_Union(self, n: Union) -> None:
        self._maybe_source_comment(n)
        flat = self._flatten_csg(Union, n.children)
        if len(flat) == 1:
            self.visit(flat[0])
            return
        # At the top level, separate each child with a blank line so a
        # reader can see where one part ends and the next begins. Nested
        # unions emit tight (no extra blanks) to avoid whitespace bloat.
        if self.indent == 0 and self.pretty:
            self.out.write(self._prefix() + "union()")
            def body():
                first = True
                for c in flat:
                    if not first:
                        self.out.write("\n")
                    first = False
                    self.visit(c)
            self._block(body)
            return
        self._emit_csg("union", flat)

    def visit_Difference(self, n: Difference) -> None:
        self._maybe_source_comment(n)
        # Difference is associative in only one direction:
        # (A - B) - C == A - B - C, but A - (B - C) != A - B - C.
        # So we flatten only when the FIRST child resolves to a Difference
        # (possibly through an inline Custom wrapper).
        flat = list(n.children)
        while flat:
            resolved = self._resolve_inline_custom(flat[0])
            if not isinstance(resolved, Difference):
                break
            flat = list(resolved.children) + flat[1:]
        if len(flat) == 1:
            self.visit(flat[0])
            return
        self._emit_csg("difference", tuple(flat))

    def visit_Intersection(self, n: Intersection) -> None:
        self._maybe_source_comment(n)
        flat = self._flatten_csg(Intersection, n.children)
        if len(flat) == 1:
            self.visit(flat[0])
            return
        self._emit_csg("intersection", flat)

    def visit_Hull(self, n: Hull) -> None:
        self._maybe_source_comment(n)
        flat = self._flatten_csg(Hull, n.children)
        if len(flat) == 1:
            self.visit(flat[0])
            return
        self._emit_csg("hull", flat)

    def visit_Minkowski(self, n: Minkowski) -> None:
        self._maybe_source_comment(n)
        self._emit_csg("minkowski", n.children)

    # --- transforms ---

    def visit_Translate(self, n: Translate) -> None:
        # Coalesce chained Translates: `translate(a) translate(b) shape` →
        # `translate(a+b) shape`. Valid because translation commutes and
        # sums. Not extended to rotate/scale because those don't commute.
        from scadwright.animation import SymbolicExpr

        def _add(u, v):
            return tuple(a + b for a, b in zip(u, v))

        combined = tuple(n.v)
        child = n.child
        while isinstance(child, Translate):
            # Only coalesce if neither vector contains a SymbolicExpr —
            # summing symbolic expressions is fine, but mixing with floats
            # would change the SCAD output shape in a way that may surprise
            # debugging.
            combined = _add(combined, child.v)
            child = child.child
        self._emit_wrap(n, "translate", _fmt_vec(combined), child)

    def visit_Rotate(self, n: Rotate) -> None:
        if n.angles is not None:
            args = _fmt_vec(n.angles)
        else:
            args = f"a={_fmt_num(n.a)}, v={_fmt_vec(n.v)}"
        self._emit_wrap(n, "rotate", args, n.child)

    def visit_Scale(self, n: Scale) -> None:
        self._emit_wrap(n, "scale", _fmt_vec(n.factor), n.child)

    def visit_Mirror(self, n: Mirror) -> None:
        self._emit_wrap(n, "mirror", _fmt_vec(n.normal), n.child)

    def visit_Color(self, n: Color) -> None:
        # String-color with non-default alpha is the odd case: SCAD wants two args.
        if isinstance(n.c, str) and n.alpha != 1.0:
            args = f"{_fmt_color(n.c)}, {_fmt_num(n.alpha)}"
        else:
            args = _fmt_color(n.c, n.alpha)
        self._emit_wrap(n, "color", args, n.child)

    def visit_Resize(self, n: Resize) -> None:
        args = [f"newsize={_fmt_vec(n.new_size)}"]
        if any(n.auto):
            if all(n.auto):
                args.append("auto=true")
            else:
                auto_txt = "[" + ", ".join(_fmt_bool(b) for b in n.auto) + "]"
                args.append(f"auto={auto_txt}")
        self._emit_wrap(n, "resize", ", ".join(args), n.child)

    _PREVIEW_SIGILS = {
        "highlight": "#",
        "background": "%",
        "disable": "*",
        "only": "!",
    }

    def visit_PreviewModifier(self, n: PreviewModifier) -> None:
        self._maybe_source_comment(n)
        sigil = self._PREVIEW_SIGILS[n.mode]
        # Render the child to a buffer at the current indent level, then
        # splice the sigil in immediately before the first non-whitespace
        # character so `#translate([...]) { ... }` comes out clean.
        buf = io.StringIO()
        saved_out = self.out
        self.out = buf
        try:
            self.visit(n.child)
        finally:
            self.out = saved_out
        text = buf.getvalue()
        stripped = text.lstrip()
        leading = text[: len(text) - len(stripped)]
        self.out.write(leading + sigil + stripped)

    def visit_MultMatrix(self, n: MultMatrix) -> None:
        self._emit_wrap(n, "multmatrix", _fmt_matrix(n.matrix), n.child)

    def visit_Projection(self, n: Projection) -> None:
        args = "cut=true" if n.cut else ""
        self._emit_wrap(n, "projection", args, n.child)

    def visit_ForceRender(self, n: ForceRender) -> None:
        args = f"convexity={int(n.convexity)}" if n.convexity is not None else ""
        self._emit_wrap(n, "render", args, n.child)

    def visit_Echo(self, n: Echo) -> None:
        parts = []
        for name, value in n.values:
            if name is None:
                parts.append(_fmt_value(value))
            else:
                parts.append(f"{name}={_fmt_value(value)}")
        args = ", ".join(parts)
        if n.child is None:
            self._maybe_source_comment(n)
            self._line(f"echo({args});")
        else:
            self._emit_wrap(n, "echo", args, n.child)

    def visit_Offset(self, n: Offset) -> None:
        args = []
        if n.r is not None:
            args.append(f"r={_fmt_num(n.r)}")
        if n.delta is not None:
            args.append(f"delta={_fmt_num(n.delta)}")
        if n.chamfer:
            args.append("chamfer=true")
        extra = self._fmt_fn_kwargs(n.fn, n.fa, n.fs)
        if extra:
            args.append(extra)
        self._emit_wrap(n, "offset", ", ".join(args), n.child)


def emit(
    node: Node,
    out: TextIO,
    *,
    pretty: bool = True,
    debug: bool = False,
    banner: bool = True,
    section_labels: bool = True,
    scad_use: list[str] | None = None,
    scad_include: list[str] | None = None,
) -> None:
    t0 = time.perf_counter()
    SCADEmitter(
        out, pretty=pretty, debug=debug, banner=banner,
        section_labels=section_labels,
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
    scad_use: list[str] | None = None,
    scad_include: list[str] | None = None,
) -> str:
    buf = io.StringIO()
    emit(node, buf, pretty=pretty, debug=debug, banner=banner,
         section_labels=section_labels,
         scad_use=scad_use, scad_include=scad_include)
    return buf.getvalue()
