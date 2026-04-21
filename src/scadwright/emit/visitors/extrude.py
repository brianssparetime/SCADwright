"""SCAD emitter visitors for extrusion AST nodes."""

from __future__ import annotations

from scadwright.ast.extrude import LinearExtrude, RotateExtrude
from scadwright.emit.format import _fmt_bool, _fmt_num, _fmt_vec


class _ExtrudeVisitorMixin:
    """Visitors for LinearExtrude and RotateExtrude."""

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
