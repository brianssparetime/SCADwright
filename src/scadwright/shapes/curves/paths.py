"""Path generators for sweep operations.

Each function returns a list of (x, y, z) tuples representing a 3D path.
"""

from __future__ import annotations

import math

from scadwright.errors import ValidationError


def helix_path(
    r: float,
    pitch: float,
    turns: float,
    *,
    r_end: float | None = None,
    overhang: float = 0.0,
    points_per_turn: int = 36,
) -> list[tuple[float, float, float]]:
    """Generate a helical path.

    The helix is centered on the z-axis, starting at (r, 0, 0) and
    rising in +z over a nominal range of ``turns * pitch`` z and
    ``turns * 2π`` angle.

    ``r`` is the helix radius at the start, ``pitch`` is the z-rise per
    full turn, and ``turns`` is the number of turns (fractional values
    allowed). When ``r_end`` is given the radius lerps linearly from
    ``r`` at the bottom to ``r_end`` at the top, producing a tapered
    spiral (use ``r_end < r`` for a funnel that constricts upward,
    ``r_end > r`` for one that flares).

    ``overhang`` extends the path past the nominal start and end by the
    given z distance on each side, continuing the same helix (angle
    and tapered radius extrapolated linearly). Useful when sweeping a
    profile to bury the endcap inside an adjacent solid and avoid a
    visible seam at the joint.
    """
    if r_end is None:
        r_end = r
    total_angle = turns * 2 * math.pi
    total_height = turns * pitch
    if overhang and total_height <= 0:
        raise ValidationError(
            f"helix_path: overhang requires non-zero total_height "
            f"(turns * pitch); got turns={turns}, pitch={pitch}"
        )
    eps = overhang / total_height if total_height > 0 else 0.0
    ext = 1 + 2 * eps  # extended t-range spans (1 + 2*eps) units
    total_points = max(2, int(turns * ext * points_per_turn) + 1)
    points = []
    for i in range(total_points):
        u = i / (total_points - 1)            # u ∈ [0, 1] over extended path
        t = -eps + u * ext                     # t ∈ [-eps, 1 + eps]
        rt = (1 - t) * r + t * r_end
        if rt <= 0:
            raise ValidationError(
                f"helix_path: extrapolated radius is non-positive ({rt:.4f}) "
                f"at overhang={overhang}; reduce overhang or moderate the taper."
            )
        angle = t * total_angle
        z = t * total_height
        points.append((rt * math.cos(angle), rt * math.sin(angle), z))
    return points


def bezier_path(
    control_points: list[tuple[float, float, float]],
    *,
    steps: int = 32,
) -> list[tuple[float, float, float]]:
    """Generate a path along a cubic Bezier curve.

    ``control_points`` must have exactly 4 points: start, control1,
    control2, end. For longer curves, chain multiple calls.
    """
    if len(control_points) != 4:
        raise ValidationError(
            f"bezier_path requires exactly 4 control points, got {len(control_points)}"
        )
    p0, p1, p2, p3 = control_points
    points = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        # Cubic Bezier: B(t) = (1-t)^3*P0 + 3(1-t)^2*t*P1 + 3(1-t)*t^2*P2 + t^3*P3
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        z = u**3 * p0[2] + 3 * u**2 * t * p1[2] + 3 * u * t**2 * p2[2] + t**3 * p3[2]
        points.append((x, y, z))
    return points


def composite_bezier_path(
    segments: list[list[tuple[float, float, float]]],
    *,
    steps_per_segment: int = 32,
) -> list[tuple[float, float, float]]:
    """Generate a path along a chain of cubic Bezier segments.

    Each segment is a list of 4 control points. Consecutive segments must
    share their boundary anchor — segment N's first point must equal
    segment N-1's last (within ``1e-6`` per coordinate). Continuity beyond
    C0 (anchors meet) is the user's responsibility: place handles to
    align tangents if you want C1.

    For a single cubic Bezier with 4 control points, ``bezier_path``
    is the simpler form. ``composite_bezier_path([segment])`` produces
    the same output as ``bezier_path(segment)``.
    """
    if not segments:
        raise ValidationError(
            "composite_bezier_path: segments must be non-empty"
        )
    for i, seg in enumerate(segments):
        if len(seg) != 4:
            raise ValidationError(
                f"composite_bezier_path: segments[{i}] must have exactly 4 "
                f"control points, got {len(seg)}"
            )
        if i > 0:
            prev_end = segments[i - 1][3]
            this_start = seg[0]
            if any(abs(prev_end[k] - this_start[k]) > 1e-6 for k in range(3)):
                raise ValidationError(
                    f"composite_bezier_path: segments[{i}][0] {this_start!r} "
                    f"must equal segments[{i - 1}][3] {prev_end!r} "
                    f"(C0 continuity)"
                )

    points: list[tuple[float, float, float]] = []
    for i, seg in enumerate(segments):
        p0, p1, p2, p3 = seg
        # First segment writes its start point; later segments rely on the
        # previous segment's end point already being in the list.
        start = 0 if i == 0 else 1
        for j in range(start, steps_per_segment + 1):
            t = j / steps_per_segment
            u = 1 - t
            x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
            y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
            z = u**3 * p0[2] + 3 * u**2 * t * p1[2] + 3 * u * t**2 * p2[2] + t**3 * p3[2]
            points.append((x, y, z))
    return points


