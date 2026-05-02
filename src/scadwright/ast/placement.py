"""Helpers for ``Node.attach()`` and ``Node.through()``.

These functions live outside ``Node`` because they're not chained-
method conveniences — they're geometry calculations the methods
delegate to. Pulling them out keeps ``ast/base.py`` focused on the
``Node`` class itself.

- ``_detect_through_axis`` picks the cut axis when ``through()`` isn't
  given an explicit ``axis=``.
- ``_extend_through_faces`` wraps a cutter in the Scale+Translate that
  extends it across whichever of its faces are coincident with a
  parent's.
- ``_resolve_attach_anchor`` looks up a named anchor with a friendly
  error message on miss (standard face vs. custom-anchor distinction).
- ``_shift_for_anchors`` builds the translation vector that puts one
  anchor on top of another, optionally fused by a small offset along
  the contact-face normal.
- ``_orient_child_to_normal`` picks the right rotation (general,
  already-aligned, 180° flip) to make two anchor normals oppose.
"""

from __future__ import annotations


_AXIS_MAP = {"x": 0, "y": 1, "z": 2}


def _detect_through_axis(self_bb, parent_bb, explicit_axis: str | None, loc) -> int:
    """Pick the cut axis for ``through()``.

    Returns the axis index (0/1/2). If ``explicit_axis`` is given, parses
    it. Otherwise auto-detects: prefers axes where the cutter has a
    face coincident with the parent (picking the most-spanning one if
    several match), and falls back to the axis where the cutter's size
    most closely matches the parent's.
    """
    from scadwright.errors import ValidationError

    if explicit_axis is not None:
        ax = _AXIS_MAP.get(explicit_axis.lower())
        if ax is None:
            raise ValidationError(
                f"through: axis must be 'x', 'y', or 'z', got {explicit_axis!r}",
                source_location=loc,
            )
        return ax

    tol_detect = 1e-4
    candidates = [
        i for i in range(3)
        if abs(self_bb.min[i] - parent_bb.min[i]) < tol_detect
        or abs(self_bb.max[i] - parent_bb.max[i]) < tol_detect
    ]
    parent_size = parent_bb.size
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        # Multiple coincident axes — pick the one where the cutter spans
        # the most of the parent.
        best = candidates[0]
        best_ratio = 0.0
        for i in candidates:
            if parent_size[i] > 1e-10:
                r = self_bb.size[i] / parent_size[i]
                if r > best_ratio:
                    best_ratio = r
                    best = i
        return best
    # No coincident faces — fall back to the closest size match.
    self_size = self_bb.size
    ratios = [
        float("inf") if parent_size[i] < 1e-10
        else abs(self_size[i] / parent_size[i] - 1.0)
        for i in range(3)
    ]
    return ratios.index(min(ratios))


def _extend_through_faces(self, self_bb, parent_bb, ax: int, eps: float, loc):
    """Wrap ``self`` in the Scale+Translate that extends it across whichever
    of its ``ax``-faces are coincident with ``parent``'s. Returns ``self``
    unchanged when no face matches (the call site's no-op contract).
    Raises ValidationError if the cutter doesn't overlap the parent on
    the cut axis at all.
    """
    from scadwright.ast.transforms import Scale, Translate
    from scadwright.errors import ValidationError

    tol = 1e-4
    if (self_bb.max[ax] < parent_bb.min[ax] - tol
            or self_bb.min[ax] > parent_bb.max[ax] + tol):
        raise ValidationError(
            f"through: cutter does not overlap parent on the "
            f"{'xyz'[ax]}-axis. Call through() after positioning the cutter.",
            source_location=loc,
        )

    min_coincident = abs(self_bb.min[ax] - parent_bb.min[ax]) < tol
    max_coincident = abs(self_bb.max[ax] - parent_bb.max[ax]) < tol
    if not min_coincident and not max_coincident:
        return self

    new_min = (parent_bb.min[ax] - eps) if min_coincident else self_bb.min[ax]
    new_max = (parent_bb.max[ax] + eps) if max_coincident else self_bb.max[ax]

    orig_size = self_bb.max[ax] - self_bb.min[ax]
    if orig_size < 1e-10:
        raise ValidationError(
            f"through: cutter has zero extent on the {'xyz'[ax]}-axis. "
            f"through() needs a 3D cutter with non-zero extent on the cut "
            f"axis; a 2D profile must be linear_extrude()'d or "
            f"rotate_extrude()'d before passing to through().",
            source_location=loc,
        )

    scale_factor = (new_max - new_min) / orig_size
    # Scale-from-origin + translate yields: new_pos = old_pos * s + delta
    # where delta shifts the scaled center onto the target center.
    old_center = (self_bb.min[ax] + self_bb.max[ax]) / 2.0
    new_center = (new_min + new_max) / 2.0
    delta = new_center - old_center * scale_factor

    factor = [1.0, 1.0, 1.0]
    factor[ax] = scale_factor
    offset = [0.0, 0.0, 0.0]
    offset[ax] = delta
    return Translate(
        v=tuple(offset),
        child=Scale(factor=tuple(factor), child=self, source_location=loc),
        source_location=loc,
    )


