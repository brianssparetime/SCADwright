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

    def fuse_extend(self, anchor, eps: float):
        """Locally extend this cube by ``eps`` along ``anchor``'s normal.

        Bumps ``size[axis]`` by ``eps`` and translates so the opposite
        face stays at its declared position. Per-axis center bool
        controls the translate delta (centered cubes grow symmetrically
        from the bump, so half the eps needs to be cancelled).

        Returns ``None`` for non-planar anchors (cubes don't have any,
        but defensive in case a caller passes one).
        """
        if anchor.kind != "planar":
            return None
        # Pick the axis the anchor's normal points along. For a true
        # bbox face anchor this is exact; the max-|component| selection
        # also tolerates small float drift from any computed anchor.
        axis = max(range(3), key=lambda i: abs(anchor.normal[i]))
        sign = 1 if anchor.normal[axis] > 0 else -1

        new_size = list(self.size)
        new_size[axis] += eps
        bumped = Cube(
            size=(new_size[0], new_size[1], new_size[2]),
            center=self.center,
            source_location=self.source_location,
        )

        # Translate so the OPPOSITE face stays put. A non-centered cube
        # grows in the +axis direction from the origin; a centered cube
        # grows symmetrically. Cases:
        #   center=False, sign=+1: bumped already extends top, no translate.
        #   center=False, sign=-1: shift -eps so the bottom moves out.
        #   center=True,  sign=±1: bumped extended ±eps/2 either way; shift
        #                          ±eps/2 to put the eps fully on the anchor side.
        if self.center[axis]:
            delta = sign * eps / 2.0
        elif sign < 0:
            delta = -eps
        else:
            delta = 0.0

        if delta == 0.0:
            return bumped
        v = [0.0, 0.0, 0.0]
        v[axis] = delta
        from scadwright.ast.transforms import Translate
        return Translate(
            v=(v[0], v[1], v[2]),
            child=bumped,
            source_location=self.source_location,
        )


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

    def cross_section_extend(self, anchor, eps: float):
        """Cross-section extension on a cylinder, with an explicit
        cone-apex check that the bbox-based detection can't catch.

        For a cone with ``r2=0`` the top disc face has zero area but
        the bbox at z=h is the full base disc — the dot-product check
        passes spuriously. Detect r=0 at the requested side here and
        raise with a cone-apex-specific message.
        """
        if anchor.kind != "planar":
            return None
        sign = 1 if anchor.normal[2] > 0 else -1
        if (sign > 0 and self.r2 == 0) or (sign < 0 and self.r1 == 0):
            from scadwright.errors import ValidationError
            side = "top" if sign > 0 else "bottom"
            raise ValidationError(
                f"cross-section fuse: cone apex at {side} (radius=0); the "
                f"bbox face at that plane is the full base disc, but the "
                f"actual material is a single point with no planar contact "
                f"region to fuse onto."
            )
        return super().cross_section_extend(anchor, eps)

    def fuse_extend(self, anchor, eps: float):
        """Locally extend this cylinder by ``eps`` along ``anchor``'s normal.

        Supports the planar top and bottom disc anchors. Cylindrical
        wall anchors (``kind="cylindrical"``) return ``None`` — there's
        no parametric lever for radial extension here.

        For a cone with ``r2=0`` (apex at top) extending the top is
        meaningless (zero-area face); same for ``r1=0`` extending the
        bottom. Both return ``None``.

        For a cone with non-zero radii at both ends, bumping ``h`` makes
        the cone slightly less steep — the apex angle changes by order
        ``eps/h``, invisible inside the eps band where the union sits.
        """
        if anchor.kind != "planar":
            return None
        sign = 1 if anchor.normal[2] > 0 else -1
        # Degenerate-apex check.
        if sign > 0 and self.r2 == 0:
            return None
        if sign < 0 and self.r1 == 0:
            return None

        bumped = Cylinder(
            h=self.h + eps,
            r1=self.r1,
            r2=self.r2,
            center=self.center,
            fn=self.fn,
            fa=self.fa,
            fs=self.fs,
            source_location=self.source_location,
        )

        if self.center:
            delta_z = sign * eps / 2.0
        elif sign < 0:
            delta_z = -eps
        else:
            delta_z = 0.0

        if delta_z == 0.0:
            return bumped
        from scadwright.ast.transforms import Translate
        return Translate(
            v=(0.0, 0.0, delta_z),
            child=bumped,
            source_location=self.source_location,
        )


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
