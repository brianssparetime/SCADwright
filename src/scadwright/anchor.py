"""Anchor dataclass and face-name utilities for the attach system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from scadwright.errors import ValidationError

if TYPE_CHECKING:
    from scadwright.bbox import BBox


@dataclass(frozen=True, slots=True)
class Anchor:
    """A named attachment point: position in local space plus outward normal."""

    position: tuple[float, float, float]
    normal: tuple[float, float, float]


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
    """
    import math as _math

    result: dict[str, Anchor] = {}
    for name, a in anchors.items():
        pos = matrix.apply_point(a.position)
        norm = matrix.apply_vector(a.normal)
        # Re-normalize.
        length = _math.sqrt(norm[0] ** 2 + norm[1] ** 2 + norm[2] ** 2)
        if length > 0:
            norm = (norm[0] / length, norm[1] / length, norm[2] / length)
        result[name] = Anchor(position=pos, normal=norm)
    return result


def get_node_anchors(node) -> dict[str, "Anchor"]:
    """Return anchors for a node, propagating custom anchors through transforms.

    - Components: returns bbox-derived anchors merged with custom anchors.
    - Transform nodes wrapping a Component: recursively gets the child's
      anchors and applies the transform to positions and normals.
    - CSG nodes or primitives: returns only bbox-derived anchors (custom
      anchors are dropped by boolean operations).
    """
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

    # Everything else (primitives, CSG): bbox-derived only.
    return anchors_from_bbox(_bbox(node))


__all__ = [
    "Anchor",
    "FACE_NAMES",
    "anchors_from_bbox",
    "get_node_anchors",
    "resolve_face_name",
    "transform_anchors",
]
