"""``add_text`` decoration transform: place raised or inset text on a host.

Registered on import. Adds ``.add_text(label=..., relief=..., font_size=..., ...)``
to every Node. See ``docs/add_text.md`` for the user-facing reference.

This module ships planar and cylindrical surface support. Conical surfaces
land with conical-surface support.
"""

from __future__ import annotations

import math
from typing import Any

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
    """Convert a string face name or numeric degrees CCW to radians."""
    if isinstance(meridian, str):
        # Friendly aliases mapping to angle CCW from +X (the cylinder's
        # reference meridian).
        aliases = {
            "+x": 0.0,
            "rside": 0.0,
            "+y": 90.0,
            "back": 90.0,
            "-x": 180.0,
            "lside": 180.0,
            "-y": 270.0,
            "front": 270.0,
        }
        key = meridian.lower()
        if key not in aliases:
            raise ValidationError(
                f"add_text: meridian must be one of {sorted(aliases)} or a "
                f"numeric angle in degrees CCW from +X; got {meridian!r}."
            )
        return math.radians(aliases[key])
    if isinstance(meridian, bool):
        raise ValidationError(
            f"add_text: meridian must be a string or numeric, got bool."
        )
    if isinstance(meridian, (int, float)):
        return math.radians(float(meridian))
    raise ValidationError(
        f"add_text: meridian must be a string or numeric, got "
        f"{type(meridian).__name__}."
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
    text_kwargs,
    loc,
):
    """Per-glyph wrap on a cylindrical or conical surface.

    For cylindrical: radius is constant per line; ``text_orient`` doesn't
    apply. For conical: radius varies with axial position, so each line
    has its own ``local_radius``; ``text_orient`` controls whether glyphs
    stay vertical along the axis (``"axial"``, default — most legible)
    or tilt with the cone's slant (``"slant"`` — surface-conforming).

    Multi-line: lines are stacked along the cylinder/cone axis (line 0 at
    higher axial position).
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
    else:
        radius = anchor.surface_param("radius")
        if radius is None:
            raise ValidationError(
                "add_text: cylindrical anchor missing 'radius' surface_param."
            )
        r_mid = radius
        slope = 0.0

    base_meridian_rad = _resolve_meridian(meridian) if meridian is not None else 0.0
    base_axial_offset = float(at_z) if at_z is not None else 0.0

    raised = relief > 0
    abs_relief = abs(relief)
    eps = _PLACEMENT_EPS
    extrude_h = abs_relief + (eps if raised else 2 * eps)

    # Axis origin uses the mid-wall radius of the host (constant across lines)
    # so the per-line glyph positions all reference the same centerline.
    axis_origin = (
        anchor.position[0] - r_mid * outward_from_axis_unit[0],
        anchor.position[1] - r_mid * outward_from_axis_unit[1],
        anchor.position[2] - r_mid * outward_from_axis_unit[2],
    )

    # Slant components are line-independent (slope is a global property
    # of the cone). For cylindrical, slope = 0 → trivial values.
    slant_norm = math.sqrt(slope * slope + 1.0)
    slant_outward_component = slope / slant_norm
    slant_axial_component = 1.0 / slant_norm

    # Per-line axial offsets. Single-line collapses to [0.0] so behavior
    # is identical to the previous single-string path.
    if len(lines) == 1:
        line_y_offsets = [0.0]
    else:
        line_y_offsets = _line_y_offsets(len(lines), font_size, line_spacing, valign)

    label_repr = "\n".join(lines)
    glyph_nodes = []
    for line_idx, (line, line_y) in enumerate(zip(lines, line_y_offsets)):
        if not line:
            continue
        line_at_z = base_axial_offset + line_y

        # Per-line local radius: constant for cylindrical, varies for conical.
        if is_conical:
            line_radius = r_mid + line_at_z * slope
            if line_radius <= 0:
                raise ValidationError(
                    f"add_text: conical surface radius at at_z={line_at_z:.3f} "
                    f"(line {line_idx}) is {line_radius:.3f} (cone tip or "
                    f"beyond). Pick an at_z / line_spacing where the radius "
                    f"is positive for every line."
                )
            if line_radius < 0.5 * font_size:
                loc_str = f" (at {loc})" if loc else ""
                _log.warning(
                    "add_text: conical local radius %.2f mm at at_z=%.2f "
                    "(line %d) is small relative to font_size=%.1f — "
                    "glyphs may overlap%s",
                    line_radius, line_at_z, line_idx, font_size, loc_str,
                )
        else:
            line_radius = r_mid

        glyph_nodes.extend(_emit_wrap_line(
            line=line,
            line_radius=line_radius,
            line_at_z=line_at_z,
            font_size=font_size,
            extrude_h=extrude_h,
            eps=eps,
            abs_relief=abs_relief,
            raised=raised,
            base_meridian_rad=base_meridian_rad,
            halign=halign, valign=valign,
            axis=axis,
            anchor_normal=anchor.normal,
            axis_origin=axis_origin,
            s_outward=s_outward,
            is_conical=is_conical,
            text_orient=text_orient,
            slant_outward_component=slant_outward_component,
            slant_axial_component=slant_axial_component,
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
    base_meridian_rad, halign, valign,
    axis, anchor_normal, axis_origin, s_outward,
    is_conical, text_orient,
    slant_outward_component, slant_axial_component,
    text_kwargs, label_repr, loc,
):
    """Emit per-glyph nodes for one line wrapped around a cylindrical or
    conical surface at a given axial position. Returns a list of placed
    glyph nodes (caller assembles them into a union or difference).
    """
    n_chars = len(line)

    advance_mm = 0.6 * font_size * text_kwargs.get("spacing", 1.0)
    arc_step = advance_mm / line_radius

    total_arc_rad = n_chars * arc_step
    if total_arc_rad > 2 * math.pi:
        loc_str = f" (at {loc})" if loc else ""
        _log.warning(
            "add_text: line %r wraps %.0f%% of the surface at radius "
            "%.2f mm — glyphs will overlap%s",
            line, 100 * total_arc_rad / (2 * math.pi), line_radius, loc_str,
        )

    if halign == "left":
        offsets = [(i + 0.5) * arc_step for i in range(n_chars)]
    elif halign == "right":
        offsets = [-(n_chars - i - 0.5) * arc_step for i in range(n_chars)]
    else:
        offsets = [(i - (n_chars - 1) / 2.0) * arc_step for i in range(n_chars)]

    out = []
    for char, offset_from_meridian in zip(line, offsets):
        theta = base_meridian_rad + offset_from_meridian
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
                slant_outward_component * outward_at_theta[0] + slant_axial_component * axis[0],
                slant_outward_component * outward_at_theta[1] + slant_axial_component * axis[1],
                slant_outward_component * outward_at_theta[2] + slant_axial_component * axis[2],
            )
            surface_normal = (
                tangent[1] * slant[2] - tangent[2] * slant[1],
                tangent[2] * slant[0] - tangent[0] * slant[2],
                tangent[0] * slant[1] - tangent[1] * slant[0],
            )
            up_dir = slant
            extrude_dir = surface_normal
        else:
            up_dir = axis
            extrude_dir = radial

        glyph_2d = _text_factory(
            char,
            size=font_size,
            font=text_kwargs.get("font"),
            halign="center",
            valign=valign if len(label_repr.split("\n")) == 1 else "center",
            spacing=text_kwargs.get("spacing", 1.0),
            direction=text_kwargs.get("direction", "ltr"),
            language=text_kwargs.get("language", "en"),
            script=text_kwargs.get("script", "latin"),
            fn=text_kwargs.get("fn"),
            fa=text_kwargs.get("fa"),
            fs=text_kwargs.get("fs"),
        )
        extruded = linear_extrude(glyph_2d, height=extrude_h)
        oriented = MultMatrix(
            matrix=_orient_glyph_matrix(tangent, up_dir, extrude_dir),
            child=extruded,
            source_location=loc,
        )

        d = s_outward * line_radius - eps - (abs_relief if not raised else 0.0)
        glyph_pos = (
            axis_origin[0] + d * radial[0] + line_at_z * axis[0],
            axis_origin[1] + d * radial[1] + line_at_z * axis[1],
            axis_origin[2] + d * radial[2] + line_at_z * axis[2],
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

    u_axis, _v_axis = _face_tangent_frame(None, face_normal)
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
            halign=halign, valign=valign,
            face_normal=face_normal,
            rim_center=rim_center,
            u_axis=u_axis,
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
    base_meridian_rad, halign, valign,
    face_normal, rim_center, u_axis,
    text_kwargs, label_repr, loc,
):
    """Emit per-glyph nodes for one rim-arc line at a given path radius."""
    n_chars = len(line)

    advance_mm = 0.6 * font_size * text_kwargs.get("spacing", 1.0)
    arc_step = advance_mm / line_path_radius

    total_arc_rad = n_chars * arc_step
    if total_arc_rad > 2 * math.pi:
        loc_str = f" (at {loc})" if loc else ""
        _log.warning(
            "add_text: line %r wraps %.0f%% of the rim circle at radius "
            "%.2f mm — glyphs will overlap%s",
            line, 100 * total_arc_rad / (2 * math.pi), line_path_radius, loc_str,
        )

    if halign == "left":
        offsets = [(i + 0.5) * arc_step for i in range(n_chars)]
    elif halign == "right":
        offsets = [-(n_chars - i - 0.5) * arc_step for i in range(n_chars)]
    else:
        offsets = [(i - (n_chars - 1) / 2.0) * arc_step for i in range(n_chars)]

    out = []
    for char, offset_from_meridian in zip(line, offsets):
        theta = base_meridian_rad + offset_from_meridian
        radial = _rotate_around_axis(u_axis, theta, face_normal)
        tangent = (
            face_normal[1] * radial[2] - face_normal[2] * radial[1],
            face_normal[2] * radial[0] - face_normal[0] * radial[2],
            face_normal[0] * radial[1] - face_normal[1] * radial[0],
        )

        glyph_2d = _text_factory(
            char,
            size=font_size,
            font=text_kwargs.get("font"),
            halign="center",
            valign=valign if len(label_repr.split("\n")) == 1 else "center",
            spacing=text_kwargs.get("spacing", 1.0),
            direction=text_kwargs.get("direction", "ltr"),
            language=text_kwargs.get("language", "en"),
            script=text_kwargs.get("script", "latin"),
            fn=text_kwargs.get("fn"),
            fa=text_kwargs.get("fa"),
            fs=text_kwargs.get("fs"),
        )
        extruded = linear_extrude(glyph_2d, height=extrude_h)
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
    font=None,
    halign="center",
    valign="center",
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

    # 2. Dispatch by surface kind.
    if placement_anchor.kind == "planar":
        # Resolve text_curvature for planar surfaces. Rim anchors (carrying
        # `rim_radius`) default to arc; flat faces default to straight.
        rim_radius = placement_anchor.surface_param("rim_radius")
        is_rim = rim_radius is not None
        if text_curvature == "arc":
            if not is_rim:
                raise ValidationError(
                    "add_text: text_curvature='arc' requires a rim anchor "
                    "(top/bottom of a Cylinder, Tube, or Funnel). This "
                    "anchor has no rim_radius surface_param."
                )
            use_arc = True
        elif text_curvature == "flat":
            use_arc = False
        else:  # None — default
            use_arc = is_rim

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

    if placement_anchor.kind in ("cylindrical", "conical"):
        if text_curvature is not None:
            raise ValidationError(
                "add_text: text_curvature applies only to flat rim "
                "anchors (top/bottom of a Cylinder, Tube, or Funnel); "
                "side walls always wrap. Drop the kwarg."
            )
        if at_radial is not None:
            raise ValidationError(
                "add_text: `at_radial` is for rim arc text; on a "
                "cylindrical or conical wall use `at_z` (axial offset)."
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
            text_kwargs, loc,
        )

    raise ValidationError(
        f"add_text: surface kind {placement_anchor.kind!r} is not supported. "
        f"Use a planar, cylindrical, or conical anchor."
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
