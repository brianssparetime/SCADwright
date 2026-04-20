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
