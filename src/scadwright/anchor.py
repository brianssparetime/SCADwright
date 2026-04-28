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
    """Transform curved-surface parameters: rotate ``axis``, scale ``radius``.

    ``axis`` is a direction vector — apply the matrix's rotational part
    (no translation) and re-normalize. ``radius`` (and conical ``r1``,
    ``r2``) scale by the matrix's effect on a unit vector perpendicular
    to the axis. ``length`` (axial extent) scales by the matrix's effect
    along the axis direction. Other params pass through unchanged.
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

    for key in ("radius", "r1", "r2", "rim_radius"):
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
    from scadwright.ast.custom import Custom
    from scadwright.ast.transforms import (
        Color,
        Echo,
        ForceRender,
        Mirror,
        MultMatrix,
        PreviewModifier,
        Rotate,
        Scale,
        Translate,
    )
    from scadwright.bbox import bbox as _bbox
    from scadwright._custom_transforms.base import get_transform
    from scadwright.component.base import Component
    from scadwright.matrix import to_matrix

    if isinstance(node, Component):
        return node.get_anchors()

    # Spatial transforms: propagate child anchors through the transform.
    if isinstance(node, (Translate, Rotate, Scale, Mirror, MultMatrix)):
        child_anchors = get_node_anchors(node.child)
        m = to_matrix(node)
        return transform_anchors(child_anchors, m)

    # Non-spatial wrappers: pass through to child.
    if isinstance(node, (Color, PreviewModifier, ForceRender)):
        return get_node_anchors(node.child)

    if isinstance(node, Echo) and node.child is not None:
        return get_node_anchors(node.child)

    # Decoration transforms (e.g. add_text) preserve the host's anchors so
    # chained decorations and post-decoration attach() calls work naturally.
    if isinstance(node, Custom):
        t = get_transform(node.name)
        if t is not None and getattr(t, "decoration", False):
            return get_node_anchors(node.child)

    # Cylinder primitive: bbox-derived faces, plus rim metadata on
    # top/bottom (so disk-rim arc text knows the radius), plus an
    # `outer_wall` cylindrical/conical anchor for side-wall decoration.
    from scadwright.ast.primitives import Cylinder as _Cylinder
    if isinstance(node, _Cylinder):
        bb = _bbox(node)
        anchors = anchors_from_bbox(bb)
        rim_top, rim_bottom = _cylinder_rim_anchors(node)
        if rim_top is not None:
            anchors["top"] = rim_top
            anchors["+z"] = rim_top
        if rim_bottom is not None:
            anchors["bottom"] = rim_bottom
            anchors["-z"] = rim_bottom
        wall = _cylinder_outer_wall_anchor(node)
        if wall is not None:
            anchors["outer_wall"] = wall
        return anchors

    # Everything else (primitives, CSG, non-decoration custom): bbox-derived only.
    return anchors_from_bbox(_bbox(node))


def _cylinder_rim_anchors(cyl):
    """Return (top_rim, bottom_rim) Anchors for a Cylinder primitive.

    Rim anchors are planar (the disk face is flat) but carry ``rim_radius``
    in ``surface_params`` so disk-rim arc text knows the circumradius.
    The ``axis`` param matches the face normal so the radius scales
    correctly under transforms (handled by ``_transform_surface_params``).
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
                ("axis", (0.0, 0.0, -1.0)),
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
    "resolve_face_name",
    "transform_anchors",
]
