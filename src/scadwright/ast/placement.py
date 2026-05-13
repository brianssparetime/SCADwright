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

    from scadwright.api.tolerances import AXIS_LEN_DEGEN_TOL, coincidence_tol
    tol_detect = coincidence_tol()
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
            if parent_size[i] > AXIS_LEN_DEGEN_TOL:
                r = self_bb.size[i] / parent_size[i]
                if r > best_ratio:
                    best_ratio = r
                    best = i
        return best
    # No coincident faces — fall back to the closest size match.
    self_size = self_bb.size
    ratios = [
        float("inf") if parent_size[i] < AXIS_LEN_DEGEN_TOL
        else abs(self_size[i] / parent_size[i] - 1.0)
        for i in range(3)
    ]
    return ratios.index(min(ratios))


def _extend_through_faces(self, self_bb, parent_bb, ax: int, eps: float, loc):
    """Wrap the cutter in the Scale+Translate that extends it across
    whichever of its ``ax``-faces are coincident with the parent's.
    Returns the cutter unchanged when no face matches (the call site's
    no-op contract). Raises ``ValidationError`` if the cutter doesn't
    overlap the parent on the cut axis at all.

    The ``self`` parameter is the cutter (named ``self`` to match the
    chained-method call convention from ``Node.through``).
    """
    from scadwright.api.tolerances import AXIS_LEN_DEGEN_TOL, coincidence_tol
    from scadwright.ast.transforms import Scale, Translate
    from scadwright.errors import ValidationError

    tol = coincidence_tol()
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
    if orig_size < AXIS_LEN_DEGEN_TOL:
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
        if anchor.radius is None:
            return None
        s_outward = -1.0 if anchor.inner else 1.0
        return (
            anchor.position[0] - anchor.radius * s_outward * anchor.normal[0],
            anchor.position[1] - anchor.radius * s_outward * anchor.normal[1],
            anchor.position[2] - anchor.radius * s_outward * anchor.normal[2],
        )
    if anchor.kind == "conical":
        if anchor.r1 is None or anchor.r2 is None:
            return None
        r_mid = (anchor.r1 + anchor.r2) / 2.0
        s_outward = -1.0 if anchor.inner else 1.0
        return (
            anchor.position[0] - r_mid * s_outward * anchor.normal[0],
            anchor.position[1] - r_mid * s_outward * anchor.normal[1],
            anchor.position[2] - r_mid * s_outward * anchor.normal[2],
        )
    if anchor.kind == "meridional":
        # Meridional anchors carry a ready-made axis-origin point that
        # survives at_z mutations — the cylindrical "position - radius *
        # normal" formula doesn't work here because the post-at_z normal
        # tilts off pure-radial along the curved meridian.
        if anchor.axis_origin is None:
            return None
        return (
            float(anchor.axis_origin[0]),
            float(anchor.axis_origin[1]),
            float(anchor.axis_origin[2]),
        )
    if anchor.kind == "planar" and anchor.rim_radius is not None:
        return anchor.position
    return None


def _meridian_arc_at(at_z: float, meridian_r: float, mid_r: float, s: int):
    """Evaluate the circular-arc meridian at axial offset ``at_z`` from
    the equator. Returns ``(local_radius, slant_outward, slant_axial)``
    where ``local_radius`` is the radial distance from the central axis
    at that point, and (``slant_outward``, ``slant_axial``) are the
    components of the surface's outward unit normal in the (radial,
    axial) frame.

    The arc passes through (end_r, ±h/2) and (mid_r, 0) (after centering
    on the equator) with center at ``(mid_r - s*meridian_r, 0)`` in the
    (radial, axial) plane. ``s`` is +1 for convex (bulging outward) and
    −1 for concave (waisted inward). Raises ``ValueError`` if ``at_z`` is
    outside the arc's vertical extent.
    """
    import math as _math
    from scadwright.api.tolerances import ARC_CLAMP_TOL

    sin_alpha = at_z / meridian_r
    if abs(sin_alpha) > 1.0 + ARC_CLAMP_TOL:
        raise ValueError(
            f"at_z={at_z} is outside the meridian arc's axial range "
            f"(|at_z| ≤ {meridian_r:.4g})."
        )
    sin_alpha = max(-1.0, min(1.0, sin_alpha))
    cos_alpha = _math.sqrt(max(0.0, 1.0 - sin_alpha * sin_alpha))
    local_r = mid_r + s * meridian_r * (cos_alpha - 1.0)
    slant_outward = cos_alpha
    slant_axial = s * sin_alpha
    return local_r, slant_outward, slant_axial


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
    from scadwright.api.tolerances import AXIS_LEN_DEGEN_TOL

    slope_x = r2 - r1
    slope_z = length
    L = _math.hypot(slope_x, slope_z)
    sign = -1.0 if inner else 1.0
    if L < AXIS_LEN_DEGEN_TOL:
        return (sign * 1.0, 0.0, 0.0)
    return (sign * slope_z / L, 0.0, sign * (-slope_x / L))


