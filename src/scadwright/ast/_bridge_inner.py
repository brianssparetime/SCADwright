"""Inner-wall bridge construction.

For a concave-inner curved host (``Tube.inner_wall``, ``Funnel.inner_wall``,
hollow ``Barrel.inner_wall``, or a hand-declared spherical-inner anchor),
``attach(..., bridge=True)`` clips the placed peg to the host's bore so
the peg's near-face *curves* to match the inner surface. The construction
is ``intersection(placed_peg, bore_extended)`` where ``bore_extended`` is
a primitive of the inner curvature, optionally expanded radially by
``eps`` to give a manifold-clean union with the host on the peg side.

This is the geometric inverse of the outer-bridge case: outer adds prism
material into an air gap; inner removes peg material that would
otherwise intrude into wall material. Same user-facing kwarg, different
operation under the hood. See ``docs/anchors.md`` for the asymmetry.
"""

from __future__ import annotations

import math


def _project_peg_axial_range(peg, host_axis, axis_origin):
    """Project the peg's bbox corners onto the host axis line. Returns
    ``(t_min, t_max)`` where ``t`` is the signed axial distance from
    ``axis_origin`` along ``host_axis``. Used to size the bore tightly
    along the host's axis so CGAL doesn't pay for unused volume.
    """
    from scadwright.bbox import bbox as _bbox

    bb = _bbox(peg)
    corners = [
        (bb.min[0] if i & 1 == 0 else bb.max[0],
         bb.min[1] if i & 2 == 0 else bb.max[1],
         bb.min[2] if i & 4 == 0 else bb.max[2])
        for i in range(8)
    ]
    ts = [
        (c[0] - axis_origin[0]) * host_axis[0]
        + (c[1] - axis_origin[1]) * host_axis[1]
        + (c[2] - axis_origin[2]) * host_axis[2]
        for c in corners
    ]
    return min(ts), max(ts)


def _rot_z_to_axis(target_axis):
    """Matrix that rotates +Z to the given unit axis (no translation)."""
    from scadwright.matrix import Matrix

    d = target_axis[2]
    if d > 1.0 - 1e-12:
        return Matrix.identity()
    if d < -1.0 + 1e-12:
        return Matrix.rotate_axis_angle(180.0, (1.0, 0.0, 0.0))
    rot_axis = (-target_axis[1], target_axis[0], 0.0)  # (0,0,1) x target
    angle = math.degrees(math.acos(max(-1.0, min(1.0, d))))
    return Matrix.rotate_axis_angle(angle, rot_axis)


def _place_along_host_axis(node, host_axis, axis_origin, length, t_center, loc):
    """Wrap ``node`` (built canonically along +Z with its center at the
    origin) in transforms that rotate +Z to ``host_axis`` and translate
    its center to ``axis_origin + t_center * host_axis``.
    """
    from scadwright.ast.transforms import MultMatrix
    from scadwright.matrix import Matrix

    rot = _rot_z_to_axis(host_axis)
    center_world = (
        axis_origin[0] + t_center * host_axis[0],
        axis_origin[1] + t_center * host_axis[1],
        axis_origin[2] + t_center * host_axis[2],
    )
    trans = Matrix.translate(center_world[0], center_world[1], center_world[2])
    m = trans @ rot
    return MultMatrix(matrix=m, child=node, source_location=loc)


def _build_inner_cylinder_bore(host_anchor, peg, eps, eps_overlap, loc):
    """Cylinder filling a cylindrical bore, axially sized to cover the peg.

    Radius = ``host_anchor.radius`` (+ ``eps`` when ``eps_overlap`` is
    True, so the peg gets an ``eps`` slab inside the wall material).
    Axially: spans the union of host length and the peg's projected
    extent, plus a small margin.
    """
    from scadwright.ast.placement import _axis_origin_for
    from scadwright.primitives import cylinder

    axis_origin = _axis_origin_for(host_anchor)
    if axis_origin is None:
        return None
    bore_r = host_anchor.radius + (eps if eps_overlap else 0.0)
    host_axis = host_anchor.axis
    host_length = host_anchor.length

    peg_t_min, peg_t_max = _project_peg_axial_range(peg, host_axis, axis_origin)
    host_t_min = -host_length / 2.0
    host_t_max = +host_length / 2.0
    t_min = min(peg_t_min, host_t_min) - eps
    t_max = max(peg_t_max, host_t_max) + eps
    total_h = t_max - t_min
    t_center = (t_min + t_max) / 2.0

    bore = cylinder(h=total_h, r=bore_r, center=True)
    return _place_along_host_axis(bore, host_axis, axis_origin, total_h, t_center, loc)


