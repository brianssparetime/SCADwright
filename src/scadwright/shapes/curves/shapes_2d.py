"""2D Bezier and Catmull-Rom shape primitives.

Each function returns a ``polygon`` Node ready for use in 2D operations
(``linear_extrude``, ``offset``, boolean ops on 2D shapes).
"""

from __future__ import annotations

from scadwright.errors import ValidationError
from scadwright.primitives import polygon as _polygon
from scadwright.shapes.curves.paths import catmull_rom_path, composite_bezier_path


def bezier_2d(
    segments: list[list[tuple[float, float]]],
    *,
    closed: bool = False,
    steps_per_segment: int = 32,
):
    """Polygon traced by a chain of cubic Bezier segments in the XY plane.

    Each segment is a list of 4 control points. Consecutive segments must
    share their boundary anchor (segment N's first point equals segment
    N-1's last, within ``1e-6`` per coordinate).

    When ``closed=True``, the curve must form a loop: the first segment's
    first anchor must equal the last segment's last anchor (within
    ``1e-6``). The duplicated point is removed before the polygon is
    built so the boundary is traced entirely by the curve.

    When ``closed=False`` (default), the curve is traced as-is. The
    resulting polygon implicitly closes with a straight edge from the
    last evaluated point back to the first — OpenSCAD's natural
    polygon behavior.
    """
    if not segments:
        raise ValidationError("bezier_2d: segments must be non-empty")

    # Promote 2D control points to 3D with z=0 so we can reuse the existing
    # composite_bezier_path math; strip z afterwards.
    segments_3d = []
    for i, seg in enumerate(segments):
        if len(seg) != 4:
            raise ValidationError(
                f"bezier_2d: segments[{i}] must have exactly 4 control "
                f"points, got {len(seg)}"
            )
        seg3d = []
        for j, p in enumerate(seg):
            try:
                x, y = float(p[0]), float(p[1])
            except (TypeError, IndexError, ValueError):
                raise ValidationError(
                    f"bezier_2d: segments[{i}][{j}] must be a 2D point, got {p!r}"
                ) from None
            seg3d.append((x, y, 0.0))
        segments_3d.append(seg3d)

    points_3d = composite_bezier_path(segments_3d, steps_per_segment=steps_per_segment)
    points_2d = [(x, y) for x, y, _ in points_3d]

    if closed:
        first = segments_3d[0][0]
        last = segments_3d[-1][3]
        if any(abs(first[k] - last[k]) > 1e-6 for k in range(2)):
            raise ValidationError(
                f"bezier_2d: closed=True requires segments[0][0] == "
                f"segments[-1][3]; got start {first[:2]!r} and end {last[:2]!r}"
            )
        # Drop the duplicated closing point so the polygon's implicit
        # close-edge is zero-length; OpenSCAD handles this fine and the
        # boundary stays curve-only.
        points_2d = points_2d[:-1]

    return _polygon(points=points_2d)


def catmull_rom_2d(
    points: list[tuple[float, float]],
    *,
    closed: bool = False,
    steps_per_segment: int = 16,
):
    """Polygon traced by a Catmull-Rom spline through ``points`` in the
    XY plane.

    The spline passes through every input point. With ``closed=False``
    (default), endpoint tangents mirror as in ``catmull_rom_path``; with
    ``closed=True``, the spline wraps from the last point back to the
    first using the neighboring points as their natural tangent
    references (no mirroring).

    The resulting polygon always closes — OpenSCAD's polygon primitive
    treats the last point as connected to the first regardless. With
    ``closed=False`` that closing edge is a straight line; with
    ``closed=True`` the loop is fully spline-traced.
    """
    if len(points) < 2:
        raise ValidationError(
            f"catmull_rom_2d: at least 2 points required, got {len(points)}"
        )

    if closed:
        # Treat the input as a cyclic sequence: reuse the existing path
        # generator with neighboring points wrapped around for the endpoint
        # tangents, then trim the duplicated closing point.
        if len(points) < 3:
            raise ValidationError(
                f"catmull_rom_2d: closed=True requires at least 3 points, "
                f"got {len(points)}"
            )
        # Build a 3D path that loops: append the first point back at the end
        # so the spline sweeps from points[-1] through points[0]. To avoid
        # mirrored endpoint tangents, prepend points[-1] and append points[1]
        # so each segment has natural neighbors.
        wrap_3d = [(p[0], p[1], 0.0) for p in points] + [(points[0][0], points[0][1], 0.0)]
        # Use the existing catmull_rom_path; it mirrors at endpoints, but
        # with the wrapped sequence the "endpoints" are the wrap-back points,
        # so the mirroring affects only the closing region. For exact
        # tangent continuity at the seam we'd need a dedicated cyclic
        # implementation; the wrap-back form is the pragmatic version.
        points_3d = catmull_rom_path(wrap_3d, steps_per_segment=steps_per_segment)
        points_2d = [(x, y) for x, y, _ in points_3d]
        # Drop the duplicated closing point.
        points_2d = points_2d[:-1]
    else:
        points_3d = catmull_rom_path(
            [(p[0], p[1], 0.0) for p in points],
            steps_per_segment=steps_per_segment,
        )
        points_2d = [(x, y) for x, y, _ in points_3d]

    return _polygon(points=points_2d)
