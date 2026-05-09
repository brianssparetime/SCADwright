"""``add_text`` decoration transform: place raised or inset text on a host.

Registered on import. Adds ``.add_text(label=..., relief=..., font_size=..., ...)``
to every Node. See ``docs/add_text.md`` for the user-facing reference.

This module ships planar and cylindrical surface support. Conical surfaces
land with conical-surface support.
"""

from __future__ import annotations

import math
from typing import Any

from scadwright._custom_transforms._textmetrics import get_advances
from scadwright._custom_transforms.base import transform
from scadwright._logging import get_logger
from scadwright.anchor import (
    Anchor,
    FACE_NAMES,
    get_node_anchors,
)
from scadwright.ast.base import SourceLocation
from scadwright.ast.transforms import MultMatrix, Rotate, Translate
from scadwright.bbox import _text_bbox_estimate, bbox as _bbox
from scadwright.boolops import difference, union
from scadwright.errors import ValidationError
from scadwright.extrusions import linear_extrude
from scadwright.matrix import Matrix
from scadwright.primitives import text as _text_factory


_log = get_logger("scadwright.add_text")

# Overshoot used to avoid coincident-surface artifacts: extends a raised
# prism slightly into the host (clean union seam) and overshoots a cutter
# both above and below the surface (clean difference cut).
_PLACEMENT_EPS = 0.01

# Sentinel used as the default for ``valign`` so we can resolve it
# context-dependently (curved/rim → "baseline", flat planar → "center")
# without changing the kwarg's documented default for users who pass an
# explicit value.
_UNSET = object()


# --- Multi-line helpers ---


def _split_lines(label: str) -> list[str]:
    """Split a label on ``\\n``. Returns ``[label]`` for single-line input.

    Empty entries (consecutive ``\\n``s, leading/trailing ``\\n``) are kept
    so the spacing slot remains; the placement code skips emitting a glyph
    set for an empty line.
    """
    if "\n" not in label:
        return [label]
    return label.split("\n")


def _line_y_offsets(n: int, font_size: float, line_spacing: float, valign: str) -> list[float]:
    """Y-offset (in mm) for each line, with line 0 visually at the TOP.

    The block's overall vertical placement is controlled by ``valign``:
    ``"center"`` centers the block on y=0; ``"top"`` puts the top edge of
    line 0 at y=0; ``"bottom"`` and ``"baseline"`` put the bottom edge of
    the last line at y=0. Per-line ``valign`` is forced to ``"center"``
    inside individual ``text()`` calls, so each line's bbox is centered
    on its returned y-coord.
    """
    spacing = line_spacing * font_size
    block_h = (n - 1) * spacing + font_size
    if valign == "center":
        base_y_top = block_h / 2.0 - font_size / 2.0
    elif valign == "top":
        base_y_top = 0.0 - font_size / 2.0
    else:  # bottom or baseline
        base_y_top = block_h - font_size / 2.0
    return [base_y_top - i * spacing for i in range(n)]


# Per-face (u, v) tangent frames for the 12 standard bbox names. ``u`` is the
# "right" direction and ``v`` is "up" when the face is viewed from outside
# the host. ``at=(u, v)`` on a named face translates by ``u * u_axis +
# v * v_axis``. Picked so axis-aligned faces feel natural; arbitrary
# normals fall back to the algorithmic frame below.
_FACE_TANGENT_FRAMES: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "top":    ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "+z":     ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "bottom": ((1.0, 0.0, 0.0), (0.0, -1.0, 0.0)),
    "-z":     ((1.0, 0.0, 0.0), (0.0, -1.0, 0.0)),
    "front":  ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "-y":     ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "back":   ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "+y":     ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "rside":  ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    "+x":     ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    "lside":  ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "-x":     ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
}


def _face_tangent_frame(face_name, normal):
    """Return ``(u_axis, v_axis)`` — the in-plane right/up directions for a
    planar surface. Hardcoded for the 12 standard face names; deterministic
    algorithmic fallback for custom anchors and ad-hoc Anchors.

    The fallback rule: ``u = normalize(cross(world_+Z, normal))`` (or
    ``cross(world_+Y, normal)`` if ``normal`` is parallel to ``+Z``);
    ``v = normalize(cross(normal, u))``. Right-handed by construction.
    """
    if face_name in _FACE_TANGENT_FRAMES:
        return _FACE_TANGENT_FRAMES[face_name]

    nx, ny, nz = normal
    # Pick a reference axis not parallel to the normal.
    if abs(nz) < 0.99:
        ref = (0.0, 0.0, 1.0)
    else:
        ref = (0.0, 1.0, 0.0)
    u = (
        ref[1] * nz - ref[2] * ny,
        ref[2] * nx - ref[0] * nz,
        ref[0] * ny - ref[1] * nx,
    )
    u_len = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2)
    if u_len < 1e-12:
        # Degenerate (shouldn't happen with the above ref selection); fall back.
        u = (1.0, 0.0, 0.0)
        u_len = 1.0
    u = (u[0] / u_len, u[1] / u_len, u[2] / u_len)
    v = (
        normal[1] * u[2] - normal[2] * u[1],
        normal[2] * u[0] - normal[0] * u[2],
        normal[0] * u[1] - normal[1] * u[0],
    )
    v_len = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if v_len > 0:
        v = (v[0] / v_len, v[1] / v_len, v[2] / v_len)
    return u, v


# --- Placement resolution ---


def _resolve_placement(host, on, at, normal, loc):
    """Resolve user-supplied placement kwargs into ``(Anchor, face_dims_or_None)``.

    Three modes are supported, disambiguated by the kwarg combination:

    1. **Named only** — ``on=`` is a string or Anchor; ``at``/``normal`` are
       absent. Text sits at the face's reference position.
    2. **Named + offset within face** — ``on=`` is a string or Anchor;
       ``at`` is a 2-tuple ``(u, v)`` in mm. The Anchor's position is
       translated by ``u * u_axis + v * v_axis`` in the face's tangent
       plane. Only valid on planar anchors; cylindrical/conical anchors
       use ``meridian=``/``at_z=`` instead.
    3. **Ad-hoc** — ``on=`` is None; ``at`` is a 3-tuple ``(x, y, z)``
       and ``normal`` a 3-tuple direction. Treated as a planar anchor at
       that position.

    ``face_dims`` is a ``(u_extent, v_extent)`` tuple in mm describing the
    face's in-plane extent — used for overflow detection. Returned only
    when the host's bbox plus a standard face name unambiguously determine
    it; ``None`` otherwise (custom anchors and ad-hoc placement).
    """
    has_on = on is not None
    has_at = at is not None
    has_normal = normal is not None

    # Validate basic combinations.
    if has_on and has_normal:
        raise ValidationError(
            "add_text: `normal=` is for ad-hoc placement and cannot be "
            "combined with `on=`. To use a named face with an in-plane "
            "offset, pass `at=(u, v)` (a 2-tuple)."
        )
    if not has_on:
        if has_at and not has_normal:
            raise ValidationError(
                "add_text: ad-hoc placement requires both `at=` and `normal=`."
            )
        if has_normal and not has_at:
            raise ValidationError(
                "add_text: `normal=` requires `at=` (or pass an Anchor "
                "via `on=Anchor(...)` to bundle them)."
            )
        if not has_at:
            raise ValidationError(
                "add_text: must specify a placement — pass `on=` "
                "(a face name or an Anchor) or `at=` + `normal=`."
            )
        # Ad-hoc: at + normal both given. Warn if the host actually carries
        # curved-surface anchors — the user probably wants the wrap path.
        _warn_if_host_is_curved(host, loc)
        return _adhoc_anchor(at, normal), None

    # Named placement (with or without 2D offset).
    if isinstance(on, str):
        anchors = get_node_anchors(host)
        if on not in anchors:
            available = sorted(anchors)
            raise ValidationError(
                f"add_text: no anchor {on!r} on host. Available: {available}"
            )
        anchor = anchors[on]
        face_dims = _face_dimensions_for_named_face(host, on)
        anchor_name = on
    elif isinstance(on, Anchor):
        anchor = on
        face_dims = None
        anchor_name = None
    else:
        raise ValidationError(
            f"add_text: `on=` must be a face name (str) or Anchor, "
            f"got {type(on).__name__}."
        )

    # Apply 2D in-face offset if `at=` was given.
    if has_at:
        anchor = _apply_face_offset(anchor, anchor_name, at)

    return anchor, face_dims