def _build_inner_cone_bore(host_anchor, peg, eps, eps_overlap, loc):
    """Truncated cone filling a conical bore. ``r1``/``r2`` enlarged by
    ``eps`` when ``eps_overlap``. The cone tapers along ``host_anchor.axis``.
    """
    from scadwright.ast.placement import _axis_origin_for
    from scadwright.primitives import cylinder

    axis_origin = _axis_origin_for(host_anchor)
    if axis_origin is None:
        return None
    r1 = host_anchor.r1
    r2 = host_anchor.r2
    if r1 is None or r2 is None:
        return None
    host_axis = host_anchor.axis
    host_length = host_anchor.length

    peg_t_min, peg_t_max = _project_peg_axial_range(peg, host_axis, axis_origin)
    host_t_min = -host_length / 2.0
    host_t_max = +host_length / 2.0
    t_min = min(peg_t_min, host_t_min) - eps
    t_max = max(peg_t_max, host_t_max) + eps

    # Linearly extrapolate the cone radii to the new axial range so the
    # cone profile keeps the host's slope outside the host's [-h/2, h/2].
    # Slope = (r2 - r1) / host_length.
    slope = (r2 - r1) / host_length if host_length > 0 else 0.0
    r1_ext = r1 + slope * (t_min - host_t_min)
    r2_ext = r2 + slope * (t_max - host_t_max)
    r1_ext = max(r1_ext + (eps if eps_overlap else 0.0), 0.0)
    r2_ext = max(r2_ext + (eps if eps_overlap else 0.0), 0.0)
    if r1_ext == 0.0 and r2_ext == 0.0:
        return None
    total_h = t_max - t_min
    t_center = (t_min + t_max) / 2.0

    bore = cylinder(h=total_h, r1=r1_ext, r2=r2_ext, center=True)
    return _place_along_host_axis(bore, host_axis, axis_origin, total_h, t_center, loc)


def _build_inner_meridional_bore(host_anchor, peg, eps, eps_overlap, loc):
    """Revolve the inner meridian arc into a solid of revolution. The arc
    is enlarged radially by ``eps`` when ``eps_overlap``.

    The meridional anchor carries ``meridian_r``, ``mid_r``, ``meridian_s``,
    ``end_r``, ``length``, ``axis_origin``. The arc passes through
    ``(end_r, ±length/2)`` and ``(mid_r, 0)`` in the (radial, axial)
    plane, centered at ``(mid_r - s * meridian_r, 0)``.
    """
    from scadwright.ast.placement import _axis_origin_for
    from scadwright.extrusions import rotate_extrude
    from scadwright.primitives import polygon

    axis_origin = _axis_origin_for(host_anchor)
    if axis_origin is None:
        return None
    meridian_r = host_anchor.meridian_r
    mid_r = host_anchor.mid_r
    s = host_anchor.meridian_s
    end_r = host_anchor.end_r
    host_axis = host_anchor.axis
    host_length = host_anchor.length
    if None in (meridian_r, mid_r, s, end_r, host_length):
        return None

    eps_r = eps if eps_overlap else 0.0
    # Sample the meridian arc, shifted radially outward by eps_r so the
    # resulting solid covers the peg-side eps slab.
    n_segments = 64
    h = host_length
    pts: list[tuple[float, float]] = []
    # Bottom rim point on the axis (closes the polygon for rotate_extrude).
    pts.append((0.0, -h / 2.0))
    # Walk the arc from (end_r, -h/2) through (mid_r, 0) to (end_r, +h/2).
    cx = mid_r - s * meridian_r
    theta = math.asin(min(1.0, max(-1.0, h / (2.0 * meridian_r))))
    for i in range(n_segments + 1):
        alpha = -theta + 2.0 * theta * i / n_segments
        x = cx + s * meridian_r * math.cos(alpha)
        z = meridian_r * math.sin(alpha)
        pts.append((max(x + eps_r, 0.0), z))
    # Top rim point on the axis.
    pts.append((0.0, h / 2.0))

    # Extend axially to cover the peg if it extends past the host. The
    # meridional inner surface is only valid within [-h/2, h/2]; outside
    # that range we extrapolate as a straight cylinder at end_r + eps_r
    # to keep the bore connected for an axially-overhanging peg.
    peg_t_min, peg_t_max = _project_peg_axial_range(peg, host_axis, axis_origin)
    if peg_t_min < -h / 2.0 - eps:
        pad = (-h / 2.0) - peg_t_min + eps
        # Insert an annular extension below: replace the first axis point.
        pts.insert(1, (end_r + eps_r, -h / 2.0 - pad))
        pts.insert(1, (0.0, -h / 2.0 - pad))
        pts.pop(0)  # remove duplicate axis-closure point
    if peg_t_max > h / 2.0 + eps:
        pad = peg_t_max - h / 2.0 + eps
        pts.append((end_r + eps_r, h / 2.0 + pad))
        pts.append((0.0, h / 2.0 + pad))
        # The pre-existing top axis point at index -1 was already (0, h/2);
        # drop it so the closure is at the new top.
        # Re-find and remove the original top closure if duplicated.
        # (Defensive: in the no-overhang case, last point is (0, h/2).)
    profile = polygon(points=pts)
    bore = rotate_extrude(profile)
    # The bore is built in the (radial, axial) plane with axis along +Z
    # and ``axis_origin`` at the canonical (0, 0, 0). Translate to the
    # host's actual axis_origin, then rotate +Z to host_axis.
    return _place_along_host_axis(bore, host_axis, axis_origin, 0.0, 0.0, loc)


