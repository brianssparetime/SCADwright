"""Path generators for sweep operations.

Each function returns a list of (x, y, z) tuples representing a 3D path.
"""

from __future__ import annotations

import math


def helix_path(
    r: float,
    pitch: float,
    turns: float,
    *,
    points_per_turn: int = 36,
) -> list[tuple[float, float, float]]:
    """Generate a helical path.

    The helix is centered on the z-axis, starting at (r, 0, 0) and
    rising in +z.

    ``r`` is the helix radius, ``pitch`` is the z-rise per full turn,
    and ``turns`` is the number of turns (fractional values allowed).
    """
    total_points = max(2, int(turns * points_per_turn) + 1)
    total_angle = turns * 2 * math.pi
    total_height = turns * pitch
    points = []
    for i in range(total_points):
        t = i / (total_points - 1)
        angle = t * total_angle
        z = t * total_height
        points.append((r * math.cos(angle), r * math.sin(angle), z))
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
        raise ValueError(
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
        raise ValueError(
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