def _apply_attach_angle(anchor, angle, at_radial, loc):
    """Return a new Anchor with position (and possibly normal) rotated
    around the surface axis to angular position ``angle``.

    Rotation is around the cylinder's actual axis line (through the
    point returned by ``_axis_origin_for``), not the axis direction
    through the world origin. This matters when the host has been
    translated: the axis line moves with it, and the rotation needs to
    follow.

    Behavior dispatches on ``anchor.kind``:

    - **cylindrical** (``outer_wall`` of a cylinder): rotate position
      and normal around the axis line by ``angle``. ``at_radial=`` is
      rejected (the anchor sits on the wall surface; different radii
      would mean a different surface).

    - **conical** (``outer_wall`` of a cone): same rotation, but the
      "normal" used for the rotated anchor is the cone's *slanted*
      surface normal (not the radial reference normal that
      ``add_text`` consumes). This ensures ``attach()`` aligns parts
      perpendicular to the slanted wall, which is what the user
      expects for surface-mounted attachments.

    - **planar with rim_radius** (``top``/``bottom`` of a cylinder/cone):
      position becomes a point on the cap at radial distance
      ``at_radial`` (defaulting to ``rim_radius``) at angular position
      ``angle``, rotated around the axis. Normal stays as-is (axial —
      perpendicular to the cap face). ``at_radial=0`` is the legitimate
      "center of cap" case.

    - **Anything else**: raise — the anchor doesn't expose surface
      geometry that an angular position can refer to.
    """
    from dataclasses import replace
    from scadwright.anchor import resolve_angle_to_radians
    from scadwright.errors import ValidationError
    from scadwright.matrix import Matrix

    angle_rad = resolve_angle_to_radians(angle, context_name="attach")
    angle_deg = angle_rad * (180.0 / _PI)

    if anchor.axis is None:
        raise ValidationError(
            f"attach: angle= is not supported for this anchor (kind="
            f"{anchor.kind!r}). Anchors that support angular placement: "
            f"cylindrical (cylinder wall), conical (cone wall), meridional "
            f"(curved-meridian wall), and planar caps with rim_radius "
            f"(cylinder/cone top/bottom).",
            source_location=loc,
        )

    rotation = Matrix.rotate_axis_angle(angle_deg, anchor.axis)

    if anchor.kind == "cylindrical":
        if at_radial is not None:
            raise ValidationError(
                "attach: at_radial= is not valid on a cylindrical anchor "
                "(the wall sits at a fixed radius). Use at_radial= only "
                "on cap anchors with rim_radius.",
                source_location=loc,
            )
        origin = _axis_origin_for(anchor)
        new_position = _rotate_about_line(anchor.position, rotation, origin)
        new_normal = rotation.apply_vector(anchor.normal)
        return replace(anchor, position=new_position, normal=new_normal)

    if anchor.kind == "meridional":
        if at_radial is not None:
            raise ValidationError(
                "attach: at_radial= is not valid on a meridional anchor "
                "(the wall radius is fixed by the meridian geometry). "
                "Use at_radial= only on cap anchors with rim_radius.",
                source_location=loc,
            )
        origin = _axis_origin_for(anchor)
        if origin is None:
            raise ValidationError(
                "attach: meridional anchor missing 'axis_origin'; cannot "
                "rotate around the central axis.",
                source_location=loc,
            )
        new_position = _rotate_about_line(anchor.position, rotation, origin)
        new_normal = rotation.apply_vector(anchor.normal)
        # Rotate meridian_zero so subsequent at_z calls walk along the
        # meridian at the new angular position. axis stays — the central
        # axis is invariant under its own rotation.
        new_meridian_zero = anchor.meridian_zero
        if anchor.meridian_zero is not None:
            new_meridian_zero = rotation.apply_vector(anchor.meridian_zero)
        return replace(
            anchor,
            position=new_position,
            normal=new_normal,
            meridian_zero=new_meridian_zero,
        )

    if anchor.kind == "conical":
        if at_radial is not None:
            raise ValidationError(
                "attach: at_radial= is not valid on a conical anchor "
                "(the wall radius is fixed by the cone geometry). Use "
                "at_radial= only on cap anchors with rim_radius.",
                source_location=loc,
            )
        # Slanted surface normal at the +X meridian, then rotate.
        if anchor.r1 is None or anchor.r2 is None or anchor.length is None:
            raise ValidationError(
                "attach: conical anchor missing r1/r2/length; cannot "
                "compute the slanted normal.",
                source_location=loc,
            )
        slanted_ref = _cone_slanted_normal(
            anchor.r1, anchor.r2, anchor.length, inner=anchor.inner,
        )
        origin = _axis_origin_for(anchor)
        new_position = _rotate_about_line(anchor.position, rotation, origin)
        new_normal = rotation.apply_vector(slanted_ref)
        return replace(anchor, position=new_position, normal=new_normal)

    # Planar with rim_radius — cap of a cylinder/cone. The rim's
    # ``axis`` is the cylinder's central axis (same direction as the
    # wall's), and ``meridian_zero`` is the +X-meridian direction in
    # the rim plane in the host's local frame. Both transform with the
    # host, so a host rotated around its own axis still gets the right
    # +X-meridian reference direction.
    if anchor.kind == "planar" and anchor.rim_radius is not None:
        r = anchor.rim_radius if at_radial is None else at_radial
        if r < 0:
            raise ValidationError(
                f"attach: at_radial= must be non-negative, got {at_radial}",
                source_location=loc,
            )
        meridian_zero = anchor.meridian_zero or (1.0, 0.0, 0.0)
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
        return replace(anchor, position=new_position)

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
    to their plane in the same sense — for those, ``at_radial=`` already
    covers the in-plane radial offset.
    """
    from dataclasses import replace
    from scadwright.errors import ValidationError

    if anchor.kind not in ("cylindrical", "conical", "meridional"):
        raise ValidationError(
            f"attach: at_z= is for cylindrical, conical, and meridional "
            f"wall anchors (it shifts along the surface axis); this "
            f"anchor is {anchor.kind!r}. For radial offset on a rim, "
            f"use at_radial=.",
            source_location=loc,
        )

    if anchor.axis is None:
        raise ValidationError(
            "attach: at_z= requires the anchor to carry a surface axis; "
            "this anchor lacks an 'axis'.",
            source_location=loc,
        )
    axis = anchor.axis

    if anchor.kind == "meridional":
        # Curved-meridian wall: jump along the actual arc, not just the
        # axis. Position lands on the surface at the new axial offset and
        # normal tilts to the local tangent plane.
        if (anchor.meridian_r is None or anchor.mid_r is None
                or anchor.meridian_s is None or anchor.length is None
                or anchor.meridian_zero is None
                or anchor.axis_origin is None):
            raise ValidationError(
                "attach: meridional anchor missing one of meridian_r, "
                "mid_r, meridian_s, length, meridian_zero, axis_origin; "
                "cannot evaluate the curved meridian.",
                source_location=loc,
            )
        from scadwright.api.tolerances import ARC_CLAMP_TOL
        if abs(at_z) > anchor.length / 2.0 + ARC_CLAMP_TOL:
            raise ValidationError(
                f"attach: at_z={at_z} is outside the meridional wall's "
                f"axial extent [-{anchor.length/2}, {anchor.length/2}].",
                source_location=loc,
            )
        try:
            local_r, slant_outward, slant_axial = _meridian_arc_at(
                at_z, anchor.meridian_r, anchor.mid_r, anchor.meridian_s,
            )
        except ValueError as exc:
            raise ValidationError(
                f"attach: {exc}", source_location=loc,
            ) from exc

        s_outward = -1.0 if anchor.inner else 1.0
        meridian_zero = anchor.meridian_zero
        axis_origin = anchor.axis_origin

        new_position = (
            axis_origin[0] + local_r * meridian_zero[0] + at_z * axis[0],
            axis_origin[1] + local_r * meridian_zero[1] + at_z * axis[1],
            axis_origin[2] + local_r * meridian_zero[2] + at_z * axis[2],
        )
        new_normal = (
            s_outward * (slant_outward * meridian_zero[0] + slant_axial * axis[0]),
            s_outward * (slant_outward * meridian_zero[1] + slant_axial * axis[1]),
            s_outward * (slant_outward * meridian_zero[2] + slant_axial * axis[2]),
        )
        return replace(anchor, position=new_position, normal=new_normal)

    new_position = (
        anchor.position[0] + at_z * axis[0],
        anchor.position[1] + at_z * axis[1],
        anchor.position[2] + at_z * axis[2],
    )

    new_normal = anchor.normal
    if anchor.kind == "conical":
        if (anchor.r1 is None or anchor.r2 is None
                or anchor.length is None or anchor.length == 0):
            raise ValidationError(
                "attach: conical anchor missing r1/r2/length; cannot "
                "compute the radial adjustment for at_z=.",
                source_location=loc,
            )
        slope = (anchor.r2 - anchor.r1) / anchor.length
        s_outward = -1.0 if anchor.inner else 1.0
        radial_shift = slope * at_z
        new_position = (
            new_position[0] + radial_shift * s_outward * anchor.normal[0],
            new_position[1] + radial_shift * s_outward * anchor.normal[1],
            new_position[2] + radial_shift * s_outward * anchor.normal[2],
        )
        r_mid = (anchor.r1 + anchor.r2) / 2.0
        local_radius = r_mid + slope * at_z
        if local_radius <= 0:
            raise ValidationError(
                f"attach: at_z={at_z} on a conical anchor places the "
                f"attachment at radius {local_radius:.3f} (cone tip or "
                f"beyond). Pick an at_z where the cone radius is "
                f"positive.",
                source_location=loc,
            )
        new_normal = _cone_slanted_normal(
            anchor.r1, anchor.r2, anchor.length, inner=anchor.inner,
        )

    return replace(anchor, position=new_position, normal=new_normal)


_PI = 3.141592653589793


def _apply_attach_polar(anchor, polar, azimuth, loc):
    """Return a new spherical anchor at the (polar, azimuth) point on the
    sphere's surface.

    ``polar`` is the angle from the north-pole direction (``anchor.axis``),
    in degrees, range [0, 180]. ``polar=0`` is the
    pole itself; ``polar=90`` is the equator.

    ``azimuth`` is the rotation around the ``axis`` from the
    ``meridian_zero`` reference direction, in degrees CCW.

    Position is computed from the sphere's ``axis_origin`` (center) and
    ``radius``. Normal is the radial outward unit vector at that point.
    """
    import math as _math
    from dataclasses import replace

    from scadwright.anchor import resolve_angle_to_radians
    from scadwright.errors import ValidationError

    if anchor.kind != "spherical":
        raise ValidationError(
            f"attach: polar= is only valid on spherical anchors; this "
            f"anchor is kind={anchor.kind!r}. For cylindrical / conical / "
            f"meridional walls use angle= and at_z=.",
            source_location=loc,
        )

    # Spherical kind's __post_init__ already enforces these are non-None;
    # we still bind locally for readability.
    radius = anchor.radius
    axis = anchor.axis
    center = anchor.axis_origin
    meridian_zero = anchor.meridian_zero

    polar_rad = resolve_angle_to_radians(
        polar, context_name="attach", param_name="polar",
    )
    polar_deg = polar_rad * (180.0 / _PI)
    from scadwright.api.tolerances import ARC_CLAMP_TOL as _ARC_TOL
    if polar_deg < -_ARC_TOL or polar_deg > 180.0 + _ARC_TOL:
        raise ValidationError(
            f"attach: polar must be in [0, 180] degrees; got {polar_deg}.",
            source_location=loc,
        )
    azimuth_rad = resolve_angle_to_radians(
        azimuth, context_name="attach", param_name="angle",
    )

    # Build an orthonormal basis: axis (north pole), meridian_zero
    # (azimuth=0 reference in the equatorial plane), and their cross
    # product (azimuth=90).
    ax, ay, az = axis
    mx, my, mz = meridian_zero
    # Cross product: axis × meridian_zero = the azimuth=90 direction.
    cx = ay * mz - az * my
    cy = az * mx - ax * mz
    cz = ax * my - ay * mx

    sin_p = _math.sin(polar_rad)
    cos_p = _math.cos(polar_rad)
    cos_a = _math.cos(azimuth_rad)
    sin_a = _math.sin(azimuth_rad)

    rx = sin_p * (cos_a * mx + sin_a * cx) + cos_p * ax
    ry = sin_p * (cos_a * my + sin_a * cy) + cos_p * ay
    rz = sin_p * (cos_a * mz + sin_a * cz) + cos_p * az

    new_position = (
        center[0] + radius * rx,
        center[1] + radius * ry,
        center[2] + radius * rz,
    )
    new_normal = (rx, ry, rz)

    return replace(anchor, position=new_position, normal=new_normal)


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

    from scadwright.api.tolerances import PARALLEL_CROSS_TOL
    d = _dot(self_normal, target_normal)
    axis = _cross(self_normal, target_normal)
    if _length(axis) > PARALLEL_CROSS_TOL:
        # General case: rotate around the cross-product axis.
        angle_deg = _math.degrees(_math.acos(max(-1.0, min(1.0, d))))
        return Rotate(a=angle_deg, v=axis, child=child, source_location=loc)
    if d > 0.5:
        # Already aligned: self_normal already points toward target_normal.
        return child
    # Anti-parallel: 180° flip around any perpendicular axis.
    perp = _cross(self_normal, (1, 0, 0) if abs(self_normal[0]) < 0.9 else (0, 1, 0))
    return Rotate(a=180.0, v=perp, child=child, source_location=loc)


# =============================================================================
# Bond dispatch — the per-bond worker functions used by Node.attach and
# boolops.fuse, plus predicates and a single shift-translate helper.
#
# Each dispatch helper is **strict**: preconditions raise rather than fall
# through. The smart cascade composes the predicates with the strict
# helpers; the explicit ``bond="..."`` paths call one helper directly.
# =============================================================================


_VALID_BOND_VALUES = ("overlap", "bridge", "shift")


def _validate_bond_and_fuse(bond, fuse, loc):
    """Validate the (bond, fuse) kwarg pair on ``Node.attach``.

    The ``fuse`` kwarg uses ``None`` as its sentinel default, so the
    validator can distinguish "user didn't pass anything" (treat
    ``bond=`` as implying ``fuse=True``) from "user explicitly passed
    ``fuse=False``" (contradicts an explicit bond).

    - ``bond=None``, ``fuse=None``: no fuse semantics (default behavior).
    - ``bond=None``, ``fuse=True``: smart cascade.
    - ``bond=None``, ``fuse=False``: no fuse (explicit, same effect as
      the default).
    - ``bond="..."``, ``fuse=None``: implies ``fuse=True``.
    - ``bond="..."``, ``fuse=True``: redundant but allowed.
    - ``bond="..."``, ``fuse=False``: raises (contradiction).
    - Anything else for ``bond`` raises with the valid set.

    Returns the effective ``(bond, fuse_bool)`` pair.
    """
    from scadwright.errors import ValidationError

    if bond is None:
        # Default fuse to False when user didn't specify (sentinel = None).
        return None, bool(fuse) if fuse is not None else False
    if bond not in _VALID_BOND_VALUES:
        raise ValidationError(
            f"attach: bond= must be one of "
            f"{list(_VALID_BOND_VALUES)} or None; got {bond!r}.",
            source_location=loc,
        )
    if fuse is False:
        raise ValidationError(
            f"attach: fuse=False contradicts bond={bond!r}. Pass either "
            f"bond= (which implies fuse=True) or fuse=False without a bond, "
            f"not both.",
            source_location=loc,
        )
    return bond, True


def _validate_bond_value(bond, loc, *, context: str = "fuse"):
    """Validate ``bond`` for ``boolops.fuse`` (no separate ``fuse`` kwarg).

    Returns the validated bond (None or one of the three values).
    """
    from scadwright.errors import ValidationError

    if bond is None or bond in _VALID_BOND_VALUES:
        return bond
    raise ValidationError(
        f"{context}: bond= must be one of "
        f"{list(_VALID_BOND_VALUES)} or None; got {bond!r}.",
        source_location=loc,
    )


def _can_dispatch_bridge(other_anchor) -> bool:
    """Whether ``bond='bridge'`` applies to this on-anchor.

    Requires a curved convex-outer host with a usable analytical radius.
    """
    is_curved = other_anchor.kind in ("cylindrical", "conical", "spherical")
    is_inner = other_anchor.inner
    if not (is_curved and not is_inner):
        return False
    radius = other_anchor.radius
    if radius is None and other_anchor.kind == "conical":
        radius = max(other_anchor.r1 or 0.0, other_anchor.r2 or 0.0)
    return bool(radius)


def _can_dispatch_overlap(self_anchor, other_anchor) -> bool:
    """Whether ``bond='overlap'`` applies — both anchors planar."""
    return self_anchor.kind == "planar" and other_anchor.kind == "planar"


def _shift_translate(working_self, self_anchor, other_anchor, *, with_eps, eps, loc):
    """Translate ``working_self`` so its anchor coincides with ``other_anchor``.

    ``with_eps=True`` adds the bilateral-shift eps offset along the
    contact normal (the legacy behavior for non-extendable shapes).
    ``with_eps=False`` does exact anchor coincidence.
    """
    from scadwright.ast.transforms import Translate

    shift = _shift_for_anchors(self_anchor, other_anchor, with_eps, eps)
    return Translate(v=shift, child=working_self, source_location=loc)


def _dispatch_overlap(working_self, working_self_anchor, other_anchor, eps, loc):
    """Local extension at a planar contact face. Strict — preconditions raise.

    Tier 1 (parametric ``fuse_extend``) wins when available; Tier 2
    (cross-section) is the universal fallback for planar contact.
    Cross-section's validator raises on degenerate geometry; if it
    succeeds, the placement preserves the user-facing dimensions of
    ``working_self`` exactly — only the contact face moves by ``eps``.
    """
    from scadwright.errors import ValidationError

    if working_self_anchor.kind != "planar":
        raise ValidationError(
            f"bond='overlap' requires a planar contact face on self (the "
            f"at-anchor); got kind={working_self_anchor.kind!r}. For curved "
            f"hosts, use bond='bridge'. For non-planar contacts that can't "
            f"be extended, use bond='shift' to accept the bilateral drift, "
            f"or fuse=False for exact contact.",
            source_location=loc,
        )
    if other_anchor.kind != "planar":
        raise ValidationError(
            f"bond='overlap' requires a planar contact face on other (the "
            f"on-anchor); got kind={other_anchor.kind!r}. For curved hosts, "
            f"use bond='bridge'.",
            source_location=loc,
        )

    extended = working_self.fuse_extend(working_self_anchor, eps)
    if extended is None:
        # Tier 2: cross-section. Raises on degenerate geometry; on
        # planar input it always returns a non-None result otherwise.
        extended = working_self.cross_section_extend(working_self_anchor, eps)
    return _shift_translate(
        extended, working_self_anchor, other_anchor,
        with_eps=False, eps=eps, loc=loc,
    )


def _dispatch_bridge(working_self, bridge_self_anchor, other, other_anchor, eps, loc):
    """Curved-host inscription bridge. Strict — preconditions raise.

    Builds a prism of the peg's cross-section, subtracted with the host,
    placed in the inscription gap between the peg's planar near-face and
    the host's curved surface. Returns ``union(placed_peg, bridge)``.
    """
    from scadwright.ast._fuse_bridge import build_curved_bridge, coaxial_normals
    from scadwright.boolops import union as _union
    from scadwright.errors import ValidationError

    if other_anchor.kind not in ("cylindrical", "conical", "spherical"):
        raise ValidationError(
            f"bond='bridge' requires a curved on-anchor (kind 'cylindrical', "
            f"'conical', or 'spherical'); got kind={other_anchor.kind!r}. "
            f"For planar-planar fuses, use bond='overlap'.",
            source_location=loc,
        )
    if other_anchor.inner:
        raise ValidationError(
            f"bond='bridge' is for convex-outer curved hosts; the on-anchor "
            f"on {type(other).__name__} is marked inner. The peg's corners "
            f"naturally inscribe into inner-wall material — use bond='shift' "
            f"or fuse=False.",
            source_location=loc,
        )
    if not coaxial_normals(bridge_self_anchor.normal, other_anchor.normal):
        raise ValidationError(
            f"bond='bridge' on a {other_anchor.kind} host requires coaxial "
            f"normals (peg at-anchor anti-parallel to host on-anchor). Got "
            f"peg normal {bridge_self_anchor.normal}, host normal "
            f"{other_anchor.normal}. Pass orient=True, or align the peg "
            f"manually so its at-anchor faces the host's on-anchor.",
            source_location=loc,
        )

    unfused_shift = _shift_for_anchors(
        bridge_self_anchor, other_anchor, False, eps,
    )
    bridge = build_curved_bridge(
        working_self, bridge_self_anchor, other, other_anchor,
        unfused_shift, eps,
    )
    if bridge is None:
        raise ValidationError(
            f"bond='bridge': host on-anchor (kind={other_anchor.kind!r}) "
            f"doesn't carry a usable radius in surface_params, so the "
            f"analytical inscription depth can't be computed. Check the "
            f"host's anchor declaration, or use bond='shift' / fuse=False.",
            source_location=loc,
        )

    from scadwright.ast.transforms import Translate
    placed_peg = Translate(
        v=unfused_shift, child=working_self, source_location=loc,
    )
    return _union(placed_peg, bridge)


def _dispatch_smart_cascade_attach(
    working_self, working_self_anchor, bridge_self_anchor,
    other, other_anchor, eps, loc,
):
    """Smart cascade for ``Node.attach(fuse=True)``.

    Try bridge if applicable, then overlap if applicable, otherwise
    raise — no silent fall-through to bilateral shift. The user who
    actually wants the shift writes ``bond='shift'`` explicitly.
    """
    from scadwright.errors import ValidationError

    if _can_dispatch_bridge(other_anchor):
        return _dispatch_bridge(
            working_self, bridge_self_anchor, other, other_anchor, eps, loc,
        )
    if _can_dispatch_overlap(working_self_anchor, other_anchor):
        return _dispatch_overlap(
            working_self, working_self_anchor, other_anchor, eps, loc,
        )
    raise ValidationError(
        f"fuse=True: no applicable bond for this attach.\n"
        f"  bond='overlap' needs planar+planar contact (got "
        f"self.kind={working_self_anchor.kind!r}, "
        f"other.kind={other_anchor.kind!r}).\n"
        f"  bond='bridge' needs a convex-outer curved host with a "
        f"radius (got kind={other_anchor.kind!r}, "
        f"inner={other_anchor.inner}).\n"
        f"To accept the bilateral shift (the entire shape moves by eps "
        f"along the contact normal), pass bond='shift'. For exact "
        f"contact, fuse=False. To skip auto-eps in a whole scope, wrap "
        f"in disable_eps_fuse().",
        source_location=loc,
    )


# =============================================================================
# Symmetric bond dispatch — used by ``boolops.fuse(a, b, ...)``, where
# either side may be the host (curved bridge case) or the extended side
# (overlap case). The chained-method ``Node.attach`` only ever moves
# self, so it uses the asymmetric dispatchers above; the standalone
# ``fuse()`` accepts both shapes as peers and picks the better side.
# =============================================================================


def _extension_is_exact(node) -> bool:
    """Whether ``node.fuse_extend(anchor)`` produces a shape whose
    geometry elsewhere is unchanged (apart from the contact face).

    - **Cube** with any face anchor: bumps a single ``size[axis]``; the
      shape elsewhere is identical → exact.
    - **Cylinder** with planar cap, true cylinder (``r1 == r2``):
      bumps ``h``; wall radius unchanged → exact.
    - **Cylinder** with planar cap, cone (``r1 != r2``): bumping ``h``
      changes the cone slope by ``eps/h`` — geometrically inexact even
      though imperceptible at typical eps values.
    - **LinearExtrude** end-cap: bumping ``height`` rescales the
      profile-to-axis ratio; any per-vertex twist propagates
      proportionally → inexact.

    Recurses through ``Translate`` / ``Rotate`` / ``Mirror`` wrappers
    (they don't change extension exactness).
    """
    from scadwright.ast.extrude import LinearExtrude
    from scadwright.ast.primitives import Cube, Cylinder
    from scadwright.ast.transforms import Mirror, Rotate, Translate

    if isinstance(node, (Translate, Rotate, Mirror)):
        return _extension_is_exact(node.child)
    if isinstance(node, Cube):
        return True
    if isinstance(node, Cylinder):
        return node.r1 == node.r2
    if isinstance(node, LinearExtrude):
        return False
    return False  # defensive: any other shape that snuck into Tier 1


def _pick_simpler_extension(a, b, extended_a, extended_b):
    """Pick the side to extend in symmetric ``boolops.fuse``.

    Returns ``"a"``, ``"b"``, or ``None`` (neither qualified).

    Ranking, in order:

    1. Exactly one side qualified (the other returned ``None``) → pick
       the qualifying side.
    2. Both qualified: prefer the side whose extension is geometrically
       exact (Cube or true Cylinder cap) over near-exact (cone cap,
       linear_extrude). Cross-section extensions are non-exact in this
       sense; in the Tier-2 cascade both sides classify as non-exact and
       the tiebreaker below applies.
    3. Within the same exactness tier, prefer the leaf over the
       Translate-wrapped form (cleaner SCAD output).
    4. Within all ties, prefer ``a`` (deterministic).
    """
    if extended_a is None and extended_b is None:
        return None
    if extended_a is None:
        return "b"
    if extended_b is None:
        return "a"

    a_exact = _extension_is_exact(a)
    b_exact = _extension_is_exact(b)
    if a_exact and not b_exact:
        return "a"
    if b_exact and not a_exact:
        return "b"

    # Same exactness tier — fall back to leaf-vs-wrapped tiebreaker.
    from scadwright.ast.transforms import Translate as _Translate
    a_wrapped = isinstance(extended_a, _Translate)
    b_wrapped = isinstance(extended_b, _Translate)
    if a_wrapped and not b_wrapped:
        return "b"
    return "a"


def _dispatch_overlap_symmetric(a, a_anchor, b, b_anchor, eps, loc):
    """Symmetric overlap for ``boolops.fuse``: either side may extend.

    Tier 1 (parametric ``fuse_extend``) on either side wins; ties broken
    by ``_pick_simpler_extension``. Tier 2 (cross-section) on either
    side is the fallback.
    """
    from scadwright.ast.transforms import Translate
    from scadwright.boolops import union as _union
    from scadwright.errors import ValidationError

    if a_anchor.kind != "planar" or b_anchor.kind != "planar":
        raise ValidationError(
            f"bond='overlap' requires planar contact face on both sides; "
            f"got a.kind={a_anchor.kind!r}, b.kind={b_anchor.kind!r}. "
            f"For curved hosts, use bond='bridge'.",
            source_location=loc,
        )

    # Tier 1.
    extended_a = a.fuse_extend(a_anchor, eps)
    extended_b = b.fuse_extend(b_anchor, eps)
    chosen = _pick_simpler_extension(a, b, extended_a, extended_b)
    if chosen == "a":
        shift = _shift_for_anchors(a_anchor, b_anchor, False, eps)
        placed_a = Translate(v=shift, child=extended_a, source_location=loc)
        return _union(placed_a, b)
    if chosen == "b":
        shift = _shift_for_anchors(a_anchor, b_anchor, False, eps)
        placed_a = Translate(v=shift, child=a, source_location=loc)
        return _union(placed_a, extended_b)

    # Tier 2: neither side has parametric extension. cross_section_extend
    # raises on degenerate contact, so a passing call returns non-None.
    extended_a = a.cross_section_extend(a_anchor, eps)
    extended_b = b.cross_section_extend(b_anchor, eps)
    chosen = _pick_simpler_extension(a, b, extended_a, extended_b)
    if chosen == "a":
        shift = _shift_for_anchors(a_anchor, b_anchor, False, eps)
        placed_a = Translate(v=shift, child=extended_a, source_location=loc)
        return _union(placed_a, b)
    if chosen == "b":
        shift = _shift_for_anchors(a_anchor, b_anchor, False, eps)
        placed_a = Translate(v=shift, child=a, source_location=loc)
        return _union(placed_a, extended_b)

    # Defensive: planar inputs make this unreachable.
    raise ValidationError(
        "bond='overlap': cross-section extension returned None on both "
        "sides for planar anchors — internal invariant violation.",
        source_location=loc,
    )


def _dispatch_bridge_symmetric(a, a_anchor, b, b_anchor, eps, loc):
    """Symmetric bridge for ``boolops.fuse``.

    Convention: ``a`` is the side that moves (per ``fuse()``'s
    signature), ``b`` stays put. If ``b``'s anchor is the curved host,
    standard case: bridge between placed-a and b. If ``a``'s anchor is
    the curved host, ``b`` is the peg sitting at its original position,
    and ``a`` (translated) carries the curved surface.
    """
    from scadwright.ast._fuse_bridge import build_curved_bridge, coaxial_normals
    from scadwright.ast.transforms import Translate
    from scadwright.boolops import union as _union
    from scadwright.errors import ValidationError

    a_curved = a_anchor.kind in ("cylindrical", "conical", "spherical")
    b_curved = b_anchor.kind in ("cylindrical", "conical", "spherical")
    a_inner = a_anchor.inner
    b_inner = b_anchor.inner

    if not (a_curved or b_curved):
        raise ValidationError(
            f"bond='bridge' requires a curved on-anchor on either a or b "
            f"(kind 'cylindrical', 'conical', or 'spherical'); got "
            f"a.kind={a_anchor.kind!r}, b.kind={b_anchor.kind!r}. For "
            f"planar-planar fuses, use bond='overlap'.",
            source_location=loc,
        )

    if b_curved and not b_inner:
        # Standard convention: b is host, a is peg.
        if not coaxial_normals(a_anchor.normal, b_anchor.normal):
            raise ValidationError(
                f"bond='bridge' on a {b_anchor.kind} host (b) requires "
                f"coaxial normals (a's at-anchor anti-parallel to b's "
                f"on-anchor). Got a normal {a_anchor.normal}, b normal "
                f"{b_anchor.normal}.",
                source_location=loc,
            )
        unfused_shift = _shift_for_anchors(a_anchor, b_anchor, False, eps)
        bridge = build_curved_bridge(a, a_anchor, b, b_anchor, unfused_shift, eps)
        if bridge is None:
            raise ValidationError(
                f"bond='bridge': host (b, kind={b_anchor.kind!r}) doesn't "
                f"carry a usable radius in surface_params — analytical "
                f"inscription depth can't be computed.",
                source_location=loc,
            )
        placed_a = Translate(v=unfused_shift, child=a, source_location=loc)
        return _union(placed_a, b, bridge)

    if a_curved and not a_inner:
        # Symmetric: a is host, b is peg. fuse() still translates a per
        # its signature, so the bridge sees a-after-translation as host;
        # peg=b stays at its original position.
        if not coaxial_normals(b_anchor.normal, a_anchor.normal):
            raise ValidationError(
                f"bond='bridge' on a {a_anchor.kind} host (a) requires "
                f"coaxial normals (b's on-anchor anti-parallel to a's "
                f"at-anchor). Got a normal {a_anchor.normal}, b normal "
                f"{b_anchor.normal}.",
                source_location=loc,
            )
        unfused_shift = _shift_for_anchors(a_anchor, b_anchor, False, eps)
        placed_a = Translate(v=unfused_shift, child=a, source_location=loc)
        bridge = build_curved_bridge(
            b, b_anchor, placed_a, a_anchor, (0.0, 0.0, 0.0), eps,
        )
        if bridge is None:
            raise ValidationError(
                f"bond='bridge': host (a, kind={a_anchor.kind!r}) doesn't "
                f"carry a usable radius in surface_params — analytical "
                f"inscription depth can't be computed.",
                source_location=loc,
            )
        return _union(placed_a, b, bridge)

    # Both sides are inner curved (or some other degenerate combo).
    raise ValidationError(
        f"bond='bridge' is for convex-outer curved hosts; both anchors "
        f"are concave-inner (a.inner={a_inner}, b.inner={b_inner}). "
        f"The peg's corners naturally inscribe into inner-wall material — "
        f"use bond='shift' or fuse=False.",
        source_location=loc,
    )


def _dispatch_smart_cascade_fuse(a, a_anchor, b, b_anchor, eps, loc):
    """Smart cascade for ``boolops.fuse(a, b)``.

    Try bridge if either side is a convex-outer curved host, then
    overlap if planar+planar, otherwise raise — no silent fall-through
    to bilateral shift on ``a``. The user who actually wants the shift
    writes ``bond='shift'`` explicitly.
    """
    from scadwright.errors import ValidationError

    if _can_dispatch_bridge(b_anchor) or _can_dispatch_bridge(a_anchor):
        return _dispatch_bridge_symmetric(a, a_anchor, b, b_anchor, eps, loc)

    if _can_dispatch_overlap(a_anchor, b_anchor):
        return _dispatch_overlap_symmetric(a, a_anchor, b, b_anchor, eps, loc)

    a_inner = a_anchor.inner
    b_inner = b_anchor.inner
    raise ValidationError(
        f"fuse: no applicable bond for this combination.\n"
        f"  bond='overlap' needs planar+planar contact (got "
        f"a.kind={a_anchor.kind!r}, b.kind={b_anchor.kind!r}).\n"
        f"  bond='bridge' needs a convex-outer curved host on either "
        f"a or b (got a.kind={a_anchor.kind!r}/inner={a_inner}, "
        f"b.kind={b_anchor.kind!r}/inner={b_inner}).\n"
        f"To accept the bilateral shift (a moves by eps along b's "
        f"normal), pass bond='shift'. To skip auto-eps in a whole "
        f"scope, wrap in disable_eps_fuse().",
        source_location=loc,
    )
