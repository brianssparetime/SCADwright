"""Curve-based transforms: along_curve, bend, twist_copy."""

from __future__ import annotations

import math

from scadwright.bbox import bbox as _bbox
from scadwright.boolops import intersection, union
from scadwright.primitives import cube
from scadwright.transforms import transform


@transform("along_curve", inline=True)
def along_curve(node, *, path, count):
    """Place ``count`` copies of a shape along a 3D path with orientation.

    Each copy is translated to an evenly-spaced point on the path and
    rotated to face along the path direction. Useful for placing
    fasteners, decorations, or features along a curved rail.

    ``path`` is a list of (x, y, z) tuples.
    ``count`` is the number of copies to place.
    """
    n = len(path)
    if count < 1 or n < 2:
        return node

    copies = []
    for i in range(count):
        # Evenly space along the path.
        t = i / max(1, count - 1) if count > 1 else 0.0
        idx = t * (n - 1)
        idx_lo = int(idx)
        idx_hi = min(idx_lo + 1, n - 1)
        frac = idx - idx_lo

        # Interpolate position.
        p0 = path[idx_lo]
        p1 = path[idx_hi]
        px = p0[0] + frac * (p1[0] - p0[0])
        py = p0[1] + frac * (p1[1] - p0[1])
        pz = p0[2] + frac * (p1[2] - p0[2])

        # Tangent direction for orientation.
        if idx_hi > idx_lo:
            tx = p1[0] - p0[0]
            ty = p1[1] - p0[1]
            tz = p1[2] - p0[2]
        else:
            tx, ty, tz = 0, 0, 1

        tlen = math.sqrt(tx * tx + ty * ty + tz * tz)
        if tlen > 1e-10:
            tx, ty, tz = tx / tlen, ty / tlen, tz / tlen

        # Compute rotation from z-up to tangent direction.
        # Using axis-angle: axis = cross(z, tangent), angle = acos(dot(z, tangent))
        dot_z = tz  # dot((0,0,1), (tx,ty,tz))
        cross_x = -ty  # cross((0,0,1), (tx,ty,tz))
        cross_y = tx
        cross_z = 0.0
        cross_len = math.sqrt(cross_x**2 + cross_y**2)

        copy = node
        if cross_len > 1e-10:
            angle_deg = math.degrees(math.acos(max(-1.0, min(1.0, dot_z))))
            copy = copy.rotate(angle_deg, v=[cross_x, cross_y, cross_z])
        elif dot_z < 0:
            # Pointing straight down: 180-degree flip.
            copy = copy.rotate([180, 0, 0])

        copy = copy.translate([px, py, pz])
        copies.append(copy)

    return union(*copies)


@transform("bend", inline=True)
def bend(node, *, radius, axis="z"):
    """Wrap linear geometry around a cylinder of ``radius``.

    Bends the shape along the specified axis, wrapping it into a
    circular arc. The bend radius is measured from the center of the
    cylinder to the shape's midplane.

    ``axis`` is the bend axis: ``"x"``, ``"y"``, or ``"z"`` (default).

    This is an approximation using slicing: the shape is divided into
    segments, each rotated and translated to approximate the bend.
    """
    bb = _bbox(node)
    axis_map = {"x": 0, "y": 1, "z": 2}
    ax = axis_map.get(axis.lower(), 2)

    # The bend wraps the shape's extent along the bend axis into an arc.
    extent = bb.size[ax]
    if extent < 1e-10:
        return node

    arc_angle = extent / radius  # total arc angle in radians
    segments = max(2, int(arc_angle * 18 / math.pi))  # ~10 deg per segment

    segment_height = extent / segments
    segment_angle = math.degrees(arc_angle / segments)

    copies = []
    for i in range(segments):
        mid_angle = (i + 0.5) * segment_angle
        # Slice the shape at this z-level and rotate it around the bend axis.
        # Approximation: take a thin slice, rotate it.
        z_lo = bb.min[ax] + i * segment_height
        z_hi = z_lo + segment_height

        # Clip to this segment's z-range.
        clip_size = [bb.size[0] + 0.02, bb.size[1] + 0.02, bb.size[2] + 0.02]
        clip_pos = [bb.min[0] - 0.01, bb.min[1] - 0.01, bb.min[2] - 0.01]
        clip_size[ax] = segment_height + 0.01
        clip_pos[ax] = z_lo - 0.005

        clip = cube(clip_size).translate(clip_pos)
        segment = intersection(node, clip)

        # Move segment so its center is at origin on the bend axis,
        # then rotate by the cumulative angle.
        mid_z = z_lo + segment_height / 2
        shift = [0.0, 0.0, 0.0]
        shift[ax] = -mid_z
        segment = segment.translate(shift)

        # Translate outward by radius, then rotate.
        if ax == 2:
            segment = segment.right(radius).rotate([0, 0, mid_angle])
        elif ax == 0:
            segment = segment.back(radius).rotate([mid_angle, 0, 0])
        else:
            segment = segment.up(radius).rotate([0, mid_angle, 0])

        copies.append(segment)

    return union(*copies)


@transform("twist_copy", inline=True)
def twist_copy(node, *, angle, count):
    """Stacked copies of a shape with incremental rotation.

    Creates ``count`` copies, each rotated by ``angle`` degrees
    relative to the previous one around the z-axis. The first copy
    is unrotated.

    Useful for creating turbine blades, decorative patterns, or
    fan-like arrays.
    """
    if count < 1:
        return node

    copies = []
    bb = _bbox(node)
    height = bb.size[2]

    for i in range(count):
        copy = node.rotate([0, 0, angle * i]).up(height * i)
        copies.append(copy)

    return union(*copies)
