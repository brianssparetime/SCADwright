"""Sweep a 2D profile along a 3D path to produce a polyhedron.

The profile is a list of (x, y) points describing a closed 2D shape.
The path is a list of (x, y, z) points. At each path point, the profile
is oriented perpendicular to the path tangent using a rotation-minimizing
frame, then connected to adjacent cross-sections with triangle strips.
"""

from __future__ import annotations

import math

from scadwright.errors import ValidationError
from scadwright.primitives import polyhedron as _polyhedron


def path_extrude(
    profile: list[tuple[float, float]],
    path: list[tuple[float, float, float]],
    *,
    closed: bool = False,
    convexity: int = 10,
) -> "Node":
    """Sweep a 2D profile along a 3D path, returning a polyhedron.

    ``profile`` is a list of (x, y) points describing the cross-section.
    Points should be ordered counter-clockwise when viewed from the
    direction the path travels (looking into the profile from ahead).

    ``path`` is a list of (x, y, z) points.

    ``closed`` connects the last cross-section back to the first (for
    torus-like shapes). When False, flat end-caps are generated.

    The end-caps are fan-triangulated from the first profile vertex,
    which assumes a convex profile. Every shipping profile generator
    (``circle_profile``, ``almond_profile``, ``square_profile``,
    ``polygon_profile``, ``rounded_rect_profile``) is convex; for a
    custom non-convex profile, pre-triangulate or use ``closed=True``
    to skip caps entirely.
    """
    if len(profile) < 3:
        raise ValidationError(
            f"path_extrude: profile needs at least 3 points, got {len(profile)}"
        )
    if len(path) < 2:
        raise ValidationError(
            f"path_extrude: path needs at least 2 points, got {len(path)}"
        )

    frames = _compute_frames(path, closed)
    n_profile = len(profile)
    n_path = len(path)

    # Place the profile at each frame to generate 3D vertices.
    points = []
    for i, (origin, normal, binormal) in enumerate(frames):
        for px, py in profile:
            x = origin[0] + px * normal[0] + py * binormal[0]
            y = origin[1] + px * normal[1] + py * binormal[1]
            z = origin[2] + px * normal[2] + py * binormal[2]
            points.append((x, y, z))

    # Build faces connecting adjacent cross-sections.
    faces = []
    for i in range(n_path - 1 if not closed else n_path):
        i_next = (i + 1) % n_path
        base = i * n_profile
        base_next = i_next * n_profile
        for j in range(n_profile):
            j_next = (j + 1) % n_profile
            # Two triangles forming a quad between adjacent profile points.
            faces.append([
                base + j,
                base_next + j,
                base_next + j_next,
            ])
            faces.append([
                base + j,
                base_next + j_next,
                base + j_next,
            ])

    # End caps (when not closed). Each cap edge must run opposite to the
    # neighboring side-face edge for OpenSCAD to see a closed manifold.
    # Side faces have inward-pointing normals, so caps need inward normals
    # too: start cap winds with profile order, end cap winds reversed.
    #
    # Fan-triangulate the caps rather than emitting one n-vertex polygon:
    # the n profile points lie in their frame's plane mathematically but
    # drift by a few ULPs in float, and CGAL's planarity check is strict
    # enough to reject a 16-gon almond cap as non-planar. Triangles are
    # planar by construction. Fan from vertex 0 is valid for any convex
    # profile — every shipping profile generator (circle, almond, square,
    # polygon, rounded_rect) is convex.
    if not closed:
        for j in range(1, n_profile - 1):
            faces.append([0, j, j + 1])
        end_base = (n_path - 1) * n_profile
        last = end_base + n_profile - 1
        for j in range(1, n_profile - 1):
            faces.append([last, last - j, last - j - 1])

    return _polyhedron(points=points, faces=faces, convexity=convexity)


