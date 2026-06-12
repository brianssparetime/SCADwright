"""``wrap_2d`` decoration transform: place a 2D profile on a host surface as
raised or inset relief, the way ``add_text`` places wrapped text.

Registered on import. Adds ``.wrap_2d(profile=..., relief=..., ...)`` and the
geometry-only ``.wrap_2d_geometry(...)`` to every Node. See ``docs/wrap_2d.md``.

Two mechanisms, chosen by ``projection=``:

- ``"wrap"`` slices the profile into columns and places each tangent at its arc
  angle, an arc-length-faithful developable wrap. Cylindrical walls only.
- ``"flat"`` extrudes the profile into a straight prism and bounds the relief
  with the host surface offset inward (inset) or outward (raised), a flat
  orthographic projection. Planar, spherical, cylindrical, and conical walls.

``projection`` defaults to ``"wrap"`` on a cylinder and ``"flat"`` everywhere
else.
"""

from __future__ import annotations

import math

from scadwright._custom_transforms.add_text import (
    _orient_glyph_matrix,
    _resolve_angle,
    _resolve_placement,
    _rotate_around_axis,
    _rotate_z_to,
)
from scadwright._custom_transforms.base import transform
from scadwright._logging import get_logger
from scadwright.api.tolerances import TEXT_FAR_OVERSHOOT, TEXT_HOST_OVERSHOOT
from scadwright.ast.base import SourceLocation
from scadwright.ast.placement import _meridian_arc_at
from scadwright.ast.transforms import Translate
from scadwright.bbox import bbox as _bbox
from scadwright.boolops import difference, intersection, union
from scadwright.errors import ValidationError
from scadwright.extrusions import linear_extrude, rotate_extrude
from scadwright.primitives import cube as _cube
from scadwright.primitives import cylinder as _cylinder
from scadwright.primitives import polygon as _polygon
from scadwright.primitives import sphere as _sphere
from scadwright.primitives import square as _square

_log = get_logger("scadwright.wrap_2d")

# Facet count for the reconstructed offset surfaces under ``flat``. High enough
# that the chord error of the curve is far below a typical relief depth.
_FLAT_FN = 128

# Meridian samples for the revolved barrel offset surface.
_MERID_SEG = 96


# --- small vector helpers (kept local; the math here is all 3-vectors) ---


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _smul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _unit(a):
    length = math.sqrt(_dot(a, a))
    if length < 1e-12:
        return None
    return (a[0] / length, a[1] / length, a[2] / length)


# --- profile sizing ---


def _scaled_profile(profile, size, loc):
    """Center the 2D profile on the origin and scale it to ``size`` (mm).

    Returns ``(scaled_profile, width, height)``. ``size`` is a scalar (sets the
    width, aspect preserved), a ``(w, h)`` pair (both, may distort), or ``None``
    (the profile's own extent). The extent comes from ``bbox(profile)``, so an
    imported SVG/DXF needs a ``scad_import(bbox=...)`` hint to be sizable.
    """
    bb = _bbox(profile)
    w0 = bb.max[0] - bb.min[0]
    h0 = bb.max[1] - bb.min[1]
    d0 = bb.max[2] - bb.min[2]
    if d0 > 1e-6:
        raise ValidationError(
            f"wrap_2d: profile must be 2D, but it has a Z extent of {d0:.3g} mm. "
            f"Pass a 2D node (an imported SVG, a polygon, an offset outline), "
            f"not an extruded solid.",
            source_location=loc,
        )
    if w0 <= 1e-9 or h0 <= 1e-9:
        raise ValidationError(
            "wrap_2d: profile has no measurable 2D extent, so it cannot be "
            "sized or placed. For an imported file pass the extent as a hint, "
            "e.g. scad_import('logo.svg', bbox=((0, 0, 0), (w, h, 0))).",
            source_location=loc,
        )
    cx = (bb.min[0] + bb.max[0]) / 2.0
    cy = (bb.min[1] + bb.max[1]) / 2.0
    if size is None:
        sx = sy = 1.0
    elif isinstance(size, bool):
        raise ValidationError("wrap_2d: size must be a number or a (w, h) pair.", source_location=loc)
    elif isinstance(size, (int, float)):
        sx = sy = float(size) / w0
    elif hasattr(size, "__len__") and len(size) == 2:
        sx = float(size[0]) / w0
        sy = float(size[1]) / h0
    else:
        raise ValidationError(
            f"wrap_2d: size must be a number (sets the width, aspect kept) or a "
            f"(w, h) pair (sets both). Got {size!r}.",
            source_location=loc,
        )
    centered = profile.translate([-cx, -cy, 0])
    scaled = centered.scale([sx, sy, 1]) if (sx != 1.0 or sy != 1.0) else centered
    return scaled, w0 * sx, h0 * sy