def arc_path(
    center: tuple[float, float, float],
    radius: float,
    start_angle: float,
    end_angle: float,
    *,
    normal: tuple[float, float, float] = (0.0, 0.0, 1.0),
    steps: int = 32,
) -> list[tuple[float, float, float]]:
    """Circular arc lying in the plane through ``center`` perpendicular
    to ``normal``.

    Angles are in degrees, measured counter-clockwise about ``normal``
    from a canonical reference direction in that plane: the projection
    of +X onto the plane, normalized. If +X is parallel or antiparallel
    to ``normal`` (within ``1e-6``), +Y is used as the reference instead.

    ``end_angle - start_angle`` is the sweep; negative values sweep
    clockwise. ``steps`` is the number of arc segments (so the result
    has ``steps + 1`` points).
    """
    if radius <= 0:
        raise ValidationError(
            f"arc_path: radius must be positive, got {radius}"
        )
    if steps < 1:
        raise ValidationError(
            f"arc_path: steps must be >= 1, got {steps}"
        )
    if abs(start_angle - end_angle) < 1e-9:
        raise ValidationError(
            f"arc_path: start_angle and end_angle are equal ({start_angle}); "
            f"the arc has zero length"
        )

    n = _normalize3(normal)
    if n is None:
        raise ValidationError(
            f"arc_path: normal must be a non-zero 3D vector, got {normal!r}"
        )

    # Build orthonormal basis (u, v) in the plane perpendicular to n.
    # u is the projection of +X onto the plane; if +X is (anti-)parallel
    # to n, fall back to +Y. v = n × u.
    if abs(n[0]) > 1.0 - 1e-6:
        # +X is along ±n; use +Y as the reference.
        ref = (0.0, 1.0, 0.0)
    else:
        ref = (1.0, 0.0, 0.0)
    # u = ref - (ref · n) n  (component of ref perpendicular to n)
    dot_rn = ref[0] * n[0] + ref[1] * n[1] + ref[2] * n[2]
    u_raw = (
        ref[0] - dot_rn * n[0],
        ref[1] - dot_rn * n[1],
        ref[2] - dot_rn * n[2],
    )
    u = _normalize3(u_raw)
    # v = n × u
    v = (
        n[1] * u[2] - n[2] * u[1],
        n[2] * u[0] - n[0] * u[2],
        n[0] * u[1] - n[1] * u[0],
    )

    cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
    sweep = end_angle - start_angle
    points = []
    for i in range(steps + 1):
        t = i / steps
        angle_deg = start_angle + t * sweep
        a = math.radians(angle_deg)
        c, s = math.cos(a), math.sin(a)
        points.append((
            cx + radius * (c * u[0] + s * v[0]),
            cy + radius * (c * u[1] + s * v[1]),
            cz + radius * (c * u[2] + s * v[2]),
        ))
    return points


def _normalize3(v):
    """Return ``v`` normalized, or ``None`` if it has zero length."""
    L = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if L < 1e-12:
        return None
    return (v[0] / L, v[1] / L, v[2] / L)


def catmull_rom_path(
    points: list[tuple[float, float, float]],
    *,
    steps_per_segment: int = 16,
) -> list[tuple[float, float, float]]:
    """Generate a smooth path through a sequence of points using Catmull-Rom splines.

    At least 2 points are required. The curve passes through every point.
    Endpoint tangents are mirrored from the adjacent segment.
    """
    n = len(points)
    if n < 2:
        raise ValidationError(
            f"catmull_rom_path requires at least 2 points, got {n}"
        )
    if n == 2:
        # Degenerate: straight line.
        result = []
        for i in range(steps_per_segment + 1):
            t = i / steps_per_segment
            result.append((
                points[0][0] + t * (points[1][0] - points[0][0]),
                points[0][1] + t * (points[1][1] - points[0][1]),
                points[0][2] + t * (points[1][2] - points[0][2]),
            ))
        return result

    result = []
    for seg in range(n - 1):
        # Catmull-Rom uses 4 control points: p_prev, p0, p1, p_next.
        # Mirror at endpoints.
        p_prev = points[seg - 1] if seg > 0 else _mirror(points[1], points[0])
        p0 = points[seg]
        p1 = points[seg + 1]
        p_next = points[seg + 2] if seg + 2 < n else _mirror(points[n - 2], points[n - 1])

        steps = steps_per_segment
        # Skip the last point of each segment except the final one, to
        # avoid duplicates at segment boundaries.
        end = steps + 1 if seg == n - 2 else steps
        for i in range(end):
            t = i / steps
            result.append(_catmull_rom_interp(p_prev, p0, p1, p_next, t))
    return result


def _mirror(anchor, center):
    """Reflect anchor across center."""
    return (
        2 * center[0] - anchor[0],
        2 * center[1] - anchor[1],
        2 * center[2] - anchor[2],
    )


def _catmull_rom_interp(p0, p1, p2, p3, t):
    """Evaluate the Catmull-Rom spline at parameter t in [0, 1]."""
    t2 = t * t
    t3 = t2 * t
    x = 0.5 * (
        (2 * p1[0])
        + (-p0[0] + p2[0]) * t
        + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
        + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
    )
    y = 0.5 * (
        (2 * p1[1])
        + (-p0[1] + p2[1]) * t
        + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
        + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
    )
    z = 0.5 * (
        (2 * p1[2])
        + (-p0[2] + p2[2]) * t
        + (2 * p0[2] - 5 * p1[2] + 4 * p2[2] - p3[2]) * t2
        + (-p0[2] + 3 * p1[2] - 3 * p2[2] + p3[2]) * t3
    )
    return (x, y, z)