def loft(
    sections: list[list[tuple[float, float]]],
    path: list[tuple[float, float, float]],
    *,
    closed: bool = False,
    smooth: bool = False,
    smooth_steps: int = 8,
    convexity: int = 10,
) -> "Node":
    """Sweep multiple 2D cross-sections along a 3D path, producing a
    polyhedron whose surface interpolates between adjacent sections.

    ``sections[i]`` is placed at ``path[i]`` perpendicular to the path
    tangent (rotation-minimizing frame, same as ``path_extrude``). All
    sections must have the same number of vertices; use
    ``resample_profile`` to align profiles with different native point
    counts before lofting.

    Two interpolation modes:

    - **Ruled** (``smooth=False``, default) — triangle strips connect
      adjacent sections directly. Surface is piecewise-linear between
      input sections. Use for ducting transitions, square-to-round
      adapters, faceted tapers.
    - **Smooth** (``smooth=True``) — each vertex's "track" across the
      input sections is smoothed with a Catmull-Rom spline sampled at
      ``smooth_steps`` sub-sections per input segment. Surface is
      C1-continuous through every input section. Use for organic
      shapes and smooth transitions. With only 2 input sections, the
      spline degenerates to a straight line: ``smooth=True`` produces
      the same shape as ruled, just with more triangles. Pass 3+
      sections to see actual curvature.

    ``closed=True`` connects the last section back to the first (for
    ring-shaped lofts). Combination with ``smooth=True`` is not
    supported in this version — the closed-Catmull-Rom case adds
    enough complexity to defer until needed.

    End-caps are fan-triangulated from vertex 0 of each end section,
    matching ``path_extrude``'s convention. Sections should be convex
    for the cap winding to produce a valid polyhedron.
    """
    if len(sections) != len(path):
        raise ValidationError(
            f"loft: sections and path must have the same length, "
            f"got {len(sections)} sections and {len(path)} path points"
        )
    if len(sections) < 2:
        raise ValidationError(
            f"loft: needs at least 2 sections, got {len(sections)}"
        )
    n_profile = len(sections[0])
    if n_profile < 3:
        raise ValidationError(
            f"loft: each section needs at least 3 points, got {n_profile}"
        )
    for i, s in enumerate(sections):
        if len(s) != n_profile:
            raise ValidationError(
                f"loft: section {i} has {len(s)} points; expected "
                f"{n_profile} (matching section 0). Use resample_profile "
                f"to align profiles with different native point counts."
            )
    if smooth and closed and len(sections) < 3:
        raise ValidationError(
            f"loft: smooth=True with closed=True needs at least 3 "
            f"sections (periodic Catmull-Rom can't form a loop from 2 "
            f"points); got {len(sections)}"
        )
    frames = _compute_frames(path, closed)
    n_path = len(path)

    # Place each section at its frame to get an n_path × n_profile grid
    # of 3D vertices.
    sect_points: list[list[tuple[float, float, float]]] = []
    for i, (origin, normal, binormal) in enumerate(frames):
        sect = []
        for px, py in sections[i]:
            sect.append((
                origin[0] + px * normal[0] + py * binormal[0],
                origin[1] + px * normal[1] + py * binormal[1],
                origin[2] + px * normal[2] + py * binormal[2],
            ))
        sect_points.append(sect)

    if smooth:
        from scadwright.shapes.curves.paths import catmull_rom_path
        # For each vertex index j, smooth its track across sections.
        # ``closed=True`` produces a periodic Catmull-Rom (no endpoint
        # mirroring; tangents come from actual wraparound neighbors).
        tracks: list[list[tuple[float, float, float]]] = []
        for j in range(n_profile):
            track = [sect_points[i][j] for i in range(n_path)]
            tracks.append(catmull_rom_path(
                track, steps_per_segment=smooth_steps, closed=closed,
            ))
        # All tracks have the same length (controlled by smooth_steps
        # and n_path). Reassemble into per-sample sections.
        m_samples = len(tracks[0])
        sect_points = [
            [tracks[j][i] for j in range(n_profile)] for i in range(m_samples)
        ]

    # Flatten to a single points list and build the face list.
    n_sect = len(sect_points)
    points = [v for sect in sect_points for v in sect]

    faces = []
    for i in range(n_sect - 1 if not closed else n_sect):
        i_next = (i + 1) % n_sect
        base = i * n_profile
        base_next = i_next * n_profile
        for j in range(n_profile):
            j_next = (j + 1) % n_profile
            faces.append([
                base + j,
                base_next + j,
                base_next + j_next,
            ])
            faces.append([
                base + j,
                base_next + j_next,
                base + j_next,
            ])

    # End caps (when not closed). Same fan triangulation as path_extrude:
    # convex section assumed; start cap winds with profile order; end
    # cap winds reversed.
    if not closed:
        for j in range(1, n_profile - 1):
            faces.append([0, j, j + 1])
        end_base = (n_sect - 1) * n_profile
        last = end_base + n_profile - 1
        for j in range(1, n_profile - 1):
            faces.append([last, last - j, last - j - 1])

    return _polyhedron(points=points, faces=faces, convexity=convexity)