# --- dispatch ---


def _collect_relief(host, *, profile, relief, on, at, normal, angle, at_z,
                    size, projection, segments, eps, loc):
    """Resolve placement, pick the mechanism, and return the relief geometry.

    Returns a single Node: the raised relief (compose with ``union``) or the
    inset cutter (compose with ``difference``). The sign of ``relief`` decides
    which, and the caller does the boolean.
    """
    if relief == 0:
        raise ValidationError("wrap_2d: relief must be non-zero (positive raises, negative insets).", source_location=loc)

    # Placement resolution is shared with add_text; relabel its messages so a
    # wrap_2d user sees the verb they called.
    try:
        anchor, _face_dims = _resolve_placement(host, on, at, normal, None, loc)
    except ValidationError as exc:
        raise ValidationError(
            exc.args[0].replace("add_text:", "wrap_2d:"),
            source_location=getattr(exc, "source_location", loc),
        ) from None
    kind = anchor.kind

    if projection is None:
        projection = "wrap" if kind == "cylindrical" else "flat"
    if projection not in ("wrap", "flat"):
        raise ValidationError(
            f"wrap_2d: projection must be 'wrap' or 'flat', got {projection!r}.",
            source_location=loc,
        )

    prof, width, height = _scaled_profile(profile, size, loc)
    eps_host = TEXT_HOST_OVERSHOOT if eps is None else float(eps)

    if projection == "wrap":
        if kind == "cylindrical":
            return _wrap_cylinder(anchor, prof, width, height, relief, angle, at_z, segments, eps_host, loc)
        if kind == "conical":
            raise ValidationError(
                "wrap_2d: projection='wrap' on a conical wall leaves non-manifold "
                "seams on the taper and is not supported. Use projection='flat' "
                "(the default on cones).",
                source_location=loc,
            )
        if kind == "planar":
            raise ValidationError(
                "wrap_2d: projection='wrap' on a planar face has nothing to wrap. "
                "Use projection='flat' (the default on flat faces).",
                source_location=loc,
            )
        raise ValidationError(
            f"wrap_2d: projection='wrap' needs a developable (cylindrical) wall; "
            f"this anchor is {kind!r}, a non-developable surface that a flat "
            f"drawing cannot lie on without distortion. Use projection='flat'.",
            source_location=loc,
        )

    # projection == "flat"
    if kind == "planar":
        return _flat_planar(anchor, prof, relief, eps_host, loc)
    if kind in ("spherical", "cylindrical", "conical", "meridional"):
        return _flat_curved(anchor, kind, prof, width, height, relief, angle, at_z, eps_host, loc)
    raise ValidationError(f"wrap_2d: unsupported surface kind {kind!r}.", source_location=loc)


# --- flat: planar ---


def _flat_planar(anchor, prof, relief, eps_host, loc):
    """Flat face: extrude the profile and place it on the face, the way
    ``add_text`` places planar text. The inner offset surface degenerates to a
    parallel plane, so no surface reconstruction is needed.
    """
    raised = relief > 0
    d = abs(relief)
    far = TEXT_FAR_OVERSHOOT
    extrude_h = d + eps_host + (0.0 if raised else far)
    extruded = linear_extrude(prof, height=extrude_h)

    n = anchor.normal
    target = n if raised else (-n[0], -n[1], -n[2])
    rotated = _rotate_z_to(extruded, target, loc)

    pos = anchor.position
    if raised:
        shift = (pos[0] - eps_host * n[0], pos[1] - eps_host * n[1], pos[2] - eps_host * n[2])
    else:
        shift = (pos[0] + eps_host * n[0], pos[1] + eps_host * n[1], pos[2] + eps_host * n[2])
    return Translate(v=shift, child=rotated, source_location=loc)


# --- flat: curved (sphere, cylinder, cone) ---