def _resolve_planar_curvature(placement_anchor, text_curvature):
    """Resolve the rim/flat split for a planar anchor.

    Returns ``(is_rim, use_arc)``. Validates that ``text_curvature='arc'``
    only appears on rim anchors. Used both upfront (so the valign default
    can know whether placement will be per-glyph) and inside the planar
    dispatch (where it's always called).
    """
    rim_radius = placement_anchor.surface_param("rim_radius")
    is_rim = rim_radius is not None
    if text_curvature == "arc":
        if not is_rim:
            raise ValidationError(
                "add_text: text_curvature='arc' requires a rim anchor "
                "(top/bottom of a Cylinder, Tube, or Funnel). This "
                "anchor has no rim_radius surface_param."
            )
        return is_rim, True
    if text_curvature == "flat":
        return is_rim, False
    return is_rim, is_rim  # default: arc on rim, flat elsewhere


def _apply_face_offset(anchor, face_name, at):
    """Translate the anchor's position by an ``(u, v)`` offset in the face's
    tangent plane. Validates the kwarg shape and rejects on curved surfaces.
    """
    if anchor.kind != "planar":
        raise ValidationError(
            f"add_text: `at=` 2D offset is for flat faces; this anchor is "
            f"{anchor.kind!r}. Use `meridian=` for the angular position "
            f"and `at_z=` for the axial offset on curved surfaces."
        )
    if not (hasattr(at, "__len__") and len(at) == 2):
        raise ValidationError(
            f"add_text: `at=` with `on=` must be a 2-tuple (u, v) — the "
            f"in-face offset in mm. For ad-hoc 3D placement, drop `on=` "
            f"and pass `at=(x, y, z)` + `normal=`. Got {at!r}."
        )
    u, v = float(at[0]), float(at[1])
    u_axis, v_axis = _face_tangent_frame(face_name, anchor.normal)
    new_position = (
        anchor.position[0] + u * u_axis[0] + v * v_axis[0],
        anchor.position[1] + u * u_axis[1] + v * v_axis[1],
        anchor.position[2] + u * u_axis[2] + v * v_axis[2],
    )
    return Anchor(
        position=new_position,
        normal=anchor.normal,
        kind=anchor.kind,
        surface_params=anchor.surface_params,
    )


def _warn_if_host_is_curved(host, loc):
    """Warn when ad-hoc planar placement is used on a host that carries
    cylindrical or conical anchors — usually the user meant to wrap.
    """
    try:
        host_anchors = get_node_anchors(host)
    except Exception:
        # Anchor lookup can fail on unusual hosts; the warning is best-effort.
        return
    curved_names = sorted(
        name for name, a in host_anchors.items()
        if a.kind in ("cylindrical", "conical")
    )
    if not curved_names:
        return
    loc_str = f" (at {loc})" if loc else ""
    _log.warning(
        "add_text: ad-hoc planar placement on a host with curved anchors "
        "%s — text will not wrap. Use on='%s' for a wrapped label%s",
        curved_names, curved_names[0], loc_str,
    )


def _adhoc_anchor(at, normal) -> Anchor:
    if not (hasattr(at, "__len__") and len(at) == 3):
        raise ValidationError(
            f"add_text: `at=` must be a 3-tuple (x, y, z), got {at!r}."
        )
    if not (hasattr(normal, "__len__") and len(normal) == 3):
        raise ValidationError(
            f"add_text: `normal=` must be a 3-tuple (x, y, z), got {normal!r}."
        )
    pos = (float(at[0]), float(at[1]), float(at[2]))
    norm = (float(normal[0]), float(normal[1]), float(normal[2]))
    norm_len = math.sqrt(norm[0] ** 2 + norm[1] ** 2 + norm[2] ** 2)
    if norm_len < 1e-9:
        raise ValidationError("add_text: `normal=` must be a non-zero vector.")
    norm = (norm[0] / norm_len, norm[1] / norm_len, norm[2] / norm_len)
    return Anchor(position=pos, normal=norm, kind="planar")


def _face_dimensions_for_named_face(host, face_name):
    """Return the in-plane extents of a standard bbox face, or ``None``.

    Custom (non-bbox) anchors return None — we don't know their face
    extent. The overflow check is best-effort, so skipping is fine.
    """
    if face_name not in FACE_NAMES:
        return None
    axis_index, _sign = FACE_NAMES[face_name]
    bb = _bbox(host)
    other_axes = [i for i in range(3) if i != axis_index]
    return (bb.size[other_axes[0]], bb.size[other_axes[1]])


# --- Overflow check ---


def _check_overflow_block(face_dims, lines, font_size, spacing, line_spacing, label, source_location):
    """Block-bbox overflow check for multi-line text on a planar face.

    Width = max per-line glyph-advance estimate. Height = block height
    spanning all lines (including empty ones, which take their spacing
    slot). Single-line falls through to the existing per-Text bbox check
    via the original ``_check_overflow`` for backward-compatible warnings.
    """
    if face_dims is None:
        return
    n = len(lines)
    if n == 1:
        # Build a Text-like proxy via the factory and reuse the legacy check.
        # Cheaper: replicate the single-line width/height directly here.
        char_w = 0.6 * font_size * spacing
        text_w = char_w * len(lines[0])
        text_h = font_size
    else:
        char_w = 0.6 * font_size * spacing
        text_w = max((char_w * len(line) for line in lines if line), default=0.0)
        text_h = (n - 1) * line_spacing * font_size + font_size
    face_w, face_h = face_dims
    if text_w > face_w or text_h > face_h:
        loc_str = f" (at {source_location})" if source_location else ""
        _log.warning(
            "add_text: label %r estimated %.1fx%.1f mm overflows face "
            "%.1fx%.1f mm%s",
            label, text_w, text_h, face_w, face_h, loc_str,
        )


def _check_overflow(text_node, face_dims, label, source_location):
    """Log a warning if the estimated text bbox exceeds the face dimensions.

    The bbox heuristic is a font-agnostic estimate (``0.6 * size * spacing``
    per character); a warning catches obvious overflows without claiming
    pixel accuracy.
    """
    if face_dims is None:
        return
    text_bb = _text_bbox_estimate(text_node)
    text_w = text_bb.max[0] - text_bb.min[0]
    text_h = text_bb.max[1] - text_bb.min[1]
    face_w, face_h = face_dims
    if text_w > face_w or text_h > face_h:
        loc = f" (at {source_location})" if source_location else ""
        _log.warning(
            "add_text: label %r estimated %.1fx%.1f mm overflows face "
            "%.1fx%.1f mm%s",
            label, text_w, text_h, face_w, face_h, loc,
        )


