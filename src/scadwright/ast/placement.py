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


def _axis_origin_for(anchor):
    """Return a point on the cylinder's central axis line for ``anchor``.

    Used by ``_apply_attach_angle`` and ``_apply_attach_at_z`` to rotate
    or translate around the cylinder's actual axis line — which may not
    pass through the world origin if the host has been translated.

    For wall anchors, the axis line passes through ``anchor.position``
    minus the (signed) radius times the +X-meridian outward direction.
    For rim anchors (planar with rim_radius), ``anchor.position`` is
    already at the cap center and lies on the axis. Returns ``None`` if
    the anchor doesn't carry the geometry needed (no surface params).
    """
    if anchor.kind == "cylindrical":
        radius = anchor.surface_param("radius")
        if radius is None:
            return None
        inner = bool(anchor.surface_param("inner", default=False))
        s_outward = -1.0 if inner else 1.0
        return (
            anchor.position[0] - radius * s_outward * anchor.normal[0],
            anchor.position[1] - radius * s_outward * anchor.normal[1],
            anchor.position[2] - radius * s_outward * anchor.normal[2],
        )
    if anchor.kind == "conical":
        r1 = anchor.surface_param("r1")
        r2 = anchor.surface_param("r2")
        if r1 is None or r2 is None:
            return None
        r_mid = (r1 + r2) / 2.0
        inner = bool(anchor.surface_param("inner", default=False))
        s_outward = -1.0 if inner else 1.0
        return (
            anchor.position[0] - r_mid * s_outward * anchor.normal[0],
            anchor.position[1] - r_mid * s_outward * anchor.normal[1],
            anchor.position[2] - r_mid * s_outward * anchor.normal[2],
        )
    if anchor.kind == "planar" and anchor.surface_param("rim_radius") is not None:
        return anchor.position
    return None


def _rotate_about_line(point, rotation, origin):
    """Apply ``rotation`` (a rotation Matrix) to ``point``, treating
    ``origin`` as the center of rotation rather than the world origin.

    Equivalent to: translate by ``-origin``, rotate, translate by
    ``+origin``. Used for rotating around the cylinder's actual axis
    line when the host has been translated.
    """
    rel = (point[0] - origin[0], point[1] - origin[1], point[2] - origin[2])
    rotated = rotation.apply_vector(rel)
    return (
        origin[0] + rotated[0],
        origin[1] + rotated[1],
        origin[2] + rotated[2],
    )


def _cone_slanted_normal(r1: float, r2: float, length: float, *, inner: bool = False):
    """Surface normal of a cone wall at the +X meridian, mid-wall, pointing
    away from the wall material.

    For a cylinder (``r1 == r2``), returns ``(±1, 0, 0)`` (positive for
    outer walls, negative for inner). For a cone, returns a unit vector
    perpendicular to the slanted wall:

    - Outer wall, widening upward (``r2 > r1``): normal tilts down (-z).
    - Outer wall, narrowing upward (``r2 < r1``): normal tilts up (+z).
    - Inner wall: the negation of the outer-wall normal at the same
      slope (the wall faces the bore, so "away from material" is the
      opposite direction).

    Math: the wall in the (radial, axial) plane runs from ``(r1, z_min)``
    to ``(r2, z_max)``. The outward normal in that plane (rotated 90°
    from the slope) is ``(length, -(r2 - r1))``, normalized; flip sign
    for inner walls.
    """
    import math as _math

    slope_x = r2 - r1
    slope_z = length
    L = _math.hypot(slope_x, slope_z)
    sign = -1.0 if inner else 1.0
    if L < 1e-12:
        return (sign * 1.0, 0.0, 0.0)
    return (sign * slope_z / L, 0.0, sign * (-slope_x / L))