def _flat_curved(anchor, kind, prof, width, height, relief, angle, at_z, eps_host, loc):
    """Flat projection cutter on a curved wall (sphere, cylinder, cone, barrel).

    Extrude the profile into a straight prism along the surface normal, clip it
    to the near half-space, and intersect with a shell bounded by the host
    surface offset into the material (inset) or into the void (raised). The
    shell's two surfaces sit a constant perpendicular distance apart, so the
    relief depth is uniform normal to the surface.

    ``surf(q)`` is the solid bounded by the host surface displaced by ``q`` along
    the outward normal: ``q > 0`` into the void where raised relief stands,
    ``q < 0`` into the material. ``s = -1`` on an inner wall (normal pointing
    toward the axis), ``+1`` on an outer wall; it flips the radius mapping so the
    same code serves a bore as serves an outer wall.
    """
    raised = relief > 0
    d = abs(relief)
    a = _unit(anchor.axis) if anchor.axis else None
    s = -1.0 if anchor.inner else 1.0

    if kind == "spherical":
        if angle is not None or at_z is not None:
            raise ValidationError(
                "wrap_2d: angle= and at_z= apply to cylindrical, conical, and "
                "barrel walls; place on a sphere with on= or at=.",
                source_location=loc,
            )
        r = anchor.radius
        if s < 0 and d >= r:
            raise ValidationError(
                f"wrap_2d: relief {d} reaches the sphere center (radius {r}); "
                f"use a shallower relief.",
                source_location=loc,
            )
        center = anchor.axis_origin
        n = _unit(anchor.normal)
        p_point = anchor.position
        clip_c = center
        r_max = r

        def surf(q):
            return _sphere(r=r + s * q, fn=_FLAT_FN).translate(list(center))

    elif kind == "cylindrical":
        r = anchor.radius
        if s < 0 and d >= r:
            raise ValidationError(
                f"wrap_2d: relief {d} reaches the bore axis (radius {r}); "
                f"use a shallower relief.",
                source_location=loc,
            )
        into_void0 = _unit(anchor.normal)
        theta = _resolve_angle(angle) if angle is not None else 0.0
        into_void = _unit(_rotate_around_axis(into_void0, theta, a))
        radial_out0 = _smul(into_void0, s)
        radial_out = _smul(into_void, s)
        o_mid = _sub(anchor.position, _smul(radial_out0, r))
        o = _add(o_mid, _smul(a, at_z or 0.0))
        n = into_void
        p_point = _add(o, _smul(radial_out, r))
        clip_c = o
        r_max = r
        cyl_len = 2.0 * anchor.length + 4.0 * (d + eps_host) + 2.0 * height

        def surf(q):
            base = _cylinder(h=cyl_len, r=r + s * q, center=True, fn=_FLAT_FN)
            return _rotate_z_to(base, a, loc).translate(list(o))

    elif kind == "conical":
        r1, r2, length = anchor.r1, anchor.r2, anchor.length
        into_void0 = _unit(anchor.normal)
        radial_out0 = _smul(into_void0, s)  # away from the axis
        theta = _resolve_angle(angle) if angle is not None else 0.0
        radial_out = _unit(_rotate_around_axis(radial_out0, theta, a))
        r_mid = (r1 + r2) / 2.0
        m = (r2 - r1) / length  # dr/dz along the axis
        o_mid = _sub(anchor.position, _smul(radial_out0, r_mid))
        o = _add(o_mid, _smul(a, at_z or 0.0))
        r_local = r_mid + m * (at_z or 0.0)
        p_point = _add(o, _smul(radial_out, r_local))
        outward_slant = _unit(_sub(radial_out, _smul(a, m)))  # away from the axis
        n = _smul(outward_slant, s)
        clip_c = o
        r_max = max(r1, r2)
        cos_a = 1.0 / math.sqrt(1.0 + m * m)
        # Reconstruct the cone solid to bound the relief. This places the base
        # half a length below the anchor, which relies on the conical anchor
        # sitting at the axial mid-wall (the convention every built-in cone
        # anchor follows; see anchors_from_cylinder).
        base_center = _sub(o_mid, _smul(a, length / 2.0))
        cone = _rotate_z_to(
            _cylinder(h=length, r1=r1, r2=r2, fn=_FLAT_FN), a, loc
        ).translate(list(base_center))

        def surf(q):
            # Perpendicular offset q (along the void normal) via an axial
            # translate of the cone solid; s carries the inner/outer flip.
            delta = -((s * q) / cos_a) / m
            return cone.translate(list(_smul(a, delta)))

    else:  # meridional (barrel)
        mr, midr, ms, length = (
            anchor.meridian_r, anchor.mid_r, anchor.meridian_s, anchor.length
        )
        if d >= mr:
            raise ValidationError(
                f"wrap_2d: relief {d} exceeds the barrel's meridian radius of "
                f"curvature {mr:.3g}; the offset surface would self-intersect. "
                f"Use a shallower relief.",
                source_location=loc,
            )
        origin = anchor.axis_origin
        at = float(at_z) if at_z is not None else 0.0
        if abs(at) > length / 2.0 + 1e-9:
            raise ValidationError(
                f"wrap_2d: at_z={at} is outside the barrel wall "
                f"[{-length / 2.0}, {length / 2.0}].",
                source_location=loc,
            )
        into_void0 = _unit(anchor.normal)
        radial_out0 = _smul(into_void0, s)
        theta = _resolve_angle(angle) if angle is not None else 0.0
        radial_out = _unit(_rotate_around_axis(radial_out0, theta, a))
        r_local, n_o, n_a = _meridian_arc_at(at, mr, midr, ms)
        o = _add(origin, _smul(a, at))
        p_point = _add(o, _smul(radial_out, r_local))
        # Into-void normal: s times the arc's outward normal, mapped into the
        # meridian plane at this angle.
        n = _unit(_add(_smul(radial_out, s * n_o), _smul(a, s * n_a)))
        clip_c = origin
        r_max = max(midr, anchor.end_r)

        def surf(q):
            # Sample the meridian, displace each point by q along its own normal
            # (s for the inner/outer flip), revolve. Offsetting along the normal,
            # not radially, is what makes the depth uniform normal to the surface.
            arc = []
            for i in range(_MERID_SEG + 1):
                zz = -length / 2.0 + length * i / _MERID_SEG
                rr, no, na = _meridian_arc_at(zz, mr, midr, ms)
                arc.append((rr + q * s * no, zz + q * s * na))
            poly = [(0.0, arc[0][1])] + arc + [(0.0, arc[-1][1])]
            sol = rotate_extrude(_polygon(poly), fn=_FLAT_FN)
            return _rotate_z_to(sol, a, loc).translate(list(origin))

    # Straight prism through the surface, long enough to cross the shell across
    # the whole footprint, then clipped to the near side.
    u = _unit(_cross(a, n)) if a else None
    if u is None:
        for ref in ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)):
            u = _unit(_cross(ref, n))
            if u is not None:
                break
    v = _unit(_cross(n, u))

    prism_len = 4.0 * r_max + 4.0 * (d + eps_host) + 2.0 * max(width, height) + 20.0
    m_orient = _orient_glyph_matrix(u, v, n)  # local +X->u, +Y->v, +Z->n
    prism = (
        linear_extrude(prof, height=prism_len)
        .translate([0, 0, -prism_len / 2.0])
        .multmatrix(m_orient)
        .translate(list(p_point))
    )

    big = 2.0 * prism_len
    halfspace = _rotate_z_to(
        _cube([big, big, big], center=True).translate([0, 0, big / 2.0]), n, loc
    ).translate(list(clip_c))

    # Shell between the void edge and the material edge, the bigger solid (more
    # material, larger ``q * s``) minus the smaller.
    def shell(q_void, q_material):
        if q_void * s >= q_material * s:
            return difference(surf(q_void), surf(q_material))
        return difference(surf(q_material), surf(q_void))

    if raised:
        shell_solid = shell(d, -eps_host)
    else:
        shell_solid = shell(eps_host, -d)
    return intersection(prism, halfspace, shell_solid)


