"""Helpers for ``Node.through()`` on rotated cutters.

The world-axis path in ``placement.py`` (``_detect_through_axis`` /
``_extend_through_faces``) handles the case where the cutter's bbox
faces are world-axis-aligned. A rotated cutter's world AABB is inflated
and its faces don't sit on the parent's, so that path is a silent no-op.

This module adds the cutter-local-frame path, activated by the user
passing ``axis="local"`` (or ``"local_x"`` / ``"local_y"`` /
``"local_z"``) to ``through()``. The math:

1. Walk the cutter's outer transforms top-down, accumulating a 4×4
   matrix M from cutter-local to world frame. The walk stops at any
   non-extractable node (primitive, Component, CSG node, custom
   transform). That stopping node is the "leaf."
2. Verify the rotation submatrix of M is orthogonal with det ≈ +1.
   Anisotropic Scale (det ≠ 1), Mirror (det = -1), or shear/MultMatrix
   with non-orthogonal rotation submatrix raise.
3. Compute the parent's world AABB, transform its 8 corners into
   cutter-local frame via M^-1, project onto the chosen local axis to
   get parent's local-frame extent on that axis.
4. Compute the leaf's local-frame bbox (via ``bbox(leaf)``); its
   extent on the chosen local axis is the cutter's local cut range.
5. Compare the two extents within tolerance. For each coincident face,
   compute a Translate+Scale that extends the cutter on that face in
   local frame.
6. Insert the Translate+Scale at the leaf level (between the leaf and
   its outer transforms) using ``dataclasses.replace``-based AST
   surgery. The Translate+Scale apply in cutter-local frame; the outer
   rotates carry the extension into world space correctly. Output
   SCAD keeps the original ``rotate(...)`` calls plus a leaf-level
   ``translate(...) scale(...)`` rather than collapsing into a single
   opaque ``multmatrix``.

Snapshot preservation: when the leaf is a Component, wrapping it in
Translate+Scale would normally trigger ``Node.__post_init__`` to
re-capture the Component's resolution snapshot from whatever ambient
context is active at ``through()`` call time — corrupting the
Position-Y snapshot that determines the Component's resolution at
build. ``_wrap_leaf_with_eps`` saves and restores the snapshot around
the wrap.
"""

from __future__ import annotations

from dataclasses import replace as _dc_replace

from scadwright.errors import ValidationError
from scadwright.matrix import Matrix, to_matrix


_AXIS_MAP_LOCAL = {
    "local": 2,
    "local_x": 0,
    "local_y": 1,
    "local_z": 2,
}


def is_local_axis(axis: str | None) -> bool:
    """Return True if the axis string opts into the local-frame path."""
    return isinstance(axis, str) and axis.startswith("local")


def parse_local_axis(axis: str, loc) -> int:
    """Resolve ``axis="local" | "local_x" | "local_y" | "local_z"`` to
    an axis index 0/1/2. ``"local"`` is a synonym for ``"local_z"``.
    """
    try:
        return _AXIS_MAP_LOCAL[axis]
    except KeyError:
        raise ValidationError(
            f"through: axis must be one of 'local', 'local_x', 'local_y', "
            f"'local_z' for the local-frame path, got {axis!r}",
            source_location=loc,
        ) from None


def extract_cumulative_transform(node):
    """Walk ``node`` top-down through extractable transforms, accumulating
    a local-to-world ``Matrix``.

    Returns ``(matrix, leaf)`` where ``leaf`` is the first non-extractable
    node encountered (primitive, Component, CSG node, custom transform,
    decoration wrapper). Translation, Rotation, MultMatrix, Scale, and
    Mirror are extracted; Color contributes identity.

    Scale and Mirror are extracted (rather than treated as leaves) so
    the pure-rotation check downstream catches their non-orthogonality
    or determinant-of-(-1) and raises a clear error. Stopping at them
    would leak through as a silent identity-rotation case.
    """
    from scadwright.ast.transforms import (
        Color,
        Mirror,
        MultMatrix,
        Rotate,
        Scale,
        Translate,
    )

    matrix = Matrix.identity()
    cur = node
    while isinstance(cur, (Translate, Rotate, MultMatrix, Color, Scale, Mirror)):
        matrix = matrix @ to_matrix(cur)
        cur = cur.child
    return matrix, cur