def _resolve_attach_anchor(node, name: str, role: str, loc):
    """Look up a named anchor on ``node``; raise ValidationError with a
    diagnostic message (custom-anchor vs. standard-face hint) on miss.
    """
    from scadwright.anchor import FACE_NAMES, get_node_anchors, resolve_face_name
    from scadwright.errors import ValidationError

    anchors = get_node_anchors(node)
    if name not in anchors:
        if name in FACE_NAMES:
            resolve_face_name(name)  # pragma: no cover — sanity path
        type_name = type(node).__name__
        available = sorted(anchors)
        # Components publish more than the 12 bbox defaults; use that as the
        # heuristic for whether a "custom anchor missing" message applies.
        if len(available) > 12:
            raise ValidationError(
                f"attach: no anchor {name!r} on {role} ({type_name}). "
                f"Available: {available}",
                source_location=loc,
            )
        raise ValidationError(
            f"attach: custom anchor {name!r} on {role} ({type_name}) — "
            f"custom anchors are only available on Components. Primitives "
            f"support the standard face names: top, bottom, front, back, "
            f"lside, rside (or +z, -z, -y, +y, -x, +x).",
            source_location=loc,
        )
    return anchors[name]


def _shift_for_anchors(self_anchor, other_anchor, fuse: bool, eps: float):
    """Translation vector that puts ``self_anchor`` on ``other_anchor``.

    When ``fuse`` is set, offset by ``eps`` along the other-anchor normal
    (into the contact face) to eliminate coincident-surface seams in
    unions.
    """
    shift = [
        other_anchor.position[i] - self_anchor.position[i] for i in range(3)
    ]
    if fuse:
        fn = other_anchor.normal
        for i in range(3):
            shift[i] -= fn[i] * eps
    return (shift[0], shift[1], shift[2])


def _orient_child_to_normal(child, self_normal, target_normal, loc):
    """Return ``child`` wrapped in the Rotate that takes ``self_normal`` to
    ``target_normal``. Picks the right branch (general, already-aligned,
    or 180° flip) based on the dot/cross of the two unit normals.
    """
    import math as _math

    from scadwright.ast.transforms import Rotate

    def _dot(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def _cross(a, b):
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    def _length(v):
        return _math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])

    d = _dot(self_normal, target_normal)
    axis = _cross(self_normal, target_normal)
    if _length(axis) > 1e-10:
        # General case: rotate around the cross-product axis.
        angle_deg = _math.degrees(_math.acos(max(-1.0, min(1.0, d))))
        return Rotate(a=angle_deg, v=axis, child=child, source_location=loc)
    if d < -0.5:
        # Normals already opposite (touching-aligned) — no rotation.
        return child
    # Normals coincide (d ~ +1); 180° flip around any perpendicular axis.
    perp = _cross(self_normal, (1, 0, 0) if abs(self_normal[0]) < 0.9 else (0, 1, 0))
    return Rotate(a=180.0, v=perp, child=child, source_location=loc)
