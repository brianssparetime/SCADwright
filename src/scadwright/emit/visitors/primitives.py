"""SCAD emitter visitors for 2D and 3D primitive AST nodes."""

from __future__ import annotations

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
from scadwright.emit.format import _fmt_bool, _fmt_num, _fmt_str, _fmt_vec


class _PrimitiveVisitorMixin:
    """Visitors for Cube, Sphere, Cylinder, Polyhedron, Square, Circle,
    Polygon, ScadImport, Surface, Text. Relies on the core emitter for
    ``_line``, ``_prefix``, ``_block``, ``_maybe_source_comment``, and
    ``_fmt_fn_kwargs``.
    """

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