def resample_profile(
    profile: list[tuple[float, float]],
    n: int,
) -> list[tuple[float, float]]:
    """Resample a closed 2D profile to ``n`` evenly-spaced points along
    its perimeter.

    Useful for adapting profiles with different native vertex counts so
    they can be lofted together — ``loft`` requires all sections to have
    the same point count.

    The original profile's perimeter is preserved within floating-point
    precision; points are linearly interpolated along each edge of the
    source polygon, spaced so that consecutive output points have equal
    arc length.

    Returns ``n`` points counter-clockwise (assuming the input is
    counter-clockwise). The first output point coincides with the
    first input point.
    """
    if n < 3:
        raise ValidationError(
            f"resample_profile: n must be >= 3, got {n}"
        )
    if len(profile) < 3:
        raise ValidationError(
            f"resample_profile: profile needs at least 3 points, "
            f"got {len(profile)}"
        )

    # Edge lengths (closed polygon).
    n_src = len(profile)
    edge_lengths = []
    for i in range(n_src):
        x0, y0 = profile[i]
        x1, y1 = profile[(i + 1) % n_src]
        edge_lengths.append(math.hypot(x1 - x0, y1 - y0))
    perimeter = sum(edge_lengths)
    if perimeter == 0:
        raise ValidationError(
            "resample_profile: profile has zero perimeter (all points "
            "coincident); can't resample"
        )

    # Walk the perimeter in equal arc-length steps. ``edge_start_at`` is
    # the cumulative arc length at the start of the current edge; advance
    # past whole edges until the target falls inside one, then linearly
    # interpolate within it.
    step = perimeter / n
    result: list[tuple[float, float]] = []
    edge_i = 0
    edge_start_at = 0.0
    for k in range(n):
        target = k * step
        while (edge_i < n_src - 1
                and edge_start_at + edge_lengths[edge_i] <= target + 1e-12):
            edge_start_at += edge_lengths[edge_i]
            edge_i += 1
        distance_into_edge = target - edge_start_at
        L = edge_lengths[edge_i]
        t = distance_into_edge / L if L > 0 else 0.0
        x0, y0 = profile[edge_i]
        x1, y1 = profile[(edge_i + 1) % n_src]
        result.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))

    return result


def circle_profile(r: float, *, segments: int = 16) -> list[tuple[float, float]]:
    """Generate a circular cross-section profile for use with path_extrude.

    Returns ``segments`` points counter-clockwise.
    """
    return [
        (r * math.cos(2 * math.pi * i / segments),
         r * math.sin(2 * math.pi * i / segments))
        for i in range(segments)
    ]