def _matches_extractable_transform(node) -> bool:
    """Mirror of the type list in ``extract_cumulative_transform``.

    Used by ``insert_at_leaf`` to know which nodes to recurse through
    when rebuilding the tree.
    """
    from scadwright.ast.transforms import (
        Color,
        Mirror,
        MultMatrix,
        Rotate,
        Scale,
        Translate,
    )
    return isinstance(node, (Translate, Rotate, MultMatrix, Color, Scale, Mirror))


def assert_pure_rotation(matrix: Matrix, loc) -> None:
    """Verify the 3×3 rotational submatrix of ``matrix`` is orthogonal
    with determinant ≈ +1. Raises ``ValidationError`` with a diagnostic
    distinguishing scale / mirror / shear if not.
    """
    e = matrix.elements
    # Extract the 3×3 rotation submatrix.
    r = (
        (e[0][0], e[0][1], e[0][2]),
        (e[1][0], e[1][1], e[1][2]),
        (e[2][0], e[2][1], e[2][2]),
    )

    # Determinant of the 3×3 submatrix.
    det = (
        r[0][0] * (r[1][1] * r[2][2] - r[1][2] * r[2][1])
        - r[0][1] * (r[1][0] * r[2][2] - r[1][2] * r[2][0])
        + r[0][2] * (r[1][0] * r[2][1] - r[1][1] * r[2][0])
    )

    tol = 1e-9
    if abs(det + 1.0) < tol:
        raise ValidationError(
            "through: cutter's cumulative transform contains a Mirror or "
            "other orientation-reversing operation (det = -1). Position "
            "the geometry directly rather than mirroring it before "
            "through().",
            source_location=loc,
        )
    if abs(det - 1.0) > tol:
        raise ValidationError(
            f"through: cutter's cumulative transform is not a pure rotation "
            f"(determinant of rotational submatrix = {det:.6f}, expected ≈ 1). "
            f"Anisotropic Scale or shear is not supported in the local-axis "
            f"path; apply scale to the underlying primitive's parameters "
            f"instead.",
            source_location=loc,
        )

    # Orthogonality: R @ R.T ≈ I.
    for i in range(3):
        for j in range(3):
            dot = sum(r[i][k] * r[j][k] for k in range(3))
            expected = 1.0 if i == j else 0.0
            if abs(dot - expected) > tol:
                raise ValidationError(
                    f"through: cutter's cumulative transform is not "
                    f"orthogonal (R @ R.T entry [{i}][{j}] = {dot:.6f}, "
                    f"expected {expected}). The local-axis path requires "
                    f"a pure rotation; check for non-uniform Scale or "
                    f"shearing MultMatrix in the cutter's transform stack.",
                    source_location=loc,
                )


def _on_parent_face(world_point, parent_bb, tol: float) -> bool:
    """True if ``world_point`` lies on one of the parent's six AABB
    face planes (within ``tol``) AND its in-plane coordinates fall
    within the parent's range on those axes.

    Why both checks: just being on a plane isn't enough — the point
    must be on the plane *within the parent's face boundary*. A cutter
    end-face center that happens to lie on the extended z=0 plane
    but at xy=(1000, 1000) is not on the parent's bottom face.
    """
    for ax in range(3):
        for pval in (parent_bb.min[ax], parent_bb.max[ax]):
            if abs(world_point[ax] - pval) < tol:
                other_axes = [i for i in range(3) if i != ax]
                in_range = all(
                    parent_bb.min[i] - tol <= world_point[i] <= parent_bb.max[i] + tol
                    for i in other_axes
                )
                if in_range:
                    return True
    return False


