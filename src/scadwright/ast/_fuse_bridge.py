"""Bridge construction for curved-surface fuse.

When ``attach(fuse=True)``'s on-anchor is a curved-surface kind
(``cylindrical`` / ``conical`` / ``spherical``) with the host material on
the convex-outer side, the framework builds a bridge piece that fills the
air gap between the peg's planar near-face and the host's curved surface.

The bridge equals the peg's cross-section extruded into the host material
direction by the analytical inscription depth, *differenced* with the
host. Subtraction (not intersection) yields the air-gap fill; the peg-side
slice of the prism overlaps the placed peg by ``eps`` and provides the
manifold-clean Duty-A overlap automatically.

For concave-inner surfaces (``surface_params["inner"]=True``), the peg's
flat near-face naturally inscribes into host material as soon as the peg
is placed tangent — corners of the peg already sit inside the wall. No
bridge is needed; the dispatcher in ``Node.attach`` falls back to the
legacy shift instead of calling this helper.
"""

from __future__ import annotations

import math


def coaxial_normals(n_a, n_b, *, tol: float = 1e-3) -> bool:
    """Return True if two unit normals are anti-parallel within tolerance.

    ``attach(fuse=True)`` to a curved host requires coaxial normals: the
    peg's at-anchor normal must oppose the host's on-anchor normal so the
    bridge extrusion direction is well-defined. Oblique attachment is
    rejected with an explicit error in the dispatcher.
    """
    d = n_a[0] * n_b[0] + n_a[1] * n_b[1] + n_a[2] * n_b[2]
    return abs(d - (-1.0)) <= tol


def _peg_max_radial_extent(peg, peg_at_anchor) -> float:
    """Maximum distance from the at-anchor to any peg bbox corner,
    measured perpendicular to the anchor's normal — i.e., the peg's
    bbox half-extent in the tangent plane.
    """
    from scadwright.bbox import bbox as _bbox

    bb = _bbox(peg)
    n = peg_at_anchor.normal
    p = peg_at_anchor.position
    corners = [
        (bb.min[0] if i & 1 == 0 else bb.max[0],
         bb.min[1] if i & 2 == 0 else bb.max[1],
         bb.min[2] if i & 4 == 0 else bb.max[2])
        for i in range(8)
    ]
    max_r_sq = 0.0
    for c in corners:
        v = (c[0] - p[0], c[1] - p[1], c[2] - p[2])
        v_dot_n = v[0] * n[0] + v[1] * n[1] + v[2] * n[2]
        perp_sq = (
            (v[0] - v_dot_n * n[0]) ** 2
            + (v[1] - v_dot_n * n[1]) ** 2
            + (v[2] - v_dot_n * n[2]) ** 2
        )
        if perp_sq > max_r_sq:
            max_r_sq = perp_sq
    return math.sqrt(max_r_sq)


def _inscription_depth(host_on_anchor, peg_max_radial: float) -> float | None:
    """Analytical inscription depth from host's surface curvature.

    For cylindrical / spherical anchors: ``R - sqrt(R² - r²)`` where ``R``
    is host radius and ``r`` is peg's max radial extent in the tangent
    plane. For conical, use the larger of ``r1`` / ``r2`` as a conservative
    radius — over-estimating depth is safe (extra prism gets subtracted by
    host).

    Returns ``None`` if the host's surface_params don't carry a usable
    radius — the dispatcher should fall through to legacy shift.
    """
    radius = host_on_anchor.surface_param("radius")
    if radius is None and host_on_anchor.kind == "conical":
        r1 = host_on_anchor.surface_param("r1") or 0.0
        r2 = host_on_anchor.surface_param("r2") or 0.0
        radius = max(r1, r2)
    if not radius:
        return None
    if peg_max_radial >= radius:
        return float(radius)
    return float(radius - math.sqrt(radius * radius - peg_max_radial * peg_max_radial))


def build_curved_bridge(peg, peg_at_anchor, host, host_on_anchor, shift, eps):
    """Build the bridge for a convex-outer curved-surface fuse.

    Args:
        peg: the shape being attached (``self`` in attach).
        peg_at_anchor: peg's at-anchor in peg's local frame.
        host: the shape being attached to (``other`` in attach).
        host_on_anchor: host's on-anchor in world frame (post any
            ``angle=`` / ``at_z=`` adjustments).
        shift: the translation that places peg's at-anchor on host's
            on-anchor (output of ``_shift_for_anchors``, no fuse offset).
        eps: overlap thickness for Duty-A manifold cleanup.

    Returns a Node (the bridge geometry in world frame) suitable for
    ``union`` with the placed peg. Returns ``None`` if the host's
    surface_params don't carry a usable radius — caller should fall
    through to the legacy shift.

    The bridge is ``prism - host`` where ``prism`` is the peg's
    cross-section extruded along ``-on_anchor.normal`` from ``-eps`` (peg
    side, providing Duty-A overlap with the placed peg) to
    ``inscription_depth`` (host side, just past the inscription gap).

    Validates the peg's at-anchor against the peg's bbox before building
    the prism — a peg whose at-anchor isn't on the outermost face, or a
    peg with degenerate bbox extent, would produce an empty or wrong-
    sided projection and silently no-op the fuse. Catches what we can
    statically; non-convex pegs whose cross-section happens to be empty
    despite a sane bbox are still a documented limitation (CGAL evaluates
    that at render time).
    """
    from scadwright.ast._fuse_cross_section import (
        align_anchor_to_z_up,
        validate_planar_anchor_for_cross_section,
    )
    from scadwright.ast.transforms import MultMatrix, Translate
    from scadwright.boolops import difference as _difference

    validate_planar_anchor_for_cross_section(
        peg, peg_at_anchor, context="bridge fuse",
    )

    peg_max_radial = _peg_max_radial_extent(peg, peg_at_anchor)
    depth = _inscription_depth(host_on_anchor, peg_max_radial)
    if depth is None:
        return None
    # Tiny margin past analytical inscription guards against numerical
    # error around the host surface; the surplus is inside host material
    # and gets subtracted, so it doesn't change the visible bridge.
    depth_total = depth + 1e-3
    prism_height = depth_total + eps

    m = align_anchor_to_z_up(peg_at_anchor)
    m_inv = m.invert()
    loc = peg.source_location

    prism_aligned = (
        MultMatrix(matrix=m, child=peg, source_location=loc)
        .projection(cut=True)
        .linear_extrude(height=prism_height)
    )
    # Translate down by eps in aligned frame so the prism spans
    # z=-eps..z=depth_total: the negative slice is the peg-side overlap;
    # the positive slice is the inscription gap (the part of which is in
    # air, after subtraction with host, becomes the bridge).
    prism_aligned = Translate(
        v=(0.0, 0.0, -eps),
        child=prism_aligned,
        source_location=loc,
    )
    prism_local = MultMatrix(matrix=m_inv, child=prism_aligned, source_location=loc)
    prism_world = Translate(v=shift, child=prism_local, source_location=loc)

    return _difference(prism_world, host)