def almond_profile(
    chord_r: float, sag: float, *, n_arc: int = 8,
) -> list[tuple[float, float]]:
    """Almond / lens / vesica cross-section: two mirrored circular segments
    arching above and below a shared chord on y=0.

    ``chord_r`` is the half-chord (so total chord width is ``2*chord_r``);
    ``sag`` is the maximum distance from the chord to either arc's apex
    (so total thickness is ``2*sag``). Returns ``2*n_arc`` points
    counter-clockwise — usable as a ``profile`` argument to
    ``path_extrude``.
    """
    if chord_r <= 0 or sag <= 0:
        raise ValidationError(
            f"almond_profile: chord_r and sag must be positive, "
            f"got chord_r={chord_r}, sag={sag}"
        )
    if n_arc < 2:
        raise ValidationError(
            f"almond_profile: n_arc must be >= 2, got {n_arc}"
        )
    seg_r = (chord_r * chord_r + sag * sag) / (2 * sag)
    half = math.asin(chord_r / seg_r)
    return [
        (s * seg_r * math.sin(t),
         s * (seg_r * math.cos(t) - (seg_r - sag)))
        for s in (+1, -1)
        for t in (half - 2 * half * i / n_arc for i in range(n_arc))
    ]


def square_profile(size, *, center: bool = True) -> list[tuple[float, float]]:
    """Square cross-section, four points counter-clockwise.

    ``size`` accepts a scalar (uniform) or ``(w, h)`` tuple. ``center=True``
    centers the square on the origin; ``center=False`` puts the lower-left
    corner at the origin.
    """
    if isinstance(size, (int, float)):
        w = h = float(size)
    else:
        try:
            w, h = float(size[0]), float(size[1])
        except (TypeError, IndexError, ValueError):
            raise ValidationError(
                f"square_profile: size must be a number or (w, h) tuple, got {size!r}"
            ) from None
    if w <= 0 or h <= 0:
        raise ValidationError(
            f"square_profile: dimensions must be positive, got w={w}, h={h}"
        )
    if center:
        return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    return [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]


def polygon_profile(
    sides: int, r: float, *, rotate: float = 0.0,
) -> list[tuple[float, float]]:
    """Regular n-gon cross-section inscribed in radius ``r``.

    Returns ``sides`` points counter-clockwise. By default the first
    vertex sits on the +X axis; ``rotate`` rotates that starting position
    by the given degrees CCW. Matches ``regular_polygon`` in
    ``scadwright.shapes.two_d``.
    """
    if sides < 3:
        raise ValidationError(
            f"polygon_profile: sides must be >= 3, got {sides}"
        )
    if r <= 0:
        raise ValidationError(
            f"polygon_profile: r must be positive, got {r}"
        )
    rotate_rad = math.radians(rotate)
    return [
        (r * math.cos(rotate_rad + 2 * math.pi * i / sides),
         r * math.sin(rotate_rad + 2 * math.pi * i / sides))
        for i in range(sides)
    ]


def rounded_rect_profile(
    x: float, y: float, r: float, *, segments_per_corner: int = 8,
) -> list[tuple[float, float]]:
    """Rounded-rectangle cross-section, centered on the origin.

    ``x`` and ``y`` are the overall width and height; ``r`` is the corner
    radius. Each corner is approximated by ``segments_per_corner`` arc
    segments. Points are returned counter-clockwise.

    A zero ``r`` produces a sharp-cornered rectangle (4 points).
    """
    if x <= 0 or y <= 0:
        raise ValidationError(
            f"rounded_rect_profile: x and y must be positive, got x={x}, y={y}"
        )
    if r < 0:
        raise ValidationError(
            f"rounded_rect_profile: r must be non-negative, got {r}"
        )
    if r * 2 > x or r * 2 > y:
        raise ValidationError(
            f"rounded_rect_profile: corner radius {r} exceeds half the smallest "
            f"side ({min(x, y)})"
        )
    if r == 0:
        return [(-x / 2, -y / 2), (x / 2, -y / 2), (x / 2, y / 2), (-x / 2, y / 2)]
    if segments_per_corner < 1:
        raise ValidationError(
            f"rounded_rect_profile: segments_per_corner must be >= 1, "
            f"got {segments_per_corner}"
        )

    # Corner centers (the four points where an inset rectangle's corners are).
    cx = x / 2 - r
    cy = y / 2 - r
    # Build CCW: start at (+X, -Y) corner's right-edge tangent, sweep up around.
    points = []
    # Each corner sweeps 90° CCW. Order: bottom-right, top-right, top-left, bottom-left.
    corners = [
        (cx, -cy, -math.pi / 2),  # bottom-right corner: arc from -90° to 0°
        (cx, cy, 0.0),            # top-right corner: arc from 0° to 90°
        (-cx, cy, math.pi / 2),   # top-left corner: arc from 90° to 180°
        (-cx, -cy, math.pi),      # bottom-left corner: arc from 180° to 270°
    ]
    for corner_x, corner_y, start_angle in corners:
        # Inclusive of start, exclusive of end: each corner contributes
        # segments_per_corner+1 points, but the last point of corner N
        # equals the first of corner N+1 only if r covers the full edge.
        # We include all segments_per_corner+1 points per corner; adjacent
        # corner endpoints land on the straight edge between them, which
        # is fine — polygon() treats the points as vertices in order.
        for i in range(segments_per_corner + 1):
            t = i / segments_per_corner
            angle = start_angle + t * math.pi / 2
            points.append((
                corner_x + r * math.cos(angle),
                corner_y + r * math.sin(angle),
            ))
    return points