def detect_face_coincidence(
    leaf_bb,
    matrix: Matrix,
    parent_bb,
    axis_idx: int,
    tol: float = 5e-4,
) -> tuple[bool, bool]:
    """Return ``(min_coincident, max_coincident)`` — whether the cutter's
    lower and upper end faces along ``axis_idx`` lie on a parent face.

    Each end face is identified by the cutter's local origin shifted to
    the bbox extent on the cut axis: ``(0, 0, leaf_bb.min[axis_idx])``
    for the min face, ``(0, 0, leaf_bb.max[axis_idx])`` for the max
    face. That local point is transformed to world coordinates via
    ``matrix`` and tested against the parent's six AABB face planes.

    Why local origin and not bbox center: the user positioned the
    cutter via ``translate(...)``, and that translation maps the cutter's
    local origin to the user's intended world location. For a cylinder
    cutter, the local origin lies on the axial centerline; for an
    asymmetric compound (e.g. a Union with off-center children), the
    bbox center can be far from where the user meant the cutter to be.
    The local origin is the most stable reference.

    Why this rather than projecting the parent's AABB corners onto
    the cut axis: a small cutter passing through a big plate has the
    plate's distant corners projecting to far cut-axis values, which
    swamps the actual surface alignment. Point-on-plane asks the right
    question.
    """
    min_face_local = [0.0, 0.0, 0.0]
    min_face_local[axis_idx] = leaf_bb.min[axis_idx]
    max_face_local = [0.0, 0.0, 0.0]
    max_face_local[axis_idx] = leaf_bb.max[axis_idx]

    min_face_world = matrix.apply_point(tuple(min_face_local))
    max_face_world = matrix.apply_point(tuple(max_face_local))

    return (
        _on_parent_face(min_face_world, parent_bb, tol),
        _on_parent_face(max_face_world, parent_bb, tol),
    )


def compute_local_extension(
    leaf_min: float,
    leaf_max: float,
    min_coincident: bool,
    max_coincident: bool,
    eps: float,
) -> tuple[float, float] | None:
    """Compute the local-frame Scale factor and Translate offset that
    extend the cutter's coincident face(s) by ``eps`` along the cut axis.

    Returns ``(scale_factor, translate_offset)`` or ``None`` when
    neither face is coincident or the leaf has zero extent on the axis.
    """
    if not min_coincident and not max_coincident:
        return None

    orig_size = leaf_max - leaf_min
    if orig_size < 1e-10:
        return None

    new_min = (leaf_min - eps) if min_coincident else leaf_min
    new_max = (leaf_max + eps) if max_coincident else leaf_max

    scale_factor = (new_max - new_min) / orig_size
    old_center = (leaf_min + leaf_max) / 2.0
    new_center = (new_min + new_max) / 2.0
    translate_offset = new_center - old_center * scale_factor
    return scale_factor, translate_offset


def wrap_leaf_with_eps(leaf, scale_factor: float, translate_offset: float, axis_idx: int, loc):
    """Wrap ``leaf`` in a local-frame ``Translate(Scale(leaf))`` that
    extends one or both of its coincident faces by ``eps`` along
    ``axis_idx``.

    Position-Y interaction (R1 in the design doc): when ``leaf`` is a
    Component, the new Translate's ``__post_init__`` would normally
    recapture the Component's resolution snapshot from whatever ambient
    context is active here — corrupting the snapshot from the
    Component's actual AST-insertion site. Save and restore the
    snapshot around the wrap.
    """
    from scadwright.ast.transforms import Scale, Translate
    from scadwright.component.base import Component

    factor = [1.0, 1.0, 1.0]
    factor[axis_idx] = scale_factor
    offset = [0.0, 0.0, 0.0]
    offset[axis_idx] = translate_offset

    saved_snapshot = leaf._ctx_resolution if isinstance(leaf, Component) else None

    wrapped = Translate(
        v=tuple(offset),
        child=Scale(
            factor=tuple(factor),
            child=leaf,
            source_location=loc,
        ),
        source_location=loc,
    )

    if isinstance(leaf, Component):
        leaf._ctx_resolution = saved_snapshot

    return wrapped


