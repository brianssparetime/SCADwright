"""Sweep a 2D profile along a 3D path to produce a polyhedron.

The profile is a list of (x, y) points describing a closed 2D shape.
The path is a list of (x, y, z) points. At each path point, the profile
is oriented perpendicular to the path tangent using a rotation-minimizing
frame, then connected to adjacent cross-sections with triangle strips.
"""

from __future__ import annotations

import math

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
    """
    if len(profile) < 3:
        raise ValueError(f"path_extrude: profile needs at least 3 points, got {len(profile)}")
    if len(path) < 2:
        raise ValueError(f"path_extrude: path needs at least 2 points, got {len(path)}")

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

    # End caps (when not closed).
    if not closed:
        # Start cap: profile at path[0], reversed winding.
        start_face = list(range(n_profile - 1, -1, -1))
        faces.append(start_face)
        # End cap: profile at path[-1], normal winding.
        end_base = (n_path - 1) * n_profile
        end_face = list(range(end_base, end_base + n_profile))
        faces.append(end_face)

    return _polyhedron(points=points, faces=faces, convexity=convexity)


def circle_profile(r: float, *, segments: int = 16) -> list[tuple[float, float]]:
    """Generate a circular cross-section profile for use with path_extrude.

    Returns ``segments`` points counter-clockwise.
    """
    return [
        (r * math.cos(2 * math.pi * i / segments),
         r * math.sin(2 * math.pi * i / segments))
        for i in range(segments)
    ]


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