def _build_inner_sphere_bore(host_anchor, peg, eps, eps_overlap, loc):
    """Sphere of revolution for a hollow-spherical inner anchor.

    Hand-declared via ``with_anchor(..., kind='spherical', inner=True)``;
    not produced by any built-in shape today, but the dispatch handles
    it for consistency.
    """
    from scadwright.ast.transforms import Translate
    from scadwright.primitives import sphere

    if host_anchor.radius is None or host_anchor.axis_origin is None:
        return None
    bore_r = host_anchor.radius + (eps if eps_overlap else 0.0)
    bore = sphere(r=bore_r)
    return Translate(
        v=host_anchor.axis_origin, child=bore, source_location=loc,
    )


def build_inner_bridge(peg, peg_at_anchor, host_on_anchor, shift, eps, *, eps_overlap):
    """Clip the placed peg to the host's bore (concave-inner case).

    Args:
        peg: the shape being attached (``self`` in attach).
        peg_at_anchor: peg's at-anchor in peg's local frame. Currently
            unused — kept for signature symmetry with ``build_curved_bridge``
            in case future validation is added.
        host_on_anchor: host's on-anchor in world frame (after ``angle=`` /
            ``at_z=`` adjustments). Must carry ``inner=True`` and
            sufficient surface_params for the kind.
        shift: translation that places peg's at-anchor on host's on-anchor.
        eps: overlap thickness for the peg-side eps slab inside the wall.
        eps_overlap: when True, enlarge the bore radius by ``eps`` so the
            placed peg has an ``eps``-deep slab of material inside the
            wall material (manifold-clean union with host). When False,
            bore matches host inner geometry exactly — peg's curved
            near-face coincides with the wall surface (preview will
            flicker; the user has opted out).

    Returns the intersection node (the peg clipped to the bore), or
    ``None`` if surface_params don't carry sufficient geometry to build
    a bore.
    """
    del peg_at_anchor  # signature symmetry; not used yet
    from scadwright.ast.transforms import Translate
    from scadwright.boolops import intersection as _intersection

    kind = host_on_anchor.kind
    if kind == "cylindrical":
        bore = _build_inner_cylinder_bore(host_on_anchor, peg, eps, eps_overlap, peg.source_location)
    elif kind == "conical":
        bore = _build_inner_cone_bore(host_on_anchor, peg, eps, eps_overlap, peg.source_location)
    elif kind == "meridional":
        bore = _build_inner_meridional_bore(host_on_anchor, peg, eps, eps_overlap, peg.source_location)
    elif kind == "spherical":
        bore = _build_inner_sphere_bore(host_on_anchor, peg, eps, eps_overlap, peg.source_location)
    else:
        return None
    if bore is None:
        return None

    placed_peg = Translate(v=shift, child=peg, source_location=peg.source_location)
    return _intersection(placed_peg, bore)
