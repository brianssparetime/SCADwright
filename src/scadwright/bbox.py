"""Bounding-box queries on AST trees.

Public API:
    sc.BBox          — frozen dataclass with min/max corners.
    sc.bbox(node)    — world-space AABB of any node, transforming through wrappers.
    sc.tight_bbox(n) — primitive-only tight bbox; raises on composed nodes.
    sc.resolved_transform(node) — world-space matrix at a top-level node (mostly identity).

Internals:
    _local_bbox(prim) — analytical AABB of a primitive in its local frame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scadwright.matrix import Matrix

Vec3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class BBox:
    """Axis-aligned bounding box. min and max are 3-tuples of floats."""

    min: Vec3
    max: Vec3

    @property
    def size(self) -> Vec3:
        return (self.max[0] - self.min[0], self.max[1] - self.min[1], self.max[2] - self.min[2])

    @property
    def center(self) -> Vec3:
        return (
            (self.min[0] + self.max[0]) / 2.0,
            (self.min[1] + self.max[1]) / 2.0,
            (self.min[2] + self.max[2]) / 2.0,
        )

    def contains(self, other: "BBox") -> bool:
        """True if `other` fits entirely within self."""
        return all(
            self.min[i] <= other.min[i] and other.max[i] <= self.max[i]
            for i in range(3)
        )

    def overlaps(self, other: "BBox") -> bool:
        """True if the two bboxes share any volume (touching counts)."""
        return all(
            self.min[i] <= other.max[i] and other.min[i] <= self.max[i]
            for i in range(3)
        )

    def union(self, other: "BBox") -> "BBox":
        return BBox(
            min=(
                min(self.min[0], other.min[0]),
                min(self.min[1], other.min[1]),
                min(self.min[2], other.min[2]),
            ),
            max=(
                max(self.max[0], other.max[0]),
                max(self.max[1], other.max[1]),
                max(self.max[2], other.max[2]),
            ),
        )

    def intersection(self, other: "BBox") -> "BBox | None":
        """Return overlap or None if disjoint."""
        lo = (
            max(self.min[0], other.min[0]),
            max(self.min[1], other.min[1]),
            max(self.min[2], other.min[2]),
        )
        hi = (
            min(self.max[0], other.max[0]),
            min(self.max[1], other.max[1]),
            min(self.max[2], other.max[2]),
        )
        if any(lo[i] > hi[i] for i in range(3)):
            return None
        return BBox(min=lo, max=hi)

    def transformed(self, m: Matrix) -> "BBox":
        """Apply m to the 8 corners, return AABB of the result."""
        corners = [
            (self.min[0], self.min[1], self.min[2]),
            (self.max[0], self.min[1], self.min[2]),
            (self.min[0], self.max[1], self.min[2]),
            (self.max[0], self.max[1], self.min[2]),
            (self.min[0], self.min[1], self.max[2]),
            (self.max[0], self.min[1], self.max[2]),
            (self.min[0], self.max[1], self.max[2]),
            (self.max[0], self.max[1], self.max[2]),
        ]
        transformed = [m.apply_point(c) for c in corners]
        xs = [p[0] for p in transformed]
        ys = [p[1] for p in transformed]
        zs = [p[2] for p in transformed]
        return BBox(min=(min(xs), min(ys), min(zs)), max=(max(xs), max(ys), max(zs)))

    def __repr__(self) -> str:
        return f"BBox(min={self.min}, max={self.max})"


# --- per-primitive analytical bbox ---


def _text_bbox_estimate(node) -> BBox:
    """Conservative bbox for a Text primitive.

    Without rasterizing the font, we approximate:
      - per-character width ≈ 0.6 * size * spacing
      - line height ≈ size (cap height + descender)
    Real rendered text may be slightly narrower. Downstream fit-checks
    stay on the conservative side.
    """
    n_chars = len(node.text)
    char_w = 0.6 * node.size * node.spacing
    width = char_w * n_chars
    size = node.size

    # Horizontal extent in "logical" layout direction.
    if node.halign == "left":
        lx0, lx1 = 0.0, width
    elif node.halign == "right":
        lx0, lx1 = -width, 0.0
    else:  # center
        lx0, lx1 = -width / 2.0, width / 2.0

    # Vertical extent with approximate ascender/descender split for baseline.
    if node.valign == "baseline":
        ly0, ly1 = -0.2 * size, 0.8 * size
    elif node.valign == "bottom":
        ly0, ly1 = 0.0, size
    elif node.valign == "top":
        ly0, ly1 = -size, 0.0
    else:  # center
        ly0, ly1 = -size / 2.0, size / 2.0

    # For top-to-bottom / bottom-to-top directions, width and height swap roles.
    if node.direction in ("ttb", "btt"):
        # Height is text stack (char height), width is the layout axis.
        stack = char_w * n_chars
        if node.direction == "ttb":
            y0, y1 = -stack, 0.0
        else:
            y0, y1 = 0.0, stack
        x0, x1 = -size / 2.0, size / 2.0
        return BBox(min=(x0, y0, 0.0), max=(x1, y1, 0.0))

    return BBox(min=(lx0, ly0, 0.0), max=(lx1, ly1, 0.0))


def _local_bbox(node) -> BBox:
    """Return the AABB of a primitive node in its own local frame.

    Raises TypeError for non-primitive nodes; the bbox visitor handles those.
    """
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

    if isinstance(node, Cube):
        sx, sy, sz = node.size
        cx, cy, cz = node.center
        # If centered on an axis, span is [-s/2, s/2]; otherwise [0, s].
        def span(s: float, centered: bool) -> tuple[float, float]:
            return (-s / 2.0, s / 2.0) if centered else (0.0, s)
        x0, x1 = span(sx, cx)
        y0, y1 = span(sy, cy)
        z0, z1 = span(sz, cz)
        return BBox(min=(x0, y0, z0), max=(x1, y1, z1))

    if isinstance(node, Sphere):
        r = node.r
        return BBox(min=(-r, -r, -r), max=(r, r, r))

    if isinstance(node, Cylinder):
        r = max(node.r1, node.r2)
        if node.center:
            return BBox(min=(-r, -r, -node.h / 2.0), max=(r, r, node.h / 2.0))
        return BBox(min=(-r, -r, 0.0), max=(r, r, node.h))

    if isinstance(node, Polyhedron):
        xs = [p[0] for p in node.points]
        ys = [p[1] for p in node.points]
        zs = [p[2] for p in node.points]
        return BBox(min=(min(xs), min(ys), min(zs)), max=(max(xs), max(ys), max(zs)))

    if isinstance(node, Square):
        sx, sy = node.size
        cx, cy = node.center
        x0, x1 = (-sx / 2.0, sx / 2.0) if cx else (0.0, sx)
        y0, y1 = (-sy / 2.0, sy / 2.0) if cy else (0.0, sy)
        return BBox(min=(x0, y0, 0.0), max=(x1, y1, 0.0))

    if isinstance(node, Circle):
        r = node.r
        return BBox(min=(-r, -r, 0.0), max=(r, r, 0.0))

    if isinstance(node, Polygon):
        xs = [p[0] for p in node.points]
        ys = [p[1] for p in node.points]
        return BBox(min=(min(xs), min(ys), 0.0), max=(max(xs), max(ys), 0.0))

    if isinstance(node, Text):
        # Explicit hint wins over the heuristic estimate.
        if node.bbox_hint is not None:
            mn, mx = node.bbox_hint
            return BBox(min=mn, max=mx)
        return _text_bbox_estimate(node)

    if isinstance(node, Surface):
        # File extent unknown without reading it. Return degenerate; users
        # can wrap with a known container (e.g. intersection with a cube)
        # if they need a real bbox for placement checks.
        return BBox(min=(0.0, 0.0, 0.0), max=(0.0, 0.0, 0.0))

    if isinstance(node, ScadImport):
        # Priority: explicit user-provided hint > STL auto-parse > degenerate.
        if node.bbox_hint is not None:
            mn, mx = node.bbox_hint
            return BBox(min=mn, max=mx)
        if node.file.lower().endswith(".stl"):
            from scadwright._stl import stl_bbox as _stl_bbox

            parsed = _stl_bbox(node.file)
            if parsed is not None:
                mn, mx = parsed
                return BBox(min=mn, max=mx)
        return BBox(min=(0.0, 0.0, 0.0), max=(0.0, 0.0, 0.0))

    if isinstance(node, LinearExtrude):
        # Extrude takes the child's 2D bbox and stretches Z.
        from scadwright.bbox import bbox as _bbox  # late import avoids cycle

        child_bb = _bbox(node.child)
        scale = node.scale
        if isinstance(scale, tuple):
            sx, sy = float(scale[0]), float(scale[1])
        else:
            sx = sy = float(scale)
        h = node.height
        z0, z1 = (-h / 2.0, h / 2.0) if node.center else (0.0, h)

        if node.twist == 0.0:
            # Exact AABB: base = child bbox at z0; top = child bbox scaled about origin.
            # Union of the two envelopes is the tight result.
            bx0, by0 = child_bb.min[0], child_bb.min[1]
            bx1, by1 = child_bb.max[0], child_bb.max[1]
            # Top scales about the origin (SCAD's behavior for linear_extrude).
            tx0, tx1 = (bx0 * sx, bx1 * sx) if sx >= 0 else (bx1 * sx, bx0 * sx)
            ty0, ty1 = (by0 * sy, by1 * sy) if sy >= 0 else (by1 * sy, by0 * sy)
            return BBox(
                min=(min(bx0, tx0), min(by0, ty0), z0),
                max=(max(bx1, tx1), max(by1, ty1), z1),
            )

        # Twisted: the profile rotates continuously. A conservative (rotationally
        # symmetric) envelope is the circumscribed disc of the child AABB, scaled
        # by the largest post-scale factor along the extrusion.
        x_ext = max(abs(child_bb.min[0]), abs(child_bb.max[0]))
        y_ext = max(abs(child_bb.min[1]), abs(child_bb.max[1]))
        r_base = math.hypot(x_ext, y_ext)
        r = r_base * max(1.0, sx, sy)
        return BBox(min=(-r, -r, z0), max=(r, r, z1))

    if isinstance(node, RotateExtrude):
        from scadwright.bbox import bbox as _bbox

        child_bb = _bbox(node.child)
        z_min, z_max = child_bb.min[1], child_bb.max[1]
        # Radial band covered by the profile (allow profiles that cross X=0).
        r_lo = child_bb.min[0]
        r_hi = child_bb.max[0]
        if r_lo < 0:
            # Profile crosses the Z axis; annular lower bound collapses.
            r_inner = 0.0
            r_outer = max(abs(r_lo), abs(r_hi))
        else:
            r_inner = r_lo
            r_outer = r_hi

        if node.angle >= 360 or node.angle <= -360:
            return BBox(min=(-r_outer, -r_outer, z_min), max=(r_outer, r_outer, z_max))

        xmin, xmax, ymin, ymax = _arc_xy_bounds(r_inner, r_outer, 0.0, float(node.angle))
        return BBox(min=(xmin, ymin, z_min), max=(xmax, ymax, z_max))

    raise TypeError(f"_local_bbox: unsupported node type {type(node).__name__}")


# --- tight_bbox: primitives only. Composed nodes use sc.bbox(). ---


def tight_bbox(node) -> BBox:
    """Tight bbox for a primitive node only.

    For composed nodes (transforms, CSG, Components), use `sc.bbox()` —
    oriented bboxes through arbitrary transforms aren't supported.
    `tight_bbox` is the primitive-only API surface.
    """
    from scadwright.ast.csg import (
        Difference,
        Hull,
        Intersection,
        Minkowski,
        Union,
    )
    from scadwright.ast.custom import Custom
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
    from scadwright.component.base import Component

    composed_types = (
        Translate,
        Rotate,
        Scale,
        Mirror,
        Color,
        Resize,
        MultMatrix,
        Projection,
        Offset,
        PreviewModifier,
        ForceRender,
        Echo,
        Union,
        Difference,
        Intersection,
        Hull,
        Minkowski,
        Custom,
        Component,
    )
    if isinstance(node, composed_types):
        raise NotImplementedError(
            "tight_bbox: only primitives are supported; "
            "use sc.bbox() for composed nodes (returns AABB)"
        )
    return _local_bbox(node)


# --- bbox visitor ---


def bbox(node) -> BBox:
    """Return the world-space AABB of `node`.

    Composes through transforms (via matrix), CSG (per-op), Components
    (materialized), and custom transforms (expanded).
    """
    return _bbox_with_context(node, Matrix.identity())


def resolved_transform(node) -> Matrix:
    """Return the world-space transform at `node` (top-level: identity).

    Mostly useful inside Component.build() callers to ask "where am I?".
    Top-level callers always get identity (the transform visitor is internal).
    """
    return Matrix.identity()


def _arc_xy_bounds(
    r_inner: float, r_outer: float, theta0_deg: float, theta1_deg: float
) -> tuple[float, float, float, float]:
    """XY extents of the annular sector {(r cos θ, r sin θ) : r∈[r_inner,r_outer], θ in swept range}.

    The swept range goes from θ0 to θ1, honoring sign (θ1 < θ0 sweeps clockwise).
    Samples the two angular endpoints and every axis crossing (0, 90, 180, 270, ...)
    that lies within the swept range, at both radii.
    """
    lo = min(theta0_deg, theta1_deg)
    hi = max(theta0_deg, theta1_deg)

    angles_deg = [lo, hi]
    # Axis crossings: all multiples of 90° within [lo, hi].
    k_start = math.ceil(lo / 90.0)
    k_end = math.floor(hi / 90.0)
    for k in range(k_start, k_end + 1):
        angles_deg.append(k * 90.0)

    xs: list[float] = []
    ys: list[float] = []
    for a_deg in angles_deg:
        a = math.radians(a_deg)
        c, s = math.cos(a), math.sin(a)
        for r in (r_inner, r_outer):
            xs.append(r * c)
            ys.append(r * s)
    return (min(xs), max(xs), min(ys), max(ys))


def _resize_scale(child_size, new_size, auto) -> tuple[float, float, float]:
    """Per-axis scale factors for SCAD's resize(newsize, auto).

    Rules (per OpenSCAD):
      - child_size[i] == 0 : axis contributes nothing; scale = 1.
      - new_size[i] > 0    : scale = new_size[i] / child_size[i].
      - new_size[i] == 0 and auto[i] : scale = max of the explicit scales from
        axes with new_size > 0 (or 1.0 if none).
      - new_size[i] == 0 and not auto[i] : scale = 1 (leave the axis alone).
    """
    explicit = []
    for i in range(3):
        if child_size[i] != 0 and new_size[i] > 0:
            explicit.append(new_size[i] / child_size[i])
    auto_scale = max(explicit) if explicit else 1.0

    out: list[float] = []
    for i in range(3):
        if child_size[i] == 0:
            out.append(1.0)
        elif new_size[i] > 0:
            out.append(new_size[i] / child_size[i])
        elif auto[i]:
            out.append(auto_scale)
        else:
            out.append(1.0)
    return (out[0], out[1], out[2])


def _fold_child_bboxes(children, ctx: Matrix, combine) -> BBox:
    """Compute each child's bbox under ctx, then fold with `combine`."""
    it = iter(children)
    result = _bbox_with_context(next(it), ctx)
    for c in it:
        result = combine(result, _bbox_with_context(c, ctx))
    return result


