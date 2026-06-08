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

    from scadwright.api.tolerances import PARALLEL_CROSS_TOL
    if cross_len > PARALLEL_CROSS_TOL:
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


def build_cross_section_slab(node, anchor, eps, *, context: str = "cross-section fuse"):
    """Return the eps slab at ``anchor``'s plane, without unioning it into
    ``node``.

    Aligns ``anchor.position`` to the origin and ``anchor.normal`` to +Z,
    takes ``projection(cut=True)`` to extract the 2D cross-section,
    ``linear_extrude``s by ``eps``, and applies the inverse alignment so the
    slab lies on the +normal side of the anchor. The caller decides what to
    do with it: ``cross_section_extend`` unions it back into ``node``; the
    N-ary fuse path collects slabs and unions once.

    Raises via ``validate_planar_anchor_for_cross_section`` if the anchor
    isn't on the shape's outermost face along its normal.
    """
    from scadwright.ast.transforms import MultMatrix

    validate_planar_anchor_for_cross_section(node, anchor, context=context)
    m = align_anchor_to_z_up(anchor)
    m_inv = m.invert()
    loc = node.source_location
    slab = (
        MultMatrix(matrix=m, child=node, source_location=loc)
        .projection(cut=True)
        .linear_extrude(height=eps)
    )
    return MultMatrix(matrix=m_inv, child=slab, source_location=loc)


def validate_planar_anchor_for_cross_section(node, anchor, *, context: str = "cross-section fuse"):
    """Raise ``ValidationError`` if ``anchor`` doesn't satisfy the
    necessary conditions for a non-degenerate cross-section on ``node``.

    Two checks, both based on the shape's axis-aligned bbox:

    1. The anchor must lie on the shape's outermost face along its
       normal direction. Computed as a dot-product comparison so the
       check works uniformly for axis-aligned and slanted normals.
       Translate / Rotate / Mirror wrappers are unwrapped first by
       inverse-transforming the anchor and recursing into the child —
       a peg rotated by ``orient=True`` to face a slanted host wall
       has a non-axis-aligned anchor in world frame, but its underlying
       primitive's AABB matches its actual silhouette and the check
       passes there.

    2. The shape must have non-zero extent in at least two of the three
       axes. A line- or point-shaped bbox can't yield a planar contact
       region.

    These are necessary but not sufficient — non-convex shapes can pass
    both checks while still having an empty cross-section at the anchor
    plane. The fuse will silently no-op in that case; the documented
    workarounds are restructuring, ``disable_eps_fuse()``, or hand-
    crafted overlap.

    ``context`` is interpolated into error messages — pass
    ``"bridge fuse"`` from the curved-host bridge dispatcher so the
    message blames the right path.
    """
    from dataclasses import replace
    from scadwright.ast.transforms import Mirror, Rotate, Translate
    from scadwright.bbox import bbox as _bbox
    from scadwright.errors import ValidationError
    from scadwright.matrix import to_matrix

    # Unwrap spatial transforms so the bbox-projection check happens in
    # the underlying primitive's local frame, where its AABB matches
    # its actual silhouette.
    if isinstance(node, Translate):
        local_anchor = replace(
            anchor,
            position=(
                anchor.position[0] - node.v[0],
                anchor.position[1] - node.v[1],
                anchor.position[2] - node.v[2],
            ),
        )
        return validate_planar_anchor_for_cross_section(
            node.child, local_anchor, context=context,
        )
    if isinstance(node, (Rotate, Mirror)):
        inv = to_matrix(node).invert()
        local_anchor = replace(
            anchor,
            position=inv.apply_point(anchor.position),
            normal=inv.apply_vector(anchor.normal),
        )
        return validate_planar_anchor_for_cross_section(
            node.child, local_anchor, context=context,
        )

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

    from scadwright.api.tolerances import ANCHOR_PLANE_TOL, BBOX_DEGEN_TOL
    if abs(p_proj - b_max) > ANCHOR_PLANE_TOL:
        raise ValidationError(
            f"{context}: anchor at {p} with normal {n} on "
            f"{type(node).__name__} doesn't lie on the shape's outermost "
            f"face along its normal direction. Projected anchor extent: "
            f"{p_proj:.4f}; expected ~{b_max:.4f} (max of bbox extents). "
            f"The anchor may be in the shape's interior, on the wrong "
            f"side, or otherwise misplaced. Workarounds: pass "
            f"fuse=False on this attach, wrap the block in "
            f"disable_eps_fuse(), or restructure so the anchor lies "
            f"on a clean planar face."
        )

    sizes = [bb.max[i] - bb.min[i] for i in range(3)]
    nonzero = sum(1 for s in sizes if s > BBOX_DEGEN_TOL)
    if nonzero < 2:
        raise ValidationError(
            f"{context}: shape {type(node).__name__} has zero "
            f"or near-zero extent in {3 - nonzero} of three axes "
            f"(sizes: {sizes!r}). No planar contact region exists for "
            f"the cross-section to span. Workarounds: pass fuse=False "
            f"on this attach, wrap the block in disable_eps_fuse(), or "
            f"give the shape non-zero extent in two axes."
        )