# --- wrap: cylindrical slice ---


def _wrap_cylinder(anchor, prof, width, height, relief, angle, at_z, segments, eps_host, loc):
    """Developable wrap on a cylinder: slice the profile into columns and place
    each tangent at its arc angle. The host carries the column bases, and each
    column overshoots into the wall by ``eps_host`` so the union stays watertight.
    """
    raised = relief > 0
    d = abs(relief)
    far = TEXT_FAR_OVERSHOOT
    r = anchor.radius
    a = _unit(anchor.axis)
    s = -1.0 if anchor.inner else 1.0
    into_void0 = _unit(anchor.normal)        # toward the void (the relief side)
    radial_out0 = _smul(into_void0, s)       # away from the axis
    theta0 = _resolve_angle(angle) if angle is not None else 0.0
    o_mid = _sub(anchor.position, _smul(radial_out0, r))
    o = _add(o_mid, _smul(a, at_z or 0.0))

    circumference = 2.0 * math.pi * r
    if width > circumference:
        _log.warning(
            "wrap_2d: profile width %.1f mm exceeds the circumference %.1f mm; "
            "it wraps past itself.", width, circumference,
        )

    if segments is not None:
        n_cols = int(segments)
        if n_cols < 1:
            raise ValidationError("wrap_2d: segments must be a positive integer.", source_location=loc)
    else:
        arc_deg = math.degrees(width / r)
        n_cols = max(8, math.ceil(arc_deg / 2.0))

    x0 = -width / 2.0
    strip_h = height + 2.0
    cols = []
    for i in range(n_cols):
        xa = x0 + width * i / n_cols
        xb = x0 + width * (i + 1) / n_cols
        xc = (xa + xb) / 2.0
        strip = _square([xb - xa, strip_h], center=True).translate([xc, 0, 0])
        slice_2d = intersection(prof, strip)

        if raised:
            sh = d + eps_host
            sl = linear_extrude(slice_2d, height=sh).translate([-xc, 0, -eps_host])
        else:
            sh = d + eps_host + far
            sl = linear_extrude(slice_2d, height=sh).translate([-xc, 0, -d])

        theta_i = theta0 + xc / r
        into_void = _unit(_rotate_around_axis(into_void0, theta_i, a))
        radial_out = _smul(into_void, s)  # surface point sits this way from the axis
        tangent = _unit(_cross(a, radial_out))
        # Local +Z is the void direction the column extrudes along; the column
        # base sits on the surface at radius r and buries eps into the wall.
        m_orient = _orient_glyph_matrix(tangent, a, into_void)
        placed = sl.multmatrix(m_orient).translate(list(_add(o, _smul(radial_out, r))))
        cols.append(placed)

    if not cols:
        raise ValidationError("wrap_2d: produced no columns; check segments and size.", source_location=loc)
    return union(*cols) if len(cols) > 1 else cols[0]


