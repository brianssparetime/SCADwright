"""SCAD emitter visitors for transform AST nodes."""

from __future__ import annotations

import io

from scadwright.ast.transforms import (
    Color,
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
from scadwright.emit.format import _fmt_bool, _fmt_color, _fmt_matrix, _fmt_num, _fmt_vec


class _TransformVisitorMixin:
    """Visitors for Translate, Rotate, Scale, Mirror, Color, Resize,
    MultMatrix, Projection, Offset, PreviewModifier.
    """

    def visit_Translate(self, n: Translate) -> None:
        # Coalesce chained Translates: `translate(a) translate(b) shape` →
        # `translate(a+b) shape`. Valid because translation commutes and
        # sums. Not extended to rotate/scale because those don't commute.
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