def _bbox_with_context(node, ctx: Matrix) -> BBox:
    """Recursive helper threading the world transform context."""
    from scadwright.ast.csg import (
        Difference,
        Hull,
        Intersection,
        Minkowski,
        Union,
    )
    from scadwright.ast.custom import ChildrenMarker, Custom
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
    from scadwright.component.base import Component
    from scadwright.matrix import to_matrix

    # Components: recurse into the materialized tree (cache lives on the instance).
    if isinstance(node, Component):
        # Use cache if present.
        cached = getattr(node, "_bbox_cache", None)
        if cached is not None:
            # Cache holds the LOCAL bbox; transform by ctx.
            return cached.transformed(ctx)
        local = _bbox_with_context(node._get_built_tree(), Matrix.identity())
        try:
            object.__setattr__(node, "_bbox_cache", local)
        except Exception:
            pass
        return local.transformed(ctx)

    # Transforms: compose into context, recurse, return child bbox in transformed frame.
    if isinstance(node, (Translate, Rotate, Scale, Mirror, MultMatrix)):
        m = to_matrix(node)
        return _bbox_with_context(node.child, ctx @ m)

    # Projection: 3D -> 2D. Conservative: take child's XY extent, drop Z.
    if isinstance(node, Projection):
        child_bb = _bbox_with_context(node.child, Matrix.identity())
        return BBox(
            min=(child_bb.min[0], child_bb.min[1], 0.0),
            max=(child_bb.max[0], child_bb.max[1], 0.0),
        ).transformed(ctx)

    # Color: identity for spatial purposes.
    if isinstance(node, Color):
        return _bbox_with_context(node.child, ctx)

    # Preview modifiers: pass-through except `disable`, which treats child as absent.
    if isinstance(node, PreviewModifier):
        if node.mode == "disable":
            return BBox(min=(0, 0, 0), max=(0, 0, 0)).transformed(ctx)
        return _bbox_with_context(node.child, ctx)

    # ForceRender: purely a preview/debug hint, passes bbox through.
    if isinstance(node, ForceRender):
        return _bbox_with_context(node.child, ctx)

    # Echo: pass through child if present; bare echo is a zero-volume statement.
    if isinstance(node, Echo):
        if node.child is None:
            return BBox(min=(0, 0, 0), max=(0, 0, 0)).transformed(ctx)
        return _bbox_with_context(node.child, ctx)

    # Offset: child is 2D; expand or contract XY extent by |r| or |delta|.
    if isinstance(node, Offset):
        child_bb = _bbox_with_context(node.child, Matrix.identity())
        r = node.r if node.r is not None else node.delta
        r = float(r)
        x0, x1 = child_bb.min[0] - r, child_bb.max[0] + r
        y0, y1 = child_bb.min[1] - r, child_bb.max[1] + r
        # Negative offsets can flip the bbox inside out; collapse to degenerate.
        if x1 < x0 or y1 < y0:
            c = child_bb.center
            return BBox(min=(c[0], c[1], 0.0), max=(c[0], c[1], 0.0)).transformed(ctx)
        return BBox(min=(x0, y0, 0.0), max=(x1, y1, 0.0)).transformed(ctx)

    # Resize: compute child's bbox in current ctx then apply per-axis scale.
    if isinstance(node, Resize):
        # Child bbox in local frame (no extra ctx — we'll apply ctx after scaling).
        child_local = _bbox_with_context(node.child, Matrix.identity())
        scaled = child_local.transformed(Matrix.scale(*_resize_scale(child_local.size, node.new_size, node.auto)))
        return scaled.transformed(ctx)

    # Custom: expand and recurse.
    if isinstance(node, Custom):
        from scadwright._custom_transforms.base import get_transform

        t = get_transform(node.name)
        if t is None:
            raise ValueError(f"bbox: unregistered custom transform {node.name!r}")
        expanded = t.expand(node.child, **node.kwargs_dict())
        return _bbox_with_context(expanded, ctx)

    # ChildrenMarker has no spatial extent of its own — only appears in module
    # body rendering. If we see it here, return a degenerate bbox at origin.
    if isinstance(node, ChildrenMarker):
        return BBox(min=(0, 0, 0), max=(0, 0, 0)).transformed(ctx)

    # CSG.
    if isinstance(node, (Union, Hull)):
        # Hull is contained within the AABB of the union of operand bboxes.
        return _fold_child_bboxes(node.children, ctx, BBox.union)

    if isinstance(node, Difference):
        # Difference is at most as large as the first operand's bbox.
        return _bbox_with_context(node.children[0], ctx)

    if isinstance(node, Intersection):
        def _intersect(a: BBox, b: BBox) -> BBox:
            inter = a.intersection(b)
            if inter is None:
                # Disjoint → degenerate bbox at first operand's center (safe, conservative).
                return BBox(min=a.center, max=a.center)
            return inter

        return _fold_child_bboxes(node.children, ctx, _intersect)

    if isinstance(node, Minkowski):
        # Bbox of Minkowski sum: extents add componentwise.
        def _mink(a: BBox, b: BBox) -> BBox:
            return BBox(
                min=(a.min[0] + b.min[0], a.min[1] + b.min[1], a.min[2] + b.min[2]),
                max=(a.max[0] + b.max[0], a.max[1] + b.max[1], a.max[2] + b.max[2]),
            )

        return _fold_child_bboxes(node.children, ctx, _mink)

    # Primitive: take its local bbox, transform by ctx.
    local = _local_bbox(node)
    return local.transformed(ctx)
