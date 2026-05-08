"""Helpers for the cross-section path of fuse local-extension.

When a planar fuse target has no parametric extension lever (it's a
``rotate_extrude``, a ``Polyhedron``, a CSG result, or a custom
Component without a parametric hook), the framework builds a thin
slab from the shape's cross-section at the anchor plane and unions
it back into the shape. This module provides the alignment math and
the bbox-based degeneracy check that gate the path.
"""

from __future__ import annotations

import math


def align_anchor_to_z_up(anchor):
    """Return a Matrix that maps ``anchor.position`` to the origin and
    ``anchor.normal`` to ``+Z``.

    Used to put a shape into a frame where the anchor's plane is the
    z=0 plane and the +Z axis points outward, so ``projection(cut=True)``
    extracts the correct cross-section and ``linear_extrude`` produces
    a slab that, after the inverse alignment, lies on the +normal side
    of the anchor.

    The math is the inverse of "rotate +Z to a target normal": same
    rotation axis, negated angle.
    """
    from scadwright.matrix import Matrix

    p = anchor.position
    n = anchor.normal
    T = Matrix.translate(-p[0], -p[1], -p[2])

    # Rotation that maps n to +Z. Cross gives the rotation axis;
    # acos(n·z) gives the angle from +Z to n; negate to invert.
    z = (0.0, 0.0, 1.0)
    d = z[0] * n[0] + z[1] * n[1] + z[2] * n[2]
    cross = (
        z[1] * n[2] - z[2] * n[1],
        z[2] * n[0] - z[0] * n[2],
        z[0] * n[1] - z[1] * n[0],
    )
    cross_len = math.sqrt(cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2)

    if cross_len > 1e-10:
        angle_deg = -math.degrees(math.acos(max(-1.0, min(1.0, d))))
        R = Matrix.rotate_axis_angle(angle_deg, cross)
    elif d > 0.5:
        # n is approximately +Z; identity rotation.
        R = Matrix.identity()
    else:
        # n is approximately -Z; 180° flip around any perpendicular axis.
        R = Matrix.rotate_axis_angle(180.0, (1.0, 0.0, 0.0))

    # M(point) = R(T(point)): translate first, then rotate.
    return R.compose(T)


def validate_planar_anchor_for_cross_section(node, anchor):
    """Raise ``ValidationError`` if ``anchor`` doesn't satisfy the
    necessary conditions for a non-degenerate cross-section on ``node``.

    Two checks, both based on the shape's axis-aligned bbox:

    1. The anchor must lie on the shape's outermost face along its
       normal direction. Computed as a dot-product comparison so the
       check works uniformly for axis-aligned and slanted normals.

    2. The shape must have non-zero extent in at least two of the three
       axes. A line- or point-shaped bbox can't yield a planar contact
       region.

    These are necessary but not sufficient — non-convex shapes can pass
    both checks while still having an empty cross-section at the anchor
    plane. The fuse will silently no-op in that case; the documented
    workarounds are restructuring, ``disable_eps_fuse()``, or hand-
    crafted overlap.
    """
    from scadwright.bbox import bbox as _bbox
    from scadwright.errors import ValidationError

    bb = _bbox(node)
    n = anchor.normal
    p = anchor.position

    # Project anchor and all 8 bbox corners onto the normal direction.
    p_proj = p[0] * n[0] + p[1] * n[1] + p[2] * n[2]
    corners = [
        (bb.min[0] if i & 1 == 0 else bb.max[0],
         bb.min[1] if i & 2 == 0 else bb.max[1],
         bb.min[2] if i & 4 == 0 else bb.max[2])
        for i in range(8)
    ]
    b_max = max(c[0] * n[0] + c[1] * n[1] + c[2] * n[2] for c in corners)

    tol = 1e-3
    if abs(p_proj - b_max) > tol:
        raise ValidationError(
            f"cross-section fuse: anchor at {p} with normal {n} on "
            f"{type(node).__name__} doesn't lie on the shape's outermost "
            f"face along its normal direction. Projected anchor extent: "
            f"{p_proj:.4f}; expected ~{b_max:.4f} (max of bbox extents). "
            f"The anchor may be in the shape's interior, on the wrong "
            f"side, or otherwise misplaced."
        )

    sizes = [bb.max[i] - bb.min[i] for i in range(3)]
    nonzero = sum(1 for s in sizes if s > tol)
    if nonzero < 2:
        raise ValidationError(
            f"cross-section fuse: shape {type(node).__name__} has zero "
            f"or near-zero extent in {3 - nonzero} of three axes "
            f"(sizes: {sizes!r}). No planar contact region exists for "
            f"the cross-section to span."
        )
