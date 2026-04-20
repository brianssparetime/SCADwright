"""Involute curve math for gear tooth profiles.

Standard involute gear geometry:
- module (m) = pitch diameter / teeth = the fundamental size parameter
- pitch_r = m * teeth / 2
- base_r = pitch_r * cos(pressure_angle)
- addendum = m (tooth height above pitch circle)
- dedendum = 1.25 * m (tooth depth below pitch circle)
- outer_r = pitch_r + addendum
- root_r = pitch_r - dedendum
"""

from __future__ import annotations

import math


def involute_point(base_r: float, angle: float) -> tuple[float, float]:
    """Point on an involute curve at parameter ``angle`` (radians)."""
    return (
        base_r * (math.cos(angle) + angle * math.sin(angle)),
        base_r * (math.sin(angle) - angle * math.cos(angle)),
    )


def involute_intersect_angle(base_r: float, target_r: float) -> float:
    """Involute parameter where the curve reaches ``target_r`` from the center.

    Solves: base_r * sqrt(1 + t^2) = target_r  =>  t = sqrt((target_r/base_r)^2 - 1)
    """
    if target_r <= base_r:
        return 0.0
    return math.sqrt((target_r / base_r) ** 2 - 1)


def gear_dimensions(module: float, teeth: int, pressure_angle: float = 20.0):
    """Compute standard gear circle radii.

    Returns (pitch_r, base_r, outer_r, root_r).
    """
    pa_rad = math.radians(pressure_angle)
    pitch_r = module * teeth / 2
    base_r = pitch_r * math.cos(pa_rad)
    addendum = module
    dedendum = 1.25 * module
    outer_r = pitch_r + addendum
    root_r = max(0, pitch_r - dedendum)
    return pitch_r, base_r, outer_r, root_r


def involute_tooth_profile(
    module: float,
    teeth: int,
    pressure_angle: float = 20.0,
    *,
    points_per_side: int = 10,
) -> list[tuple[float, float]]:
    """Generate the 2D polygon for a single gear tooth pair (tooth + gap).

    Returns a closed polygon representing one angular period (2*pi/teeth)
    of the gear profile, suitable for rotating and unioning to build the
    full gear.
    """
    pitch_r, base_r, outer_r, root_r = gear_dimensions(module, teeth, pressure_angle)

    # Angular half-thickness of the tooth at the pitch circle.
    # tooth_thickness_at_pitch = pi * module / 2
    # half_angle = tooth_thickness / (2 * pitch_r)
    tooth_thick_angle = math.pi / (2 * teeth)

    # Involute function: inv(a) = tan(a) - a
    pa_rad = math.radians(pressure_angle)
    inv_pa = math.tan(pa_rad) - pa_rad

    # The involute starts at the base circle. The angular offset between
    # the involute start (at base_r) and the tooth center (at pitch_r)
    # determines the tooth's angular width.
    half_tooth_angle = tooth_thick_angle + inv_pa

    # Build the right flank of the tooth (involute from base to outer).
    t_max = involute_intersect_angle(base_r, outer_r)
    right_flank = []
    for i in range(points_per_side + 1):
        t = t_max * i / points_per_side
        x, y = involute_point(base_r, t)
        # Rotate so the tooth is centered at angle=0.
        r = math.sqrt(x**2 + y**2)
        a = math.atan2(y, x) + half_tooth_angle
        right_flank.append((r * math.cos(a), r * math.sin(a)))

    # Left flank is a mirror of the right flank across the tooth center.
    left_flank = [(x, -y) for x, y in reversed(right_flank)]

    # Build the full tooth-period polygon: root arc -> left flank -> tip arc -> right flank -> root arc.
    period_angle = 2 * math.pi / teeth
    points = []

    # Root arc on the left side of the gap (from -period_angle/2 to left flank start).
    gap_start_angle = -period_angle / 2
    left_start_angle = math.atan2(left_flank[0][1], left_flank[0][0])
    arc_steps = max(2, points_per_side // 2)
    for i in range(arc_steps):
        a = gap_start_angle + (left_start_angle - gap_start_angle) * i / arc_steps
        points.append((root_r * math.cos(a), root_r * math.sin(a)))

    # Left flank.
    points.extend(left_flank)

    # Tip arc (from left flank end to right flank start).
    left_end_angle = math.atan2(left_flank[-1][1], left_flank[-1][0])
    right_start_angle = math.atan2(right_flank[0][1], right_flank[0][0])
    for i in range(1, arc_steps):
        a = left_end_angle + (right_start_angle - left_end_angle) * i / arc_steps
        points.append((outer_r * math.cos(a), outer_r * math.sin(a)))

    # Right flank.
    points.extend(right_flank)

    # Root arc on the right side of the gap (to period_angle/2).
    right_end_angle = math.atan2(right_flank[-1][1], right_flank[-1][0])
    gap_end_angle = period_angle / 2
    for i in range(1, arc_steps + 1):
        a = right_end_angle + (gap_end_angle - right_end_angle) * i / arc_steps
        points.append((root_r * math.cos(a), root_r * math.sin(a)))

    return points