# --- Geometry: rotate +Z to a target normal ---


def _rotate_z_to(child, target_normal, loc):
    """Rotate ``child`` so its local +Z axis points along ``target_normal``.

    The text prism comes out of ``linear_extrude`` aligned with +Z (from
    Z=0 at the base to Z=h at the top). To place it on a surface, +Z
    must align with the outward direction of the prism's growth — that's
    the surface normal for raised text and the inward normal for inset.
    """
    z = (0.0, 0.0, 1.0)
    n = target_normal

    d = z[0] * n[0] + z[1] * n[1] + z[2] * n[2]
    cross = (
        z[1] * n[2] - z[2] * n[1],
        z[2] * n[0] - z[0] * n[2],
        z[0] * n[1] - z[1] * n[0],
    )
    cross_len = math.sqrt(cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2)

    if cross_len > 1e-10:
        angle_deg = math.degrees(math.acos(max(-1.0, min(1.0, d))))
        return Rotate(a=angle_deg, v=cross, child=child, source_location=loc)

    if d > 0.5:
        # Already aligned with +Z; no rotation needed.
        return child

    # d ≈ -1: 180° flip around +X (any axis perpendicular to Z works).
    return Rotate(a=180.0, v=(1.0, 0.0, 0.0), child=child, source_location=loc)


# --- The transform itself ---


# --- Cylindrical placement helpers ---


def _resolve_meridian(meridian) -> float:
    """Convert a string face name or numeric degrees CCW to radians.

    Thin alias for ``resolve_angle_to_radians`` with the historical
    ``param_name="meridian"`` so error messages stay backward-compatible
    for ``add_text`` users.
    """
    from scadwright.anchor import resolve_angle_to_radians
    return resolve_angle_to_radians(
        meridian, context_name="add_text", param_name="meridian",
    )


def _rotate_around_axis(vec, angle_rad, axis):
    """Rodrigues' rotation: rotate ``vec`` by ``angle_rad`` around unit ``axis``."""
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    ax, ay, az = axis
    vx, vy, vz = vec
    cross_x = ay * vz - az * vy
    cross_y = az * vx - ax * vz
    cross_z = ax * vy - ay * vx
    dot = ax * vx + ay * vy + az * vz
    return (
        vx * c + cross_x * s + ax * dot * (1 - c),
        vy * c + cross_y * s + ay * dot * (1 - c),
        vz * c + cross_z * s + az * dot * (1 - c),
    )