# --- public transforms ---


@transform("wrap_2d", inline=True, decoration=True)
def wrap_2d(
    host,
    *,
    profile,
    relief,
    on=None,
    at=None,
    normal=None,
    angle=None,
    at_z=None,
    size=None,
    projection=None,
    segments=None,
    eps=None,
):
    """Place a 2D profile on a host surface as raised or inset relief.

    ``profile`` is any 2D node — an imported SVG (``scad_import('logo.svg',
    bbox=...)``), a polygon, an offset outline. ``relief`` is signed: positive
    raises the profile outward by that distance and unions it on; negative cuts
    it that deep into the host.

    Placement reuses ``add_text``'s vocabulary: ``on=`` for a named anchor or an
    ``Anchor``, or ``at=(x, y, z)`` + ``normal=`` for ad-hoc placement.
    ``angle=`` and ``at_z=`` set the angular position and axial offset on
    cylindrical and conical walls. ``size=`` sets the profile's millimetre
    extent (a scalar keeps aspect, a ``(w, h)`` pair sets both).

    ``projection=`` chooses the mechanism: ``"wrap"`` (developable, cylinder
    only) keeps proportions; ``"flat"`` presses the profile straight onto the
    surface and suits a small shape on a large curved one. It defaults to
    ``"wrap"`` on a cylinder and ``"flat"`` elsewhere. ``segments=`` sets the
    column count for ``"wrap"``; ``eps=`` overrides the host overshoot.

    For the placed relief without the host (a cutter, or for use outside a
    ``force_render`` scope), use ``wrap_2d_geometry`` with the same kwargs.
    """
    loc = SourceLocation.from_caller()
    relief_geom = _collect_relief(
        host, profile=profile, relief=relief, on=on, at=at, normal=normal,
        angle=angle, at_z=at_z, size=size, projection=projection,
        segments=segments, eps=eps, loc=loc,
    )
    if relief > 0:
        return union(host, relief_geom)
    return difference(host, relief_geom)


@transform("wrap_2d_geometry", inline=True)
def wrap_2d_geometry(
    host,
    *,
    profile,
    relief,
    on=None,
    at=None,
    normal=None,
    angle=None,
    at_z=None,
    size=None,
    projection=None,
    segments=None,
    eps=None,
):
    """Return the placed relief geometry in the host's frame *without* combining
    it with the host. Same kwargs as ``wrap_2d``; the host is consumed for
    anchor resolution only. The sign of ``relief`` still chooses the direction:
    negative produces a cutter (compose with ``difference``), positive a raised
    mesh (compose with ``union``).
    """
    loc = SourceLocation.from_caller()
    return _collect_relief(
        host, profile=profile, relief=relief, on=on, at=at, normal=normal,
        angle=angle, at_z=at_z, size=size, projection=projection,
        segments=segments, eps=eps, loc=loc,
    )