def _apply_attach_angle(anchor, angle, radius, loc):
    """Return a new Anchor with position (and possibly normal) rotated
    around the surface axis to angular position ``angle``.

    Rotation is around the cylinder's actual axis line (through the
    point returned by ``_axis_origin_for``), not the axis direction
    through the world origin. This matters when the host has been
    translated: the axis line moves with it, and the rotation needs to
    follow.

    Behavior dispatches on ``anchor.kind``:

    - **cylindrical** (``outer_wall`` of a cylinder): rotate position
      and normal around the axis line by ``angle``. ``radius=`` is
      rejected (the anchor sits on the wall surface; different radii
      would mean a different surface).

    - **conical** (``outer_wall`` of a cone): same rotation, but the
      "normal" used for the rotated anchor is the cone's *slanted*
      surface normal (not the radial reference normal that
      ``add_text`` consumes). This ensures ``attach()`` aligns parts
      perpendicular to the slanted wall, which is what the user
      expects for surface-mounted attachments.

    - **planar with rim_radius** (``top``/``bottom`` of a cylinder/cone):
      position becomes a point on the cap at radial distance ``radius``
      (defaulting to ``rim_radius``) at angular position ``angle``,
      rotated around the axis. Normal stays as-is (axial — perpendicular
      to the cap face). ``radius=0`` is the legitimate "center of cap"
      case.

    - **Anything else**: raise — the anchor doesn't expose surface
      geometry that an angular position can refer to.
    """
    from scadwright.anchor import Anchor, resolve_angle_to_radians
    from scadwright.errors import ValidationError
    from scadwright.matrix import Matrix

    angle_rad = resolve_angle_to_radians(angle, context_name="attach")
    angle_deg = angle_rad * (180.0 / _PI)

    axis = anchor.surface_param("axis")
    if axis is None:
        raise ValidationError(
            f"attach: angle= is not supported for this anchor (kind="
            f"{anchor.kind!r}). Anchors that support angular placement: "
            f"cylindrical (cylinder wall), conical (cone wall), and planar "
            f"caps with rim_radius (cylinder/cone top/bottom).",
            source_location=loc,
        )

    rotation = Matrix.rotate_axis_angle(angle_deg, axis)

    if anchor.kind == "cylindrical":
        if radius is not None:
            raise ValidationError(
                "attach: radius= is not valid on a cylindrical anchor "
                "(the wall sits at a fixed radius). Use radius= only on "
                "cap anchors with rim_radius.",
                source_location=loc,
            )
        origin = _axis_origin_for(anchor)
        new_position = _rotate_about_line(anchor.position, rotation, origin)
        new_normal = rotation.apply_vector(anchor.normal)
        return Anchor(
            position=new_position,
            normal=new_normal,
            kind=anchor.kind,
            surface_params=anchor.surface_params,
        )

    if anchor.kind == "conical":
        if radius is not None:
            raise ValidationError(
                "attach: radius= is not valid on a conical anchor "
                "(the wall radius is fixed by the cone geometry). Use "
                "radius= only on cap anchors with rim_radius.",
                source_location=loc,
            )
        # Slanted surface normal at the +X meridian, then rotate.
        r1 = anchor.surface_param("r1")
        r2 = anchor.surface_param("r2")
        length = anchor.surface_param("length")
        if r1 is None or r2 is None or length is None:
            raise ValidationError(
                "attach: conical anchor missing r1/r2/length surface_params; "
                "cannot compute the slanted normal.",
                source_location=loc,
            )
        inner = bool(anchor.surface_param("inner", default=False))
        slanted_ref = _cone_slanted_normal(r1, r2, length, inner=inner)
        origin = _axis_origin_for(anchor)
        new_position = _rotate_about_line(anchor.position, rotation, origin)
        new_normal = rotation.apply_vector(slanted_ref)
        return Anchor(
            position=new_position,
            normal=new_normal,
            kind=anchor.kind,
            surface_params=anchor.surface_params,
        )

    # Planar with rim_radius — cap of a cylinder/cone. The rim's
    # ``axis`` is the cylinder's central axis (same direction as the
    # wall's), and ``meridian_zero`` is the +X-meridian direction in
    # the rim plane in the host's local frame. Both transform with the
    # host, so a host rotated around its own axis still gets the right
    # +X-meridian reference direction.
    rim_radius = anchor.surface_param("rim_radius")
    if anchor.kind == "planar" and rim_radius is not None:
        r = rim_radius if radius is None else radius
        if r < 0:
            raise ValidationError(
                f"attach: radius= must be non-negative, got {radius}",
                source_location=loc,
            )
        meridian_zero = anchor.surface_param(
            "meridian_zero", default=(1.0, 0.0, 0.0),
        )
        offset_local = (
            r * meridian_zero[0],
            r * meridian_zero[1],
            r * meridian_zero[2],
        )
        offset_rotated = rotation.apply_vector(offset_local)
        new_position = (
            anchor.position[0] + offset_rotated[0],
            anchor.position[1] + offset_rotated[1],
            anchor.position[2] + offset_rotated[2],
        )
        return Anchor(
            position=new_position,
            normal=anchor.normal,
            kind=anchor.kind,
            surface_params=anchor.surface_params,
        )

    raise ValidationError(
        f"attach: angle= is not supported for this anchor (kind="
        f"{anchor.kind!r}). Anchors that support angular placement: "
        f"cylindrical (cylinder wall), conical (cone wall), and planar "
        f"caps with rim_radius (cylinder/cone top/bottom).",
        source_location=loc,
    )


