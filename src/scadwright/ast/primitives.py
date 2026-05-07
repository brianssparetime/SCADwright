"""Primitive AST nodes."""

from __future__ import annotations

from dataclasses import dataclass, field

from scadwright.ast.base import Node


@dataclass(frozen=True)
class Cube(Node):
    size: tuple[float, float, float]
    # Per-axis center. All-True or all-False emit as SCAD's native center= kwarg;
    # mixed gets wrapped in a translate() at emit time.
    center: tuple[bool, bool, bool] = (False, False, False)

    def fillet(self, edges, *, r: float):
        """Round one or more edges of this cube. Sugar over ``FilletMask``.

        ``edges`` accepts a single edge name (e.g. ``"top_front"``), a list
        of names, or a group selector (``"top"`` / ``"bottom"`` /
        ``"vertical"`` for the four edges of that face / axis). The 12
        canonical edge names are face-pairs (``top_front``, ``top_back``,
        ``top_lside``, ``top_rside``, ``bottom_*``, ``front_lside``, etc.)
        using the framework's anchor-face vocabulary.

        Call ``.fillet()`` before any rotation; rotated primitives don't
        have this method by design — for those, use ``FilletMask`` manually.
        """
        from scadwright.ast._edge_fillets import cube_fillet
        return cube_fillet(self, edges, r=r)

    def chamfer(self, edges, *, size: float):
        """Chamfer (45° bevel) one or more edges of this cube. Same edge
        selector grammar as ``.fillet()``. Sugar over ``ChamferMask``.
        """
        from scadwright.ast._edge_fillets import cube_chamfer
        return cube_chamfer(self, edges, size=size)


@dataclass(frozen=True)
class Sphere(Node):
    r: float
    fn: float | None = None
    fa: float | None = None
    fs: float | None = None


@dataclass(frozen=True)
class Cylinder(Node):
    h: float
    # r1 and r2 always carry values; factory normalizes from r/d/r1/r2/d1/d2.
    r1: float
    r2: float
    center: bool = False
    fn: float | None = None
    fa: float | None = None
    fs: float | None = None

    def fillet(self, rim: str, *, r: float):
        """Round one of the cylinder's two rim edges (``"top_rim"`` or
        ``"bottom_rim"``). Sugar over a custom ``rotate_extrude`` cutter.

        Restricted to non-cone cylinders (r1 == r2). Cones raise; for
        cone rim fillets, build a custom ``rotate_extrude`` profile.

        Call ``.fillet()`` before any rotation; rotated primitives don't
        have this method by design.
        """
        from scadwright.ast._edge_fillets import cylinder_fillet
        return cylinder_fillet(self, rim, r=r)

    def chamfer(self, rim: str, *, size: float):
        """Chamfer (45° bevel) one of the cylinder's two rim edges. Same
        rim-name grammar as ``.fillet()``. Restricted to non-cone cylinders.
        """
        from scadwright.ast._edge_fillets import cylinder_chamfer
        return cylinder_chamfer(self, rim, size=size)


@dataclass(frozen=True)
class Polyhedron(Node):
    points: tuple[tuple[float, float, float], ...]
    faces: tuple[tuple[int, ...], ...]
    convexity: int | None = None


# --- 2D primitives ---


@dataclass(frozen=True)
class Square(Node):
    size: tuple[float, float]
    center: tuple[bool, bool] = (False, False)


@dataclass(frozen=True)
class Circle(Node):
    r: float
    fn: float | None = None
    fa: float | None = None
    fs: float | None = None


@dataclass(frozen=True)
class Polygon(Node):
    points: tuple[tuple[float, float], ...]
    paths: tuple[tuple[int, ...], ...] | None = None
    convexity: int | None = None


@dataclass(frozen=True)
class ScadImport(Node):
    """Import external geometry via SCAD's import() — STL/SVG/DXF/3MF/OFF/AMF.

    `bbox_hint` is scadwright-side only (never emitted); it's how users declare
    a bbox for non-STL formats where scadwright can't determine it.
    """

    file: str
    bbox_hint: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
    convexity: int | None = None
    layer: str | None = None               # DXF
    origin: tuple[float, float] | None = None  # DXF
    scale: float | None = None             # DXF
    fn: float | None = None
    fa: float | None = None
    fs: float | None = None


@dataclass(frozen=True)
class Surface(Node):
    """Heightmap surface from a PNG or DAT file. Produces 3D geometry."""

    file: str
    center: bool = False
    invert: bool = False       # PNG only — inverts brightness mapping
    convexity: int | None = None


@dataclass(frozen=True)
class Text(Node):
    """2D text primitive. Emits as SCAD's `text(...)`.

    Bbox is estimated at `0.6 * size * spacing` per character when no explicit
    hint is given. Real glyphs vary: narrow sans-serifs are tighter, monospace
    and bold italics wider. Pass `bbox=...` (scadwright-side metadata, never
    emitted) for precise assembly checks.
    """

    text: str
    size: float = 10.0
    font: str | None = None
    halign: str = "left"       # "left" | "center" | "right"
    valign: str = "baseline"   # "top" | "center" | "baseline" | "bottom"
    spacing: float = 1.0
    direction: str = "ltr"     # "ltr" | "rtl" | "ttb" | "btt"
    language: str = "en"
    script: str = "latin"
    bbox_hint: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
    fn: float | None = None
    fa: float | None = None
    fs: float | None = None