def _orient_glyph_matrix(tangent, axial, radial) -> Matrix:
    """Build a 4x4 multmatrix mapping local +X→tangent, +Y→axial, +Z→radial."""
    return Matrix((
        (tangent[0], axial[0], radial[0], 0.0),
        (tangent[1], axial[1], radial[1], 0.0),
        (tangent[2], axial[2], radial[2], 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))


def _place_wrapped(
    host_node,
    anchor,
    lines,
    font_size,
    relief,
    meridian,
    at_z,
    halign,
    valign,
    line_spacing,
    text_orient,
    text_dir,
    rotate_glyphs,
    flip,
    text_kwargs,
    loc,
):
    """Per-glyph wrap on a cylindrical or conical surface.

    For cylindrical: radius is constant per line; ``text_orient`` doesn't
    apply. For conical: radius varies with axial position, so each line
    has its own ``local_radius``; ``text_orient`` controls whether glyphs
    stay vertical along the axis (``"axial"``, default — most legible)
    or tilt with the cone's slant (``"slant"`` — surface-conforming).

    ``text_dir`` chooses how the line lays on the surface — ``"circumferential"``
    (default, line wraps around the axis) or ``"axial"`` (line runs along
    the surface axis, glyphs at successive at_z values). ``rotate_glyphs``
    rotates each glyph 90° in the surface tangent plane; ``flip`` rotates
    the layout (line direction + glyph orientation) 180°.

    Multi-line: with text_dir="circumferential", lines are stacked along
    the axis (line 0 at higher axial position). text_dir="axial" with
    multi-line is rejected upstream.
    """
    if not any(line for line in lines):
        raise ValidationError("add_text: label is empty.")

    axis = anchor.surface_param("axis")
    if axis is None:
        raise ValidationError("add_text: anchor missing 'axis' surface_param.")

    # Inner walls: see _place_wrapped header doc — flip sign so
    # outward_from_axis_unit always points away from axis.
    inner = bool(anchor.surface_param("inner", default=False))
    s_outward = -1.0 if inner else 1.0
    outward_from_axis_unit = (
        s_outward * anchor.normal[0],
        s_outward * anchor.normal[1],
        s_outward * anchor.normal[2],
    )

    is_conical = anchor.kind == "conical"
    is_meridional = anchor.kind == "meridional"
    is_curved_axially = is_conical or is_meridional
    if is_conical:
        r1 = anchor.surface_param("r1")
        r2 = anchor.surface_param("r2")
        length = anchor.surface_param("length")
        if r1 is None or r2 is None or length is None:
            raise ValidationError(
                "add_text: conical anchor missing 'r1', 'r2', or 'length' "
                "surface_params."
            )
        r_mid = (r1 + r2) / 2.0
        slope = (r2 - r1) / length if length > 0 else 0.0
        meridian_r = mid_r_param = meridian_s_param = None
        merid_length = None
    elif is_meridional:
        meridian_r = anchor.surface_param("meridian_r")
        mid_r_param = anchor.surface_param("mid_r")
        meridian_s_param = anchor.surface_param("meridian_s")
        merid_length = anchor.surface_param("length")
        if (meridian_r is None or mid_r_param is None
                or meridian_s_param is None or merid_length is None):
            raise ValidationError(
                "add_text: meridional anchor missing 'meridian_r', 'mid_r', "
                "'meridian_s', or 'length' surface_params."
            )
        r_mid = mid_r_param
        slope = 0.0  # unused; per-line slant is computed from the arc
    else:
        radius = anchor.surface_param("radius")
        if radius is None:
            raise ValidationError(
                "add_text: cylindrical anchor missing 'radius' surface_param."
            )
        r_mid = radius
        slope = 0.0
        meridian_r = mid_r_param = meridian_s_param = None
        merid_length = None

    base_meridian_rad = _resolve_meridian(meridian) if meridian is not None else 0.0
    base_axial_offset = float(at_z) if at_z is not None else 0.0

    raised = relief > 0
    abs_relief = abs(relief)
    eps = _PLACEMENT_EPS
    extrude_h = abs_relief + (eps if raised else 2 * eps)

    # Axis origin uses the mid-wall radius of the host (constant across lines)
    # so the per-line glyph positions all reference the same centerline.
    if is_meridional:
        # The reference position at the equator IS at radius mid_r along
        # the +X meridian, so position - mid_r * outward gives the equator
        # axis point — same calculation as cylindrical/conical. (We could
        # read axis_origin straight from surface_params; deriving keeps
        # the code uniform and matches cylindrical's pattern.)
        axis_origin = (
            anchor.position[0] - r_mid * outward_from_axis_unit[0],
            anchor.position[1] - r_mid * outward_from_axis_unit[1],
            anchor.position[2] - r_mid * outward_from_axis_unit[2],
        )
    else:
        axis_origin = (
            anchor.position[0] - r_mid * outward_from_axis_unit[0],
            anchor.position[1] - r_mid * outward_from_axis_unit[1],
            anchor.position[2] - r_mid * outward_from_axis_unit[2],
        )

    # Conical slant components are global (cone slope is line-independent).
    # Cylindrical: slope = 0 → trivial values. Meridional: recomputed per-line.
    slant_norm = math.sqrt(slope * slope + 1.0)
    slant_outward_component = slope / slant_norm
    slant_axial_component = 1.0 / slant_norm

    # Closure that returns (radius, slant_outward, slant_axial) at any at_z.
    # Used by axial-line text where each glyph sits at a different at_z and
    # therefore (on conical/meridional surfaces) at a different local
    # radius. Cylindrical: constant. Conical: linear in at_z. Meridional:
    # arc-based via ``_meridian_arc_at``.
    if is_conical:
        def compute_geom_at(at_z_local):
            return (r_mid + at_z_local * slope,
                    slant_outward_component,
                    slant_axial_component)
    elif is_meridional:
        from scadwright.ast.placement import _meridian_arc_at as _arc_at
        def compute_geom_at(at_z_local):
            return _arc_at(at_z_local, meridian_r, mid_r_param, meridian_s_param)
    else:  # cylindrical
        def compute_geom_at(at_z_local):
            return r_mid, 0.0, 1.0

    # Length of the curved wall along the axis (cylindrical/conical) or arc
    # (meridional). Used by ``_emit_wrap_line`` for axial-extent overflow
    # warnings; ``None`` when the anchor doesn't carry it.
    if is_meridional:
        surface_length = merid_length
    elif is_conical:
        surface_length = anchor.surface_param("length")
    else:
        surface_length = anchor.surface_param("length")

    # Per-line axial offsets. Single-line collapses to [0.0] so behavior
    # is identical to the previous single-string path.
    if len(lines) == 1:
        line_y_offsets = [0.0]
    else:
        line_y_offsets = _line_y_offsets(len(lines), font_size, line_spacing, valign)

    # Multi-line block overflow check for axial mode: total circumferential
    # span (n-1)*line_spacing*font_size must be < 2π * line_radius.
    if text_dir == "axial" and len(lines) > 1:
        center_radius, _, _ = compute_geom_at(base_axial_offset)
        block_circum_extent = (len(lines) - 1) * line_spacing * font_size
        if block_circum_extent >= 2 * math.pi * center_radius:
            loc_str = f" (at {loc})" if loc else ""
            _log.warning(
                "add_text: %d axial-line block spans %.1f mm circumferentially, "
                "wrapping past the cylinder at radius %.2f mm — lines will overlap%s",
                len(lines), block_circum_extent, center_radius, loc_str,
            )

    label_repr = "\n".join(lines)
    glyph_nodes = []
    for line_idx, (line, line_y) in enumerate(zip(lines, line_y_offsets)):
        if not line:
            continue

        # In circumferential mode, line_y is an axial offset (lines stack
        # along the axis). In axial mode, line_y is a tangent-mm offset
        # (lines stack circumferentially) and gets converted to an angular
        # offset using the line-center radius.
        if text_dir == "axial":
            line_at_z = base_axial_offset
        else:
            line_at_z = base_axial_offset + line_y

        # Per-line local radius and slant components — at the line center.
        if is_conical:
            line_radius = r_mid + line_at_z * slope
            line_slant_outward = slant_outward_component
            line_slant_axial = slant_axial_component
            if line_radius <= 0:
                raise ValidationError(
                    f"add_text: conical surface radius at at_z={line_at_z:.3f} "
                    f"(line {line_idx}) is {line_radius:.3f} (cone tip or "
                    f"beyond). Pick an at_z / line_spacing where the radius "
                    f"is positive for every line."
                )
        elif is_meridional:
            from scadwright.ast.placement import _meridian_arc_at
            if abs(line_at_z) > merid_length / 2.0 + 1e-9:
                raise ValidationError(
                    f"add_text: meridional at_z={line_at_z:.3f} "
                    f"(line {line_idx}) is outside the wall extent "
                    f"[-{merid_length/2}, {merid_length/2}]."
                )
            try:
                line_radius, line_slant_outward, line_slant_axial = (
                    _meridian_arc_at(line_at_z, meridian_r, mid_r_param, meridian_s_param)
                )
            except ValueError as exc:
                raise ValidationError(f"add_text: {exc}") from exc
            if line_radius <= 0:
                raise ValidationError(
                    f"add_text: meridional surface radius at at_z="
                    f"{line_at_z:.3f} (line {line_idx}) is "
                    f"{line_radius:.3f} (wall pinches to the axis)."
                )
        else:
            line_radius = r_mid
            line_slant_outward = slant_outward_component
            line_slant_axial = slant_axial_component

        if is_curved_axially and line_radius < 0.5 * font_size:
            loc_str = f" (at {loc})" if loc else ""
            _log.warning(
                "add_text: %s local radius %.2f mm at at_z=%.2f "
                "(line %d) is small relative to font_size=%.1f — "
                "glyphs may overlap%s",
                anchor.kind, line_radius, line_at_z, line_idx, font_size, loc_str,
            )

        # Per-line meridian: in axial mode, lines stack circumferentially
        # so line_y becomes an angular offset (radians = mm-of-arc / radius).
        if text_dir == "axial":
            line_meridian_rad = base_meridian_rad + line_y / line_radius
        else:
            line_meridian_rad = base_meridian_rad

        glyph_nodes.extend(_emit_wrap_line(
            line=line,
            line_radius=line_radius,
            line_at_z=line_at_z,
            font_size=font_size,
            extrude_h=extrude_h,
            eps=eps,
            abs_relief=abs_relief,
            raised=raised,
            base_meridian_rad=line_meridian_rad,
            halign=halign,
            axis=axis,
            anchor_normal=anchor.normal,
            axis_origin=axis_origin,
            s_outward=s_outward,
            is_conical=is_curved_axially,  # "use slant orientation"
            text_orient=text_orient,
            text_dir=text_dir,
            rotate_glyphs=rotate_glyphs,
            flip=flip,
            slant_outward_component=line_slant_outward,
            slant_axial_component=line_slant_axial,
            compute_geom_at=compute_geom_at,
            surface_length=surface_length,
            text_kwargs=text_kwargs,
            label_repr=label_repr,
            loc=loc,
        ))

    if raised:
        return union(host_node, *glyph_nodes)
    return difference(host_node, *glyph_nodes)


def _emit_wrap_line(
    *,
    line, line_radius, line_at_z,
    font_size, extrude_h, eps, abs_relief, raised,
    base_meridian_rad, halign,
    axis, anchor_normal, axis_origin, s_outward,
    is_conical, text_orient,
    text_dir, rotate_glyphs, flip,
    slant_outward_component, slant_axial_component,
    compute_geom_at, surface_length,
    text_kwargs, label_repr, loc,
):
    """Emit per-glyph nodes for one line wrapped around a cylindrical, conical,
    or meridional surface. Returns a list of placed glyph nodes (caller
    assembles them into a union or difference).

    ``text_dir`` chooses whether the line advances around the axis
    (``"circumferential"``) or along it (``"axial"``). On axial mode with a
    curved-axially surface, the per-glyph radius and slant components are
    recomputed via ``compute_geom_at`` (which closes over the surface kind
    and its parameters in the caller).

    ``rotate_glyphs`` and ``flip`` together select one of 4 in-tangent-
    plane glyph orientations:

        rg=F, flip=F → glyph right=+e1, up=+e2  (default)
        rg=F, flip=T → glyph right=-e1, up=-e2  (180°)
        rg=T, flip=F → glyph right=-e2, up=+e1  (90° CCW)
        rg=T, flip=T → glyph right=+e2, up=-e1  (90° CW)

    where (e1, e2) = (surface tangent, surface "up" direction). The "up"
    direction is the surface axis in the simple case and the slant axis
    when text_orient="slant" on a conical or meridional wall.

    Per-glyph emit always uses ``halign="left"`` and ``valign="baseline"``,
    pre-translated by ``-advance/2`` along local 2D-x so each glyph's
    advance midpoint sits at the placement origin. The caller's halign
    drives where that line of advance midpoints sits relative to
    ``base_meridian_rad`` (or ``line_at_z`` in axial mode); the caller's
    valign was applied at the line-stacking stage (see ``_line_y_offsets``)
    and doesn't reach here.

    Centering on the advance midpoint (rather than the left edge) keeps
    the orientation matrix evaluated at the glyph's visual centre, which
    matters most for short labels where evaluating at the left edge
    leaves the whole glyph noticeably rotated.
    """
    advances_mm = get_advances(
        tuple(line),
        font=text_kwargs.get("font"),
        size=font_size,
        spacing=text_kwargs.get("spacing", 1.0),
    )

    # Per-char offset list and overflow check, branching on text_dir.
    if text_dir == "circumferential":
        total_mm = sum(advances_mm)
        total_arc_rad = total_mm / line_radius
        if total_arc_rad > 2 * math.pi:
            loc_str = f" (at {loc})" if loc else ""
            _log.warning(
                "add_text: line %r wraps %.0f%% of the surface at radius "
                "%.2f mm — glyphs will overlap%s",
                line, 100 * total_arc_rad / (2 * math.pi), line_radius, loc_str,
            )
        # Per-glyph CENTER position (mm, from base_meridian). Each glyph's
        # advance midpoint sits here; the per-glyph 2D shape is shifted
        # by -advance/2 so that midpoint coincides with the placement origin.
        # halign decides how the cumulative line spans relative to base_meridian.
        sign = -1.0 if flip else 1.0
        cum = [0.0]
        for a in advances_mm[:-1]:
            cum.append(cum[-1] + a)
        if halign == "left":
            centers_mm = [c + a / 2.0 for c, a in zip(cum, advances_mm)]
        elif halign == "right":
            centers_mm = [c + a / 2.0 - total_mm for c, a in zip(cum, advances_mm)]
        else:
            centers_mm = [c + a / 2.0 - total_mm / 2.0 for c, a in zip(cum, advances_mm)]
        scalar_offsets = [m / line_radius * sign for m in centers_mm]
        char_advances = [(o, 0.0) for o in scalar_offsets]
    else:  # text_dir == "axial"
        # On slanted surfaces with text_orient="slant", scale per-glyph
        # advance by the line-center slant_axial_component so spacing
        # measures arc-length along the slant (uniform visual spacing on
        # a tapered surface; using the line-center value uniformly is the
        # same approximation as before).
        if (is_conical or anchor_normal is None) and text_orient == "slant":
            axial_advances = [a * slant_axial_component for a in advances_mm]
        else:
            axial_advances = list(advances_mm)
        total_mm = sum(axial_advances)
        cum = [0.0]
        for a in axial_advances[:-1]:
            cum.append(cum[-1] + a)
        # Default axial direction: -axis (top-to-bottom on a vertical
        # cylinder, char 0 at the top). flip negates.
        sign = 1.0 if flip else -1.0
        if halign == "left":
            centers_mm = [c + a / 2.0 for c, a in zip(cum, axial_advances)]
        elif halign == "right":
            centers_mm = [c + a / 2.0 - total_mm for c, a in zip(cum, axial_advances)]
        else:
            centers_mm = [c + a / 2.0 - total_mm / 2.0 for c, a in zip(cum, axial_advances)]
        scalar_offsets = [m * sign for m in centers_mm]
        char_advances = [(0.0, o) for o in scalar_offsets]
        # Axial-extent overflow check: warn if the total axial extent
        # plus the line center's offset pushes any glyph past the wall.
        if surface_length is not None:
            char_at_zs = [line_at_z + o for o in scalar_offsets]
            half_len = surface_length / 2.0
            # Use the widest per-glyph advance as the half-width at each end.
            edge_pad = max(advances_mm) / 2.0 if advances_mm else 0.0
            min_at_z = min(char_at_zs) - edge_pad
            max_at_z = max(char_at_zs) + edge_pad
            if min_at_z < -half_len or max_at_z > half_len:
                loc_str = f" (at {loc})" if loc else ""
                _log.warning(
                    "add_text: line %r axial extent [%.2f, %.2f] exceeds "
                    "wall extent [%.2f, %.2f]%s",
                    line, min_at_z, max_at_z, -half_len, half_len, loc_str,
                )

    out = []
    for char, glyph_advance_mm, (theta_off, at_z_off) in zip(line, advances_mm, char_advances):
        theta = base_meridian_rad + theta_off
        char_at_z = line_at_z + at_z_off

        # Per-glyph geometry. For text_dir="circumferential", every glyph
        # on a line shares (line_radius, line_slant_*) — passed in. For
        # text_dir="axial" with curved-axially surfaces, recompute per glyph.
        if text_dir == "axial" and is_conical:
            char_radius, char_slant_o, char_slant_a = compute_geom_at(char_at_z)
            if char_radius <= 0:
                raise ValidationError(
                    f"add_text: surface radius at at_z={char_at_z:.3f} "
                    f"(char {char!r}) is {char_radius:.3f} (wall pinches "
                    f"to the axis or beyond cone tip)."
                )
        else:
            char_radius = line_radius
            char_slant_o = slant_outward_component
            char_slant_a = slant_axial_component

        radial = _rotate_around_axis(anchor_normal, theta, axis)
        outward_at_theta = (
            s_outward * radial[0],
            s_outward * radial[1],
            s_outward * radial[2],
        )
        tangent = (
            axis[1] * radial[2] - axis[2] * radial[1],
            axis[2] * radial[0] - axis[0] * radial[2],
            axis[0] * radial[1] - axis[1] * radial[0],
        )

        if is_conical and text_orient == "slant":
            slant = (
                char_slant_o * outward_at_theta[0] + char_slant_a * axis[0],
                char_slant_o * outward_at_theta[1] + char_slant_a * axis[1],
                char_slant_o * outward_at_theta[2] + char_slant_a * axis[2],
            )
            surface_normal = (
                tangent[1] * slant[2] - tangent[2] * slant[1],
                tangent[2] * slant[0] - tangent[0] * slant[2],
                tangent[0] * slant[1] - tangent[1] * slant[0],
            )
            e2 = slant
            extrude_dir = surface_normal
        else:
            e2 = axis
            extrude_dir = radial

        e1 = tangent

        # 8-combo orientation: (rotate_glyphs, flip) → (g_right, g_up).
        # g_right gets glyph local +X; g_up gets glyph local +Y.
        if not rotate_glyphs and not flip:
            g_right, g_up = e1, e2
        elif not rotate_glyphs and flip:
            g_right = (-e1[0], -e1[1], -e1[2])
            g_up = (-e2[0], -e2[1], -e2[2])
        elif rotate_glyphs and not flip:
            g_right = (-e2[0], -e2[1], -e2[2])
            g_up = e1
        else:  # rotate_glyphs and flip
            g_right = e2
            g_up = (-e1[0], -e1[1], -e1[2])

        # Per-glyph emit always uses halign="left" / valign="baseline" so
        # the glyph's left edge sits at 2D x=0 and its baseline at y=0,
        # then we shift by -advance/2 in 2D so the advance midpoint sits
        # at the placement origin (the center of the glyph's allotted arc
        # range). Baseline alignment keeps mixed-height glyphs (g, t, i)
        # on a common line — per-glyph "center" centers each glyph on its
        # own bbox, which has different heights per glyph and produces
        # visible vertical jitter.
        glyph_2d = _text_factory(
            char,
            size=font_size,
            font=text_kwargs.get("font"),
            halign="left",
            valign="baseline",
            spacing=text_kwargs.get("spacing", 1.0),
            direction=text_kwargs.get("direction", "ltr"),
            language=text_kwargs.get("language", "en"),
            script=text_kwargs.get("script", "latin"),
            fn=text_kwargs.get("fn"),
            fa=text_kwargs.get("fa"),
            fs=text_kwargs.get("fs"),
        )
        glyph_2d_centered = Translate(
            v=(-glyph_advance_mm / 2.0, 0.0, 0.0),
            child=glyph_2d,
            source_location=loc,
        )
        extruded = linear_extrude(glyph_2d_centered, height=extrude_h)
        oriented = MultMatrix(
            matrix=_orient_glyph_matrix(g_right, g_up, extrude_dir),
            child=extruded,
            source_location=loc,
        )

        d = s_outward * char_radius - eps - (abs_relief if not raised else 0.0)
        glyph_pos = (
            axis_origin[0] + d * radial[0] + char_at_z * axis[0],
            axis_origin[1] + d * radial[1] + char_at_z * axis[1],
            axis_origin[2] + d * radial[2] + char_at_z * axis[2],
        )
        out.append(Translate(v=glyph_pos, child=oriented, source_location=loc))
    return out


def _place_on_rim(
    host_node,
    anchor,
    lines,
    font_size,
    relief,
    meridian,
    at_radial,
    halign,
    valign,
    line_spacing,
    text_kwargs,
    loc,
):
    """Per-glyph wrap on a circular planar rim (Cylinder/Tube/Funnel top
    or bottom). The rim's plane is perpendicular to ``anchor.normal``;
    each line of text is laid out along its own circle centered on the
    rim center.

    Multi-line: lines stack radially, with line 0 at the OUTERMOST
    circle (largest radius) and subsequent lines on progressively
    smaller circles. The user's ``valign`` controls block placement
    relative to the default rim path radius.
    """
    if not any(line for line in lines):
        raise ValidationError("add_text: label is empty.")

    rim_radius = anchor.surface_param("rim_radius")
    if rim_radius is None or rim_radius <= 0:
        raise ValidationError(
            "add_text: rim anchor missing 'rim_radius' surface_param "
            "(or radius is non-positive)."
        )

    face_normal = anchor.normal
    rim_center = anchor.position

    # Default at_radial: leave a font_size margin inside the rim so a
    # single line of text fits. For multi-line, the outermost line uses
    # this default; inner lines are placed at smaller radii by line
    # offsets.
    if at_radial is None:
        path_radius = max(rim_radius - font_size, font_size * 0.5)
    else:
        path_radius = float(at_radial)
        if path_radius <= 0:
            raise ValidationError(
                f"add_text: at_radial must be positive, got {at_radial!r}."
            )
        if path_radius > rim_radius:
            loc_str = f" (at {loc})" if loc else ""
            _log.warning(
                "add_text: at_radial=%.2f mm exceeds rim_radius=%.2f mm — "
                "text path is outside the rim%s",
                path_radius, rim_radius, loc_str,
            )

    # Prefer meridian_zero / axis from surface_params so meridian=N
    # follows the cylinder's local frame (transforms with the host),
    # consistent with attach(rim, angle=N). Fall back to deriving from
    # face_normal for ad-hoc rim Anchors that lack the surface params.
    meridian_zero = anchor.surface_param("meridian_zero")
    rotation_axis = anchor.surface_param("axis")
    if meridian_zero is None or rotation_axis is None:
        u_axis, _v_axis = _face_tangent_frame(None, face_normal)
        rotation_axis = face_normal
    else:
        u_axis = meridian_zero
    base_meridian_rad = _resolve_meridian(meridian) if meridian is not None else 0.0

    raised = relief > 0
    abs_relief = abs(relief)
    eps = _PLACEMENT_EPS
    extrude_h = abs_relief + (eps if raised else 2 * eps)

    if len(lines) == 1:
        line_y_offsets = [0.0]
    else:
        line_y_offsets = _line_y_offsets(len(lines), font_size, line_spacing, valign)

    label_repr = "\n".join(lines)
    glyph_nodes = []
    for line_idx, (line, line_y) in enumerate(zip(lines, line_y_offsets)):
        if not line:
            continue
        # Line 0 (top of block) maps to LARGER radius on the rim. y > 0
        # for upper lines, so add y to path_radius to push the outermost
        # line outward.
        line_path_radius = path_radius + line_y
        if line_path_radius <= 0:
            raise ValidationError(
                f"add_text: rim path radius for line {line_idx} would be "
                f"{line_path_radius:.3f} mm (non-positive). Increase "
                f"at_radial or reduce line_spacing/font_size."
            )
        if line_path_radius > rim_radius and at_radial is None:
            loc_str = f" (at {loc})" if loc else ""
            _log.warning(
                "add_text: rim path radius for line %d is %.2f mm, "
                "exceeding rim_radius=%.2f mm — that line is outside "
                "the rim%s",
                line_idx, line_path_radius, rim_radius, loc_str,
            )

        glyph_nodes.extend(_emit_rim_line(
            line=line,
            line_path_radius=line_path_radius,
            font_size=font_size,
            extrude_h=extrude_h,
            eps=eps,
            raised=raised,
            base_meridian_rad=base_meridian_rad,
            halign=halign,
            face_normal=face_normal,
            rim_center=rim_center,
            u_axis=u_axis,
            rotation_axis=rotation_axis,
            text_kwargs=text_kwargs,
            label_repr=label_repr,
            loc=loc,
        ))

    if raised:
        return union(host_node, *glyph_nodes)
    return difference(host_node, *glyph_nodes)


def _emit_rim_line(
    *,
    line, line_path_radius,
    font_size, extrude_h, eps, raised,
    base_meridian_rad, halign,
    face_normal, rim_center, u_axis, rotation_axis,
    text_kwargs, label_repr, loc,
):
    """Emit per-glyph nodes for one rim-arc line at a given path radius.

    ``rotation_axis`` is the cylinder's central axis (the rim
    anchor's ``surface_params["axis"]``), used to spin glyphs around
    the rim from ``u_axis`` (the +X-meridian reference). ``face_normal``
    is the rim's outward normal (perpendicular to the rim plane); used
    for the glyph "right" direction (tangent = face_normal × radial)
    and for the small offset that lifts the glyph above or sinks it
    below the rim surface.

    Per-glyph emit always uses ``halign="left"`` and ``valign="baseline"``
    (see ``_emit_wrap_line`` for the same rationale).
    """
    advances_mm = get_advances(
        tuple(line),
        font=text_kwargs.get("font"),
        size=font_size,
        spacing=text_kwargs.get("spacing", 1.0),
    )
    total_mm = sum(advances_mm)
    total_arc_rad = total_mm / line_path_radius
    if total_arc_rad > 2 * math.pi:
        loc_str = f" (at {loc})" if loc else ""
        _log.warning(
            "add_text: line %r wraps %.0f%% of the rim circle at radius "
            "%.2f mm — glyphs will overlap%s",
            line, 100 * total_arc_rad / (2 * math.pi), line_path_radius, loc_str,
        )

    cum = [0.0]
    for a in advances_mm[:-1]:
        cum.append(cum[-1] + a)
    # Per-glyph CENTER position (mm, from base_meridian along the arc).
    # See ``_emit_wrap_line`` for the rationale: orient each glyph at its
    # advance midpoint and pre-translate the 2D shape by -advance/2.
    if halign == "left":
        centers_mm = [c + a / 2.0 for c, a in zip(cum, advances_mm)]
    elif halign == "right":
        centers_mm = [c + a / 2.0 - total_mm for c, a in zip(cum, advances_mm)]
    else:
        centers_mm = [c + a / 2.0 - total_mm / 2.0 for c, a in zip(cum, advances_mm)]
    offsets = [m / line_path_radius for m in centers_mm]

    out = []
    for char, glyph_advance_mm, offset_from_meridian in zip(line, advances_mm, offsets):
        theta = base_meridian_rad + offset_from_meridian
        radial = _rotate_around_axis(u_axis, theta, rotation_axis)
        tangent = (
            face_normal[1] * radial[2] - face_normal[2] * radial[1],
            face_normal[2] * radial[0] - face_normal[0] * radial[2],
            face_normal[0] * radial[1] - face_normal[1] * radial[0],
        )

        glyph_2d = _text_factory(
            char,
            size=font_size,
            font=text_kwargs.get("font"),
            halign="left",
            valign="baseline",
            spacing=text_kwargs.get("spacing", 1.0),
            direction=text_kwargs.get("direction", "ltr"),
            language=text_kwargs.get("language", "en"),
            script=text_kwargs.get("script", "latin"),
            fn=text_kwargs.get("fn"),
            fa=text_kwargs.get("fa"),
            fs=text_kwargs.get("fs"),
        )
        glyph_2d_centered = Translate(
            v=(-glyph_advance_mm / 2.0, 0.0, 0.0),
            child=glyph_2d,
            source_location=loc,
        )
        extruded = linear_extrude(glyph_2d_centered, height=extrude_h)
        oriented = MultMatrix(
            matrix=_orient_glyph_matrix(tangent, radial, face_normal),
            child=extruded,
            source_location=loc,
        )

        normal_shift = -eps if raised else eps
        glyph_pos = (
            rim_center[0] + line_path_radius * radial[0] + normal_shift * face_normal[0],
            rim_center[1] + line_path_radius * radial[1] + normal_shift * face_normal[1],
            rim_center[2] + line_path_radius * radial[2] + normal_shift * face_normal[2],
        )
        out.append(Translate(v=glyph_pos, child=oriented, source_location=loc))
    return out


# --- The transform itself ---


@transform("add_text", inline=True, decoration=True)
def add_text(
    node,
    *,
    label,
    relief,
    font_size,
    on=None,
    at=None,
    normal=None,
    meridian=None,
    at_z=None,
    at_radial=None,
    text_curvature=None,
    text_orient="axial",
    text_dir="circumferential",
    rotate_glyphs=False,
    flip=False,
    font=None,
    halign="center",
    valign=_UNSET,
    spacing=1.0,
    line_spacing=1.2,
    direction="ltr",
    language="en",
    script="latin",
    fn=None,
    fa=None,
    fs=None,
):
    """Add raised or inset text to a host shape's surface.

    ``relief`` is signed: positive raises the text outward by that
    distance, negative cuts it that deep into the host. The ``on=``,
    ``at=``, and ``normal=`` kwargs choose the placement. ``meridian=``
    and ``at_z=`` apply only on cylindrical and conical surfaces (the
    angular position around the axis and the axial offset from
    mid-wall). ``text_orient=`` controls glyph orientation on conical
    surfaces (``"axial"`` keeps glyphs vertical; ``"slant"`` tilts them
    with the cone). See ``docs/add_text.md`` for the full reference.
    """
    if not isinstance(label, str):
        raise ValidationError(
            f"add_text: `label=` must be a string, got {type(label).__name__}."
        )
    if not isinstance(font_size, (int, float)) or isinstance(font_size, bool):
        raise ValidationError(
            f"add_text: `font_size=` must be a positive number, got {font_size!r}."
        )
    if font_size <= 0:
        raise ValidationError(
            f"add_text: `font_size=` must be a positive number, got {font_size!r}."
        )
    if not isinstance(relief, (int, float)) or isinstance(relief, bool):
        raise ValidationError(
            f"add_text: `relief=` must be a number, got {type(relief).__name__}."
        )
    if relief == 0:
        raise ValidationError(
            "add_text: relief=0 (decal mode) is not yet supported. Use a "
            "positive value for raised text or a negative value for inset."
        )
    if not isinstance(line_spacing, (int, float)) or isinstance(line_spacing, bool):
        raise ValidationError(
            f"add_text: line_spacing must be a positive number, got "
            f"{line_spacing!r}."
        )
    if line_spacing <= 0:
        raise ValidationError(
            f"add_text: line_spacing must be positive, got {line_spacing!r}."
        )

    # Multi-line: only enter the multi-line code path when the label
    # contains an explicit newline. Single-line behavior is unchanged so
    # all existing single-line goldens stay byte-identical.
    lines = _split_lines(label)
    is_multiline = len(lines) > 1
    if is_multiline:
        if direction in ("ttb", "btt"):
            raise ValidationError(
                f"add_text: multi-line labels (containing '\\n') do not "
                f"support direction={direction!r}; column-writing is "
                f"single-line only. Drop the newline or change direction."
            )
        if not any(line for line in lines):
            raise ValidationError(
                "add_text: label contains only newlines — must have at "
                "least one non-empty line."
            )

    loc = SourceLocation.from_caller()

    # 1. Resolve placement into (Anchor, face_dims_or_None).
    placement_anchor, face_dims = _resolve_placement(node, on, at, normal, loc)

    # Validate text_orient and text_curvature kwargs.
    if text_orient not in ("axial", "slant"):
        raise ValidationError(
            f"add_text: text_orient must be 'axial' or 'slant', got {text_orient!r}."
        )
    if text_curvature not in (None, "arc", "flat"):
        raise ValidationError(
            f"add_text: text_curvature must be 'arc', 'flat', or None "
            f"(default), got {text_curvature!r}."
        )
    if text_dir not in ("circumferential", "axial"):
        raise ValidationError(
            f"add_text: text_dir must be 'circumferential' or 'axial', "
            f"got {text_dir!r}."
        )
    if not isinstance(rotate_glyphs, bool):
        raise ValidationError(
            f"add_text: rotate_glyphs must be a bool, got {type(rotate_glyphs).__name__}."
        )
    if not isinstance(flip, bool):
        raise ValidationError(
            f"add_text: flip must be a bool, got {type(flip).__name__}."
        )

    # text_dir / rotate_glyphs / flip apply only to curved walls
    # (cylindrical / conical / meridional). On planar surfaces — flat
    # faces or rim anchors — pass them and they'd silently no-op, which
    # is the worst kind of failure mode. Reject with a clear error.
    if placement_anchor.kind not in ("cylindrical", "conical", "meridional"):
        if text_dir == "axial":
            raise ValidationError(
                f"add_text: text_dir='axial' requires a cylindrical, conical, "
                f"or meridional anchor (a curved wall with an axis to follow); "
                f"got kind={placement_anchor.kind!r}. On a planar surface, "
                f"rotate the host instead."
            )
        if rotate_glyphs:
            raise ValidationError(
                f"add_text: rotate_glyphs=True applies only to curved walls "
                f"(cylindrical / conical / meridional); got "
                f"kind={placement_anchor.kind!r}. On a planar surface, "
                f"rotate the host with .rotate([0, 0, 90]) instead. On a rim, "
                f"this combination isn't supported yet."
            )
        if flip:
            raise ValidationError(
                f"add_text: flip=True applies only to curved walls "
                f"(cylindrical / conical / meridional); got "
                f"kind={placement_anchor.kind!r}. On a planar or rim anchor, "
                f"flip the host with .mirror() or use the existing halign / "
                f"meridian kwargs to reverse reading order."
            )

    # Resolve `valign`. Curved walls and rim arcs emit one ``text()`` per
    # glyph, where ``valign="center"`` centers each glyph's bbox on the
    # baseline — but a tall ``t``, an ``i`` whose ink starts above zero,
    # and a ``g`` with a descender all have different bbox heights, so
    # per-glyph centering produces visible vertical jitter. The right
    # answer is per-glyph baseline alignment. Reject explicit "center" on
    # those hosts, and resolve the unset default to "baseline" there.
    # Flat planar dispatch emits one whole-line ``text()`` so its
    # ``valign="center"`` keeps working correctly — that path's default
    # stays "center".
    if placement_anchor.kind in ("cylindrical", "conical", "meridional"):
        is_per_glyph = True
    elif placement_anchor.kind == "planar":
        _, is_per_glyph = _resolve_planar_curvature(placement_anchor, text_curvature)
    else:
        is_per_glyph = False
    if valign is _UNSET:
        valign = "baseline" if is_per_glyph else "center"
    elif is_per_glyph and valign == "center":
        raise ValidationError(
            "add_text: valign='center' is not supported on cylindrical, "
            "conical, meridional, or rim-arc placements. Per-glyph "
            "centering produces uneven baselines because each glyph's "
            "bbox is sized to its own ink (a 't' is tall, an 'i' starts "
            "above zero, a 'g' has a descender). Use 'baseline' "
            "(default), 'top', or 'bottom'."
        )

    # 2. Dispatch by surface kind.
    if placement_anchor.kind == "planar":
        # Resolve text_curvature for planar surfaces. Rim anchors (carrying
        # `rim_radius`) default to arc; flat faces default to straight.
        is_rim, use_arc = _resolve_planar_curvature(placement_anchor, text_curvature)

        # at_z is axial along a curved wall — never meaningful on a planar
        # rim or flat face.
        if at_z is not None:
            raise ValidationError(
                "add_text: `at_z` is the axial offset on a cylindrical or "
                "conical wall and does not apply to planar surfaces. "
                "On a rim, use `at_radial` for the path-circle radius."
            )
        # meridian only makes sense on the arc path (rotates the label
        # around the rim center); reject it on flat planar.
        if meridian is not None and not use_arc:
            raise ValidationError(
                "add_text: `meridian` applies on rim arc text and on "
                "cylindrical/conical walls; this is a flat planar surface."
            )

        if at_radial is not None and not use_arc:
            raise ValidationError(
                "add_text: `at_radial` only applies to arc-following rim "
                "text. Drop it, or pass text_curvature='arc' on a rim "
                "anchor."
            )

        if use_arc:
            text_kwargs = {
                "font": font,
                "spacing": spacing,
                "direction": direction,
                "language": language,
                "script": script,
                "fn": fn, "fa": fa, "fs": fs,
            }
            return _place_on_rim(
                node, placement_anchor,
                lines, font_size, relief,
                meridian, at_radial,
                halign, valign, line_spacing,
                text_kwargs, loc,
            )

        return _place_planar(
            node, placement_anchor, face_dims,
            lines, font_size, relief,
            font, halign, valign, spacing, line_spacing,
            direction, language, script,
            fn, fa, fs, loc,
        )

    if placement_anchor.kind in ("cylindrical", "conical", "meridional"):
        if text_curvature is not None:
            raise ValidationError(
                "add_text: text_curvature applies only to flat rim "
                "anchors (top/bottom of a Cylinder, Tube, or Funnel); "
                "side walls always wrap. Drop the kwarg."
            )
        if at_radial is not None:
            raise ValidationError(
                "add_text: `at_radial` is for rim arc text; on a "
                "cylindrical, conical, or meridional wall use `at_z` "
                "(axial offset)."
            )
        text_kwargs = {
            "font": font,
            "spacing": spacing,
            "direction": direction,
            "language": language,
            "script": script,
            "fn": fn, "fa": fa, "fs": fs,
        }
        return _place_wrapped(
            node, placement_anchor,
            lines, font_size, relief,
            meridian, at_z,
            halign, valign, line_spacing,
            text_orient,
            text_dir, rotate_glyphs, flip,
            text_kwargs, loc,
        )

    raise ValidationError(
        f"add_text: surface kind {placement_anchor.kind!r} is not supported. "
        f"Use a planar, cylindrical, conical, or meridional anchor."
    )


def _place_planar(
    node, placement_anchor, face_dims,
    lines, font_size, relief,
    font, halign, valign, spacing, line_spacing,
    direction, language, script,
    fn, fa, fs, loc,
):
    """Planar-surface placement. For multi-line, builds a 2D union of
    per-line ``text()`` nodes (each centered on its own y-coord); the
    block is positioned per ``valign``. Single-line goes straight to the
    classic single-text path so the emitted SCAD is unchanged.
    """
    label = "\n".join(lines)  # for warning messages
    if len(lines) == 1:
        text_2d = _text_factory(
            lines[0],
            size=font_size,
            font=font,
            halign=halign,
            valign=valign,
            spacing=spacing,
            direction=direction,
            language=language,
            script=script,
            fn=fn,
            fa=fa,
            fs=fs,
        )
    else:
        y_offsets = _line_y_offsets(len(lines), font_size, line_spacing, valign)
        line_nodes = []
        for line, y in zip(lines, y_offsets):
            if not line:
                continue  # empty line — keep its slot in spacing, emit nothing
            line_2d = _text_factory(
                line,
                size=font_size,
                font=font,
                halign=halign,
                valign="center",
                spacing=spacing,
                direction=direction,
                language=language,
                script=script,
                fn=fn,
                fa=fa,
                fs=fs,
            )
            line_nodes.append(line_2d.translate([0, y, 0]))
        if len(line_nodes) == 1:
            text_2d = line_nodes[0]
        else:
            text_2d = union(*line_nodes)

    _check_overflow_block(face_dims, lines, font_size, spacing, line_spacing, label, loc)

    raised = relief > 0
    abs_relief = abs(relief)
    eps = _PLACEMENT_EPS
    extrude_h = abs_relief + (eps if raised else 2 * eps)
    extruded = linear_extrude(text_2d, height=extrude_h)

    n = placement_anchor.normal
    target = n if raised else (-n[0], -n[1], -n[2])
    rotated = _rotate_z_to(extruded, target, loc)

    pos = placement_anchor.position
    if raised:
        shift = (pos[0] - eps * n[0], pos[1] - eps * n[1], pos[2] - eps * n[2])
    else:
        shift = (pos[0] + eps * n[0], pos[1] + eps * n[1], pos[2] + eps * n[2])
    placed = Translate(v=shift, child=rotated, source_location=loc)

    if raised:
        return union(node, placed)
    return difference(node, placed)