def _compute_frames(path, closed):
    """Compute rotation-minimizing frames along the path.

    Returns a list of (origin, normal, binormal) tuples. The tangent at
    each point is the path direction; normal and binormal span the plane
    perpendicular to the tangent. The frame is propagated using parallel
    transport to minimize twisting.
    """
    n = len(path)

    # Compute tangent vectors.
    tangents = []
    for i in range(n):
        if i == 0:
            t = _sub(path[1], path[0])
        elif i == n - 1:
            t = _sub(path[n - 1], path[n - 2])
        else:
            t = _sub(path[i + 1], path[i - 1])
        tangents.append(_normalize(t))

    # Initial frame: choose a normal perpendicular to the first tangent.
    t0 = tangents[0]
    if abs(t0[2]) < 0.9:
        seed = (0.0, 0.0, 1.0)
    else:
        seed = (1.0, 0.0, 0.0)
    normal = _normalize(_cross(t0, seed))
    binormal = _cross(t0, normal)

    frames = [(path[0], normal, binormal)]

    # Propagate using parallel transport (rotation-minimizing frame).
    for i in range(1, n):
        t_prev = tangents[i - 1]
        t_curr = tangents[i]

        # Rotation axis and angle from t_prev to t_curr.
        axis = _cross(t_prev, t_curr)
        axis_len = _length(axis)
        if axis_len > 1e-10:
            axis = _scale_vec(1.0 / axis_len, axis)
            dot = max(-1.0, min(1.0, _dot(t_prev, t_curr)))
            angle = math.acos(dot)
            # Rotate normal and binormal.
            normal = _rotate_vec(normal, axis, angle)
            binormal = _rotate_vec(binormal, axis, angle)

        # Re-orthogonalize to avoid drift.
        binormal = _normalize(_cross(t_curr, normal))
        normal = _cross(binormal, t_curr)

        frames.append((path[i], normal, binormal))

    return frames


# --- vector math helpers ---

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )

def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

def _length(v):
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)

def _normalize(v):
    l = _length(v)
    if l < 1e-15:
        return (0.0, 0.0, 0.0)
    return (v[0] / l, v[1] / l, v[2] / l)

def _scale_vec(s, v):
    return (s * v[0], s * v[1], s * v[2])

def _rotate_vec(v, axis, angle):
    """Rodrigues' rotation: rotate v around axis by angle (radians)."""
    c = math.cos(angle)
    s = math.sin(angle)
    d = _dot(axis, v)
    cr = _cross(axis, v)
    return (
        v[0] * c + cr[0] * s + axis[0] * d * (1 - c),
        v[1] * c + cr[1] * s + axis[1] * d * (1 - c),
        v[2] * c + cr[2] * s + axis[2] * d * (1 - c),
    )
