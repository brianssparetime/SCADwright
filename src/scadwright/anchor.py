"""Anchor dataclass and face-name utilities for the attach system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from scadwright.errors import ValidationError

if TYPE_CHECKING:
    from scadwright.bbox import BBox


@dataclass(frozen=True, slots=True)
class Anchor:
    """A named attachment point: position in local space plus outward normal.

    ``kind`` describes the surface geometry the anchor lives on. ``"planar"``
    is the default and covers every bbox-derived face. Curved-surface kinds
    (``"cylindrical"``, ``"conical"``) carry the parameters needed to wrap
    decorations like text on ``surface_params`` — a sorted tuple of
    ``(name, value)`` pairs. The kwarg form accepts a dict for ergonomics
    and is normalized at construction.
    """

    position: tuple[float, float, float]
    normal: tuple[float, float, float]
    kind: str = "planar"
    surface_params: tuple[tuple[str, Any], ...] = ()

    def surface_param(self, name: str, default: Any = None) -> Any:
        """Return ``surface_params[name]`` or ``default`` if missing."""
        for k, v in self.surface_params:
            if k == name:
                return v
        return default


def _point_in_bbox(p, bb, tol: float = 1e-6) -> bool:
    """Whether ``p`` lies inside (or on, within ``tol``) the bbox ``bb``.

    Used by ``visit_Difference`` to decide whether a propagated
    custom anchor might have been invalidated by a cutter — a cutter
    whose bbox covers the anchor's position may have removed material
    at the anchor's face.
    """
    return all(bb.min[i] - tol <= p[i] <= bb.max[i] + tol for i in range(3))


def _normalize_surface_params(sp) -> tuple[tuple[str, Any], ...]:
    """Coerce a dict/tuple/None to a sorted tuple-of-pairs.

    Accepts a dict for caller ergonomics, a tuple-of-pairs for direct
    construction, or None/empty for the no-params case. Sorting keeps the
    Anchor hashable and stable for cache/equality use.
    """
    if sp is None or sp == ():
        return ()
    if isinstance(sp, dict):
        return tuple(sorted(sp.items()))
    return tuple(sorted(sp))


# Mapping from friendly face names to (axis_index, sign).
#   top/bottom  -> Z axis
#   front/back  -> Y axis  (front = -Y, back = +Y, matching scadwright convention)
#   lside/rside -> X axis  (lside = -X = left, rside = +X = right)
_FRIENDLY_TO_AXIS: dict[str, tuple[int, int]] = {
    "top": (2, 1),
    "bottom": (2, -1),
    "front": (1, -1),
    "back": (1, 1),
    "lside": (0, -1),
    "rside": (0, 1),
}

_AXIS_SIGN_TO_AXIS: dict[str, tuple[int, int]] = {
    "+x": (0, 1),
    "-x": (0, -1),
    "+y": (1, 1),
    "-y": (1, -1),
    "+z": (2, 1),
    "-z": (2, -1),
}

# All accepted face names.
FACE_NAMES: dict[str, tuple[int, int]] = {**_FRIENDLY_TO_AXIS, **_AXIS_SIGN_TO_AXIS}

# The six normals, indexed by (axis_index, sign).
_NORMALS: dict[tuple[int, int], tuple[float, float, float]] = {
    (0, 1): (1.0, 0.0, 0.0),
    (0, -1): (-1.0, 0.0, 0.0),
    (1, 1): (0.0, 1.0, 0.0),
    (1, -1): (0.0, -1.0, 0.0),
    (2, 1): (0.0, 0.0, 1.0),
    (2, -1): (0.0, 0.0, -1.0),
}


def resolve_face_name(name: str) -> tuple[int, int]:
    """Return ``(axis_index, sign)`` for a face name, or raise ``ValidationError``."""
    try:
        return FACE_NAMES[name]
    except KeyError:
        friendly = sorted(_FRIENDLY_TO_AXIS)
        axis_sign = sorted(_AXIS_SIGN_TO_AXIS)
        raise ValidationError(
            f"Unknown face name {name!r}. "
            f"Use one of {friendly} or {axis_sign}."
        )


# Friendly-string angles around a cylinder, measured CCW from +X (the
# canonical reference meridian). Used by ``add_text(meridian=...)`` and
# ``Node.attach(angle=...)`` for parametric angular position on cylindrical
# / conical / rim anchors.
_ANGLE_ALIASES: dict[str, float] = {
    "+x": 0.0,
    "rside": 0.0,
    "+y": 90.0,
    "back": 90.0,
    "-x": 180.0,
    "lside": 180.0,
    "-y": 270.0,
    "front": 270.0,
}


def resolve_angle_to_radians(
    value,
    *,
    context_name: str,
    param_name: str = "angle",
) -> float:
    """Convert a numeric angle (degrees CCW) or a face-name string alias
    to radians.

    Used by every API that takes a parametric angle around a cylindrical
    or rim surface — keeps the alias vocabulary identical across
    ``attach(angle=...)``, ``add_text(meridian=...)``, and any future
    callers.

    ``context_name`` ("attach", "add_text", etc.) and ``param_name``
    ("angle", "meridian", etc.) are interpolated into the error message
    so the user knows which call rejected the input and which keyword
    they used. ``param_name`` defaults to ``"angle"`` for newer callers;
    pass it explicitly to preserve historical names like ``meridian``.
    """
    import math as _math

    if isinstance(value, str):
        key = value.lower()
        if key not in _ANGLE_ALIASES:
            raise ValidationError(
                f"{context_name}: {param_name} must be one of "
                f"{sorted(_ANGLE_ALIASES)} or a numeric angle in degrees "
                f"CCW from +X; got {value!r}."
            )
        return _math.radians(_ANGLE_ALIASES[key])
    if isinstance(value, bool):
        raise ValidationError(
            f"{context_name}: {param_name} must be a string or numeric, got bool."
        )
    if isinstance(value, (int, float)):
        return _math.radians(float(value))
    raise ValidationError(
        f"{context_name}: {param_name} must be a string or numeric, got "
        f"{type(value).__name__}."
    )


def anchors_from_bbox(bb: "BBox") -> dict[str, Anchor]:
    """Derive the six standard face anchors from an axis-aligned bounding box.

    Returns a dict with 12 keys (6 friendly names + 6 axis-sign names).
    Friendly and axis-sign keys for the same face share the same Anchor object.
    """
    cx, cy, cz = bb.center

    anchors: dict[str, Anchor] = {}
    for name, (axis, sign) in FACE_NAMES.items():
        # Position: center of the face (bbox center, with the face-axis
        # coordinate replaced by the min or max of the bbox on that axis).
        pos = [cx, cy, cz]
        pos[axis] = bb.max[axis] if sign > 0 else bb.min[axis]
        anchor = Anchor(
            position=(pos[0], pos[1], pos[2]),
            normal=_NORMALS[(axis, sign)],
        )
        anchors[name] = anchor

    return anchors


def transform_anchors(
    anchors: dict[str, "Anchor"],
    matrix: "Matrix",
) -> dict[str, "Anchor"]:
    """Apply a transform matrix to every anchor's position and normal.

    Returns a new dict. Normals are re-normalized after transformation.
    Cylindrical / conical surface params (``axis``, ``radius``, ``r1``,
    ``r2``) are transformed alongside position and normal so curved
    anchors survive ``.scale()`` and ``.rotate()`` correctly. Non-uniform
    scaling perpendicular to the axis turns a cylinder into an ellipse —
    we don't model that; the radius scales by the magnitude of a unit
    perpendicular vector after transform.
    """
    import math as _math

    result: dict[str, Anchor] = {}
    for name, a in anchors.items():
        pos = matrix.apply_point(a.position)
        norm = matrix.apply_vector(a.normal)
        length = _math.sqrt(norm[0] ** 2 + norm[1] ** 2 + norm[2] ** 2)
        if length > 0:
            norm = (norm[0] / length, norm[1] / length, norm[2] / length)
        new_params = _transform_surface_params(a.surface_params, matrix)
        result[name] = Anchor(
            position=pos,
            normal=norm,
            kind=a.kind,
            surface_params=new_params,
        )
    return result


def _transform_surface_params(
    surface_params: tuple[tuple[str, Any], ...],
    matrix: "Matrix",
) -> tuple[tuple[str, Any], ...]:
    """Transform curved-surface parameters: rotate direction vectors, scale
    radii, translate axis_origin.

    Direction-vector params (``axis``, ``meridian_zero``) get the
    matrix's rotational part applied and are re-normalized. Radial
    scalars (``radius``, ``r1``, ``r2``, ``rim_radius``, ``mid_r``,
    ``end_r``, ``meridian_r``) scale by the matrix's effect on a unit
    vector perpendicular to the axis. ``length`` scales by the matrix's
    effect along the axis direction. ``axis_origin`` is a point on the
    axis line — gets the full affine transform (rotation + translation).
    Other params pass through unchanged.
    """
    import math as _math

    if not surface_params:
        return surface_params

    params = dict(surface_params)
    axis = params.get("axis")
    if axis is None:
        return surface_params  # nothing axis-relative to transform

    # Rotate the axis (it's a direction, not a point).
    new_axis_raw = matrix.apply_vector(axis)
    axis_len = _math.sqrt(sum(c * c for c in new_axis_raw))
    if axis_len < 1e-12:
        # Degenerate matrix collapsed the axis — leave params untouched.
        return surface_params
    new_axis = tuple(c / axis_len for c in new_axis_raw)
    params["axis"] = new_axis

    # ``meridian_zero`` (rim and meridional anchors) is a direction vector;
    # transforms exactly like ``axis``.
    mz = params.get("meridian_zero")
    if mz is not None:
        new_mz_raw = matrix.apply_vector(mz)
        mz_len = _math.sqrt(sum(c * c for c in new_mz_raw))
        if mz_len > 1e-12:
            params["meridian_zero"] = tuple(c / mz_len for c in new_mz_raw)

    # ``axis_origin`` (meridional anchors) is a point on the central axis
    # line; transforms with the full affine matrix.
    ao = params.get("axis_origin")
    if ao is not None:
        params["axis_origin"] = matrix.apply_point(ao)

    # Pick a unit vector perpendicular to the original axis to measure
    # radial scaling. The choice doesn't matter for uniform scales; for
    # non-uniform scales we approximate with this single perpendicular.
    ax, ay, az = axis
    if abs(az) < 0.99:
        ref = (0.0, 0.0, 1.0)
    else:
        ref = (1.0, 0.0, 0.0)
    perp = (
        ref[1] * az - ref[2] * ay,
        ref[2] * ax - ref[0] * az,
        ref[0] * ay - ref[1] * ax,
    )
    perp_len = _math.sqrt(sum(c * c for c in perp))
    if perp_len > 1e-12:
        perp_unit = tuple(c / perp_len for c in perp)
        new_perp = matrix.apply_vector(perp_unit)
        radial_scale = _math.sqrt(sum(c * c for c in new_perp))
    else:
        radial_scale = 1.0

    for key in ("radius", "r1", "r2", "rim_radius", "mid_r", "end_r", "meridian_r"):
        if key in params and isinstance(params[key], (int, float)):
            params[key] = params[key] * radial_scale

    # Axial scaling for `length`, if present.
    if "length" in params and isinstance(params["length"], (int, float)):
        new_axis_full = matrix.apply_vector(axis)
        axial_scale = _math.sqrt(sum(c * c for c in new_axis_full))
        params["length"] = params["length"] * axial_scale

    return tuple(sorted(params.items()))


def get_node_anchors(node) -> dict[str, "Anchor"]:
    """Return anchors for a node, propagating custom anchors through transforms.

    - Components: returns bbox-derived anchors merged with custom anchors.
    - Transform nodes wrapping a Component: recursively gets the child's
      anchors and applies the transform to positions and normals.
    - Decoration custom transforms (``@transform(decoration=True)``): pass
      through to the child so labels/decals don't strip the host's
      anchors. See ``docs/add_text.md``.
    - CSG nodes or primitives: returns only bbox-derived anchors (custom
      anchors are dropped by boolean operations).
    """
    return _AnchorVisitor().visit(node)


# =============================================================================
# AnchorVisitor — Visitor subclass walking the AST to compute named anchors
# =============================================================================


from scadwright.emit.visitor import Visitor as _Visitor  # noqa: E402


class _AnchorVisitor(_Visitor):
    """Compute a node's named anchors by walking the AST.

    Returns ``dict[str, Anchor]``. Stateless: spatial transforms apply
    on the way back up — each transform's ``visit_X`` recurses on the
    child, then transforms the returned anchor positions and normals.
    Components return their own ``get_anchors()`` dict (bbox-derived
    plus custom anchors merged). Decoration custom transforms pass
    through to the child so chained labels and post-decoration
    ``attach()`` calls keep working.
    """

    # --- Component: own anchor collection. ---

    def visit_component(self, n):
        return n.get_anchors()

    # --- Spatial transforms: recurse, then apply matrix to result. ---

    def _visit_spatial(self, n):
        from scadwright.matrix import to_matrix
        return transform_anchors(self.visit(n.child), to_matrix(n))

    def visit_Translate(self, n): return self._visit_spatial(n)
    def visit_Rotate(self, n): return self._visit_spatial(n)
    def visit_Scale(self, n): return self._visit_spatial(n)
    def visit_Mirror(self, n): return self._visit_spatial(n)
    def visit_MultMatrix(self, n): return self._visit_spatial(n)

    # --- Pass-through wrappers. ---

    def visit_Color(self, n): return self.visit(n.child)
    def visit_PreviewModifier(self, n): return self.visit(n.child)
    def visit_ForceRender(self, n): return self.visit(n.child)

    # --- WithAnchor: recurse, then add the named anchor on top. ---

    def visit_WithAnchor(self, n):
        anchors = dict(self.visit(n.child))
        anchors[n.anchor_name] = n.anchor
        return anchors

    # --- Difference: propagate first-child anchors, dropping any custom
    # anchor whose position falls inside a cutter's bbox.
    #
    # The first child's bbox is the difference's bbox (conservative);
    # its bbox-derived faces are also the difference's bbox-derived
    # faces, so they propagate as-is. Custom anchors on the first
    # child usually survive a difference — drilling a hole doesn't move
    # the bracket's mount face — but a cutter whose bbox covers an
    # anchor's position may have removed material at it. Drop those
    # defensively. The user gets a clear missing-anchor error at attach
    # time pointing at the lost anchor; if the cutter actually doesn't
    # affect the anchor's face, the user can re-declare a fresh anchor.
    #
    # Union and Intersection still drop all custom anchors (handled by
    # generic_visit) — the semantic ambiguity there is real and there's
    # no clear "first child's anchors carry through" rule.

    def visit_Difference(self, n):
        from scadwright.bbox import bbox as _bbox

        if not n.children:
            return self.generic_visit(n)

        first_anchors = dict(self.visit(n.children[0]))
        if len(n.children) == 1:
            return first_anchors

        first_bb = _bbox(n.children[0])
        bbox_defaults = anchors_from_bbox(first_bb)
        cutter_bboxes = [_bbox(c) for c in n.children[1:]]

        result: dict[str, Anchor] = {}
        for name, a in first_anchors.items():
            # Bbox-derived defaults of the first child = bbox-derived
            # defaults of the difference. Propagate without the cutter
            # check (they're at the bbox extreme and unaffected by the
            # boolean's conservative bbox).
            if bbox_defaults.get(name) == a:
                result[name] = a
                continue
            # Custom anchor: drop if any cutter's bbox covers it.
            if any(_point_in_bbox(a.position, cb) for cb in cutter_bboxes):
                continue
            result[name] = a
        return result

    def visit_Echo(self, n):
        if n.child is None:
            return self.generic_visit(n)
        return self.visit(n.child)

    # --- Custom: decoration transforms preserve host anchors. ---

    def visit_Custom(self, n):
        from scadwright._custom_transforms.base import get_transform

        t = get_transform(n.name)
        if t is not None and getattr(t, "decoration", False):
            return self.visit(n.child)
        return self.generic_visit(n)

    # --- Cylinder: bbox-derived faces plus rim/wall metadata. ---

    def visit_Cylinder(self, n):
        from scadwright.bbox import bbox as _bbox
        bb = _bbox(n)
        anchors = anchors_from_bbox(bb)
        rim_top, rim_bottom = _cylinder_rim_anchors(n)
        if rim_top is not None:
            anchors["top"] = rim_top
            anchors["+z"] = rim_top
        if rim_bottom is not None:
            anchors["bottom"] = rim_bottom
            anchors["-z"] = rim_bottom
        wall = _cylinder_outer_wall_anchor(n)
        if wall is not None:
            anchors["outer_wall"] = wall
        return anchors

    # --- Sphere: bbox-derived faces, but every face anchor is on the
    # spherical surface (a tangent point), not a planar face. Declare
    # kind="spherical" so curved-surface fuse dispatches via the bridge
    # mechanism instead of trying the planar cross-section path.
    # ``axis_origin`` (sphere center), ``axis`` (north-pole direction),
    # and ``meridian_zero`` (azimuth=0 reference) let attach() compute
    # arbitrary polar/azimuth points on the sphere.

    def visit_Sphere(self, n):
        from scadwright.bbox import bbox as _bbox
        bb = _bbox(n)
        radius = float(n.r)
        center = (bb.center[0], bb.center[1], bb.center[2])
        params = (
            ("axis", (0.0, 0.0, 1.0)),
            ("axis_origin", center),
            ("meridian_zero", (1.0, 0.0, 0.0)),
            ("radius", radius),
        )
        anchors: dict[str, Anchor] = {}
        for name, (axis, sign) in FACE_NAMES.items():
            pos = [center[0], center[1], center[2]]
            pos[axis] = bb.max[axis] if sign > 0 else bb.min[axis]
            anchors[name] = Anchor(
                position=(pos[0], pos[1], pos[2]),
                normal=_NORMALS[(axis, sign)],
                kind="spherical",
                surface_params=params,
            )
        # ``surface`` is the canonical entry-point anchor for polar /
        # angle placement on a sphere — defaults to the +Z tangent
        # point but the attach() helper recomputes position and normal
        # from polar/azimuth, so the actual default doesn't matter much.
        anchors["surface"] = Anchor(
            position=(center[0], center[1], center[2] + radius),
            normal=(0.0, 0.0, 1.0),
            kind="spherical",
            surface_params=params,
        )
        return anchors

    # --- Default: bbox-derived only (other primitives, CSG, etc). ---

    def generic_visit(self, n):
        from scadwright.bbox import bbox as _bbox
        return anchors_from_bbox(_bbox(n))


def _cylinder_rim_anchors(cyl):
    """Return (top_rim, bottom_rim) Anchors for a Cylinder primitive.

    Rim anchors are planar (the disk face is flat) but carry ``rim_radius``
    in ``surface_params`` so disk-rim arc text knows the circumradius.
    ``axis`` is the cylinder's central axis direction — the same value for
    top and bottom rim, and identical to the wall anchor's ``axis``. This
    keeps the angular convention (``angle=`` CCW from +X around the
    cylinder's axis) consistent across both rims and the wall.

    ``meridian_zero`` is the +X-meridian direction in the local frame —
    the reference direction for ``angle=0``. It transforms with the host
    just like ``axis`` and the wall anchor's normal, so when the host is
    rotated around its own axis the meridian-zero direction follows. For
    an axis-aligned cylinder, this is just ``(1, 0, 0)``.
    """
    h = cyl.h
    if cyl.center:
        z_min = -h / 2.0
        z_max = h / 2.0
    else:
        z_min = 0.0
        z_max = h

    rim_top = None
    if cyl.r2 > 0:
        rim_top = Anchor(
            position=(0.0, 0.0, z_max),
            normal=(0.0, 0.0, 1.0),
            kind="planar",
            surface_params=(
                ("axis", (0.0, 0.0, 1.0)),
                ("meridian_zero", (1.0, 0.0, 0.0)),
                ("rim_radius", float(cyl.r2)),
            ),
        )
    rim_bottom = None
    if cyl.r1 > 0:
        rim_bottom = Anchor(
            position=(0.0, 0.0, z_min),
            normal=(0.0, 0.0, -1.0),
            kind="planar",
            surface_params=(
                ("axis", (0.0, 0.0, 1.0)),
                ("meridian_zero", (1.0, 0.0, 0.0)),
                ("rim_radius", float(cyl.r1)),
            ),
        )
    return rim_top, rim_bottom


def _cylinder_outer_wall_anchor(cyl) -> "Anchor | None":
    """Build the outer_wall anchor for a Cylinder primitive in its local frame.

    Cylinders (r1 == r2) get a ``"cylindrical"`` anchor; cones (r1 != r2)
    get a ``"conical"`` anchor with both radii. The reference position is
    the +X meridian at the wall's axial midpoint, with outward normal +X
    (radial — not the surface normal of a slanted cone, but the canonical
    reference direction add_text uses to compute glyph positions).
    """
    h = cyl.h
    if cyl.center:
        z_mid = 0.0
    else:
        z_mid = h / 2.0

    if cyl.r1 == cyl.r2:
        r = cyl.r1
        if r <= 0:
            return None
        return Anchor(
            position=(r, 0.0, z_mid),
            normal=(1.0, 0.0, 0.0),
            kind="cylindrical",
            surface_params=(
                ("axis", (0.0, 0.0, 1.0)),
                ("length", float(h)),
                ("radius", float(r)),
            ),
        )

    # Conical: r1 at z_min, r2 at z_max. Mid-wall radius for the reference position.
    if cyl.r1 < 0 or cyl.r2 < 0:
        return None
    r_mid = (cyl.r1 + cyl.r2) / 2.0
    if r_mid <= 0:
        return None
    return Anchor(
        position=(r_mid, 0.0, z_mid),
        normal=(1.0, 0.0, 0.0),
        kind="conical",
        surface_params=(
            ("axis", (0.0, 0.0, 1.0)),
            ("length", float(h)),
            ("r1", float(cyl.r1)),
            ("r2", float(cyl.r2)),
        ),
    )


__all__ = [
    "Anchor",
    "FACE_NAMES",
    "_normalize_surface_params",
    "anchors_from_bbox",
    "get_node_anchors",
    "resolve_angle_to_radians",
    "resolve_face_name",
    "transform_anchors",
]