def _apply_attach_at_z(anchor, at_z, loc):
    """Return a new Anchor shifted along the surface axis by ``at_z`` mm.

    Valid only on cylindrical and conical wall anchors. For conical
    anchors, the position is also adjusted radially to stay on the
    slanted surface — without that, an axis-only shift would put the
    new anchor inside the cone (for inward narrowing) or outside it
    (for outward widening) rather than on the wall.

    Rim anchors don't have a meaningful "axial" direction perpendicular
    to their plane in the same sense — for those, ``radius=`` already
    covers the in-plane radial offset.
    """
    from scadwright.anchor import Anchor
    from scadwright.errors import ValidationError

    if anchor.kind not in ("cylindrical", "conical"):
        raise ValidationError(
            f"attach: at_z= is for cylindrical and conical wall anchors "
            f"(it shifts along the surface axis); this anchor is "
            f"{anchor.kind!r}. For radial offset on a rim, use radius=.",
            source_location=loc,
        )

    axis = anchor.surface_param("axis")
    if axis is None:
        raise ValidationError(
            "attach: at_z= requires the anchor to carry a surface axis; "
            "this anchor's surface_params lack 'axis'.",
            source_location=loc,
        )

    new_position = (
        anchor.position[0] + at_z * axis[0],
        anchor.position[1] + at_z * axis[1],
        anchor.position[2] + at_z * axis[2],
    )

    new_normal = anchor.normal
    if anchor.kind == "conical":
        r1 = anchor.surface_param("r1")
        r2 = anchor.surface_param("r2")
        length = anchor.surface_param("length")
        if r1 is None or r2 is None or length is None or length == 0:
            raise ValidationError(
                "attach: conical anchor missing r1/r2/length surface_params; "
                "cannot compute the radial adjustment for at_z=.",
                source_location=loc,
            )
        slope = (r2 - r1) / length
        # The +X-meridian outward direction is +anchor.normal for outer
        # walls, -anchor.normal for inner walls (where normal points
        # toward the axis).
        inner = bool(anchor.surface_param("inner", default=False))
        s_outward = -1.0 if inner else 1.0
        radial_shift = slope * at_z
        new_position = (
            new_position[0] + radial_shift * s_outward * anchor.normal[0],
            new_position[1] + radial_shift * s_outward * anchor.normal[1],
            new_position[2] + radial_shift * s_outward * anchor.normal[2],
        )
        r_mid = (r1 + r2) / 2.0
        local_radius = r_mid + slope * at_z
        if local_radius <= 0:
            raise ValidationError(
                f"attach: at_z={at_z} on a conical anchor places the "
                f"attachment at radius {local_radius:.3f} (cone tip or "
                f"beyond). Pick an at_z where the cone radius is "
                f"positive.",
                source_location=loc,
            )
        # Match _apply_attach_angle: when placing on a cone wall, expose
        # the slanted-surface normal so orient=True lays the part flush
        # against the wall instead of perpendicular to the radial
        # reference. (Composition with angle= still produces the right
        # final normal — _apply_attach_angle recomputes from r1/r2/length
        # and rotates.)
        new_normal = _cone_slanted_normal(r1, r2, length, inner=inner)

    return Anchor(
        position=new_position,
        normal=new_normal,
        kind=anchor.kind,
        surface_params=anchor.surface_params,
    )


_PI = 3.141592653589793


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