def insert_at_leaf(root, target_leaf, new_leaf):
    """Walk ``root`` through extractable transforms; when the recursion
    reaches ``target_leaf`` (by identity), return ``new_leaf`` instead.
    Otherwise rebuild parent transform nodes with the modified child via
    ``dataclasses.replace``.
    """
    if root is target_leaf:
        return new_leaf
    if _matches_extractable_transform(root):
        new_child = insert_at_leaf(root.child, target_leaf, new_leaf)
        return _dc_replace(root, child=new_child)
    # Shouldn't happen if extract_cumulative_transform identified the leaf
    # correctly; surface a clear error.
    raise ValidationError(
        f"through: AST surgery encountered unexpected node "
        f"{type(root).__name__} while walking to leaf "
        f"{type(target_leaf).__name__}"
    )


def extend_through_faces_local(
    self,
    parent,
    axis: str,
    eps: float,
    loc,
):
    """Local-frame variant of ``_extend_through_faces``. See module
    docstring for the algorithm.

    Returns the cutter wrapped with the extension applied at the leaf
    level. Raises if the cumulative transform isn't a pure rotation,
    or if no coincident face is found (the user explicitly asked for
    the local-frame path; silent no-op would mask their bug).
    """
    from scadwright.bbox import bbox as _bbox

    axis_idx = parse_local_axis(axis, loc)
    matrix, leaf = extract_cumulative_transform(self)
    assert_pure_rotation(matrix, loc)

    parent_bb = _bbox(parent)
    leaf_bb = _bbox(leaf)

    min_coincident, max_coincident = detect_face_coincidence(
        leaf_bb, matrix, parent_bb, axis_idx,
    )
    extension = compute_local_extension(
        leaf_bb.min[axis_idx],
        leaf_bb.max[axis_idx],
        min_coincident,
        max_coincident,
        eps,
    )
    if extension is None:
        raise ValidationError(
            f"through(axis={axis!r}): no cutter end-face is coincident "
            f"with a parent face plane on cutter-local axis {axis_idx} "
            f"(tol=5e-4). Cutter's local-frame bbox on axis: "
            f"({leaf_bb.min[axis_idx]:.4f}, {leaf_bb.max[axis_idx]:.4f}). "
            f"Reposition the cutter so one of its end-face centers sits "
            f"on a parent surface, or omit the explicit axis to fall "
            f"back to no-op behavior.",
            source_location=loc,
        )

    scale_factor, translate_offset = extension
    new_leaf = wrap_leaf_with_eps(leaf, scale_factor, translate_offset, axis_idx, loc)
    return insert_at_leaf(self, leaf, new_leaf)


def has_rotation(node) -> bool:
    """Does the cutter's cumulative transform contain a *non-axis-permuting*
    rotation?

    Used by ``Node.through()``'s auto-detect dispatch when the world-axis
    path fails to find coincidence. A non-axis-permuting rotation (30°,
    45°, etc.) means the cutter's bbox in world frame is inflated and
    won't align with the parent's faces — that's the case where we want
    to raise pointing at the local-axis form. An axis-permuting rotation
    (90° around an axis: FilletMask's ``Rotate(0, 90, 0)``, etc.) keeps
    the world bbox axis-aligned and the world-axis path handles it
    correctly; we don't want to false-alarm on those.

    The check: extract the cumulative rotation matrix; ask whether each
    row is a signed unit basis vector (entries are 0 or ±1 within tol).
    Equivalent: every entry of the rotation submatrix is approximately
    0 or ±1.
    """
    matrix, _leaf = extract_cumulative_transform(node)
    e = matrix.elements
    tol = 1e-6
    for i in range(3):
        for j in range(3):
            v = e[i][j]
            if not (abs(v) < tol or abs(v - 1.0) < tol or abs(v + 1.0) < tol):
                return True
    return False
