"""Surface-coincidence predicates for ``Node.fuse`` and the standalone
``fuse`` peer form.

Pure functions over ``Anchor`` instances. The matching engine in
``find_contacts`` composes these into the per-kind match rules for the
spec. Tolerances come from ``scadwright.api.tolerances``:

- Radial / position equality: ``coincidence_tol()`` (user-tunable).
- Direction unit-vector parallelism: ``PARALLEL_CROSS_TOL``.
- Axial-extent strict overlap: ``coincidence_tol()`` margin.
"""

from __future__ import annotations

import math


def _vec_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _axes_parallel(d1, d2, cross_tol):
    """True if d1 and d2 are parallel (or anti-parallel) within ``cross_tol``."""
    return _length(_cross(d1, d2)) <= cross_tol


def axis_origin(anchor):
    """A point on the central axis line of ``anchor``'s surface.

    For cylindrical / conical anchors: derived from position minus the
    radial offset along the (signed by ``inner``) normal.
    For meridional / spherical anchors: the ``axis_origin`` field.

    Returns ``None`` if the anchor doesn't carry sufficient geometry
    (planar bbox-face anchors, etc.).
    """
    from scadwright.ast.placement import _axis_origin_for
    return _axis_origin_for(anchor)


def axis_lines_coincide(a1, a2):
    """Two curved anchors share the same axis-of-rotation line.

    Checks (a) ``axis`` directions parallel (or anti-parallel) within
    ``PARALLEL_CROSS_TOL``, and (b) the vector between their axis
    origins is itself parallel to the axis (the two origins lie on the
    same line) within ``coincidence_tol()``.
    """
    from scadwright.api.tolerances import PARALLEL_CROSS_TOL, coincidence_tol

    if a1.axis is None or a2.axis is None:
        return False
    o1 = axis_origin(a1)
    o2 = axis_origin(a2)
    if o1 is None or o2 is None:
        return False

    if not _axes_parallel(a1.axis, a2.axis, PARALLEL_CROSS_TOL):
        return False

    delta = _vec_sub(o2, o1)
    delta_len = _length(delta)
    if delta_len <= coincidence_tol():
        return True
    # delta must be parallel to axis (cross with axis dir near zero)
    # Normalize delta to make the cross magnitude scale-independent.
    delta_unit = (delta[0] / delta_len, delta[1] / delta_len, delta[2] / delta_len)
    return _length(_cross(delta_unit, a1.axis)) <= PARALLEL_CROSS_TOL


def _axial_position_in_shared_frame(anchor, shared_origin, shared_axis):
    """Project ``anchor``'s axis_origin onto the shared axis (signed scalar).

    The result is the offset along ``shared_axis`` from
    ``shared_origin`` to the anchor's axis_origin. Combined with the
    anchor's ``length`` and the convention that the anchor's reference
    position is at axial midpoint, the axial extent is
    ``[result - length/2, result + length/2]``.
    """
    o = axis_origin(anchor)
    return _dot(_vec_sub(o, shared_origin), shared_axis)


def _sign_for_relative_axis(a1, a2):
    """Return +1 if a2.axis points the same way as a1.axis, -1 if opposite."""
    return 1.0 if _dot(a1.axis, a2.axis) >= 0 else -1.0


def axial_extent_in_shared_frame(anchor, shared_anchor):
    """Return ``(lo, hi)`` axial extent of ``anchor`` in the shared frame
    defined by ``shared_anchor.axis_origin`` and ``shared_anchor.axis``.

    Requires the shared axis lines to coincide; caller is expected to
    have already verified via ``axis_lines_coincide``.
    """
    shared_origin = axis_origin(shared_anchor)
    shared_axis = shared_anchor.axis
    midpoint = _axial_position_in_shared_frame(anchor, shared_origin, shared_axis)
    length = anchor.length or 0.0
    half = length / 2.0
    return (midpoint - half, midpoint + half)


def axial_extents_overlap(a1, a2):
    """Strict overlap of axial extents in a1's frame. Touching at an
    endpoint does NOT count (an end-to-end pair falls to a cap-to-cap
    planar match, not a wall match)."""
    from scadwright.api.tolerances import coincidence_tol

    if a1.length is None or a2.length is None:
        return False
    e1 = axial_extent_in_shared_frame(a1, a1)
    e2 = axial_extent_in_shared_frame(a2, a1)
    tol = coincidence_tol()
    return (e2[0] < e1[1] - tol) and (e1[0] < e2[1] - tol)


def axial_extents_match_strict(a1, a2):
    """Axial extents coincide endpoint-for-endpoint in a1's frame.

    Stricter than ``axial_extents_overlap``: required for conical and
    meridional matches where the surface ``r(z)`` function depends on
    axial position, so partial overlap is not generally a coincident
    surface.
    """
    from scadwright.api.tolerances import coincidence_tol

    if a1.length is None or a2.length is None:
        return False
    e1 = axial_extent_in_shared_frame(a1, a1)
    e2 = axial_extent_in_shared_frame(a2, a1)
    tol = coincidence_tol()
    return abs(e1[0] - e2[0]) <= tol and abs(e1[1] - e2[1]) <= tol


def _radii_match(r_a, r_b, tol):
    return r_a is not None and r_b is not None and abs(r_a - r_b) <= tol


def cylindrical_radius_match(a1, a2):
    from scadwright.api.tolerances import coincidence_tol
    return _radii_match(a1.radius, a2.radius, coincidence_tol())


def conical_radii_match(a1, a2):
    """Both r1 and r2 match. Caller must also verify axial extents match
    strictly, because r1/r2 are radii at the cone's ends and only
    describe the same surface if the ends are at the same axial
    positions in the shared frame."""
    from scadwright.api.tolerances import coincidence_tol
    tol = coincidence_tol()
    return _radii_match(a1.r1, a2.r1, tol) and _radii_match(a1.r2, a2.r2, tol)


def spherical_match(a1, a2):
    """Same center (axis_origin) and same radius. Spherical anchors
    don't have an axial extent — the whole sphere surface is the
    contact."""
    from scadwright.api.tolerances import coincidence_tol
    tol = coincidence_tol()
    if a1.axis_origin is None or a2.axis_origin is None:
        return False
    if not _radii_match(a1.radius, a2.radius, tol):
        return False
    delta = _vec_sub(a1.axis_origin, a2.axis_origin)
    return _length(delta) <= tol


def meridional_radii_match(a1, a2):
    """meridian_r, mid_r, end_r, meridian_s all match. Caller verifies
    axial extents match strictly (curved meridian r(z) depends on z)."""
    from scadwright.api.tolerances import coincidence_tol
    tol = coincidence_tol()
    return (
        _radii_match(a1.meridian_r, a2.meridian_r, tol)
        and _radii_match(a1.mid_r, a2.mid_r, tol)
        and _radii_match(a1.end_r, a2.end_r, tol)
        and a1.meridian_s == a2.meridian_s
    )


def planar_coincidence(a1, a2):
    """Two planar anchors with coincident positions and anti-parallel
    normals. The bog-standard mating-face contact."""
    from scadwright.api.tolerances import coincidence_tol, PARALLEL_CROSS_TOL

    if a1.kind != "planar" or a2.kind != "planar":
        return False
    delta = _vec_sub(a1.position, a2.position)
    if _length(delta) > coincidence_tol():
        return False
    # Normals must be anti-parallel: n1 + n2 ≈ 0.
    sum_n = (a1.normal[0] + a2.normal[0],
             a1.normal[1] + a2.normal[1],
             a1.normal[2] + a2.normal[2])
    return _length(sum_n) <= PARALLEL_CROSS_TOL * 10 or _length(sum_n) <= 1e-6


def compatible_inner_flags(a1, a2):
    """Exactly one anchor has ``inner=True``; the other has
    ``inner=False``. Required for cylindrical / conical / spherical /
    meridional matches (concentric contact: one inner, one outer)."""
    return bool(a1.inner) != bool(a2.inner)


# =============================================================================
# Match engine — combines the per-kind predicates into the spec's rules.
# =============================================================================


from dataclasses import dataclass


@dataclass(frozen=True)
class ContactMatch:
    """A coincident-surface contact between two anchors.

    ``self_name`` / ``host_name`` are the canonical (friendly) names used
    in error messages. ``concentric`` is True for curved matches whose
    alignment step should skip the translate (axis lines coincide and
    radii match) and False for planar.
    """
    self_name: str
    self_anchor: object
    host_name: str
    host_anchor: object
    kind: str
    concentric: bool


def _match_pair(a, b):
    """Return ``(kind, concentric)`` if (a, b) describe the same surface,
    else ``None``.

    The per-kind rules:

    - **planar**: positions coincident, normals anti-parallel.
    - **cylindrical**: axis lines coincide, radii match, one ``inner=True``
      and one ``inner=False``, axial extents overlap.
    - **conical**: axis lines coincide, r1/r2 match, ``inner`` compat,
      axial extents match strictly (r(z) depends on z).
    - **spherical**: same center, same radius, ``inner`` compat.
    - **meridional**: axis lines coincide, all meridian params match,
      ``inner`` compat, axial extents match strictly.
    """
    if a.kind != b.kind:
        return None
    if a.kind == "planar":
        if planar_coincidence(a, b):
            return ("planar", False)
        return None
    if a.kind == "cylindrical":
        if (axis_lines_coincide(a, b)
                and cylindrical_radius_match(a, b)
                and compatible_inner_flags(a, b)
                and axial_extents_overlap(a, b)):
            return ("cylindrical", True)
        return None
    if a.kind == "conical":
        if (axis_lines_coincide(a, b)
                and conical_radii_match(a, b)
                and compatible_inner_flags(a, b)
                and axial_extents_match_strict(a, b)):
            return ("conical", True)
        return None
    if a.kind == "spherical":
        if spherical_match(a, b) and compatible_inner_flags(a, b):
            return ("spherical", True)
        return None
    if a.kind == "meridional":
        if (axis_lines_coincide(a, b)
                and meridional_radii_match(a, b)
                and compatible_inner_flags(a, b)
                and axial_extents_match_strict(a, b)):
            return ("meridional", True)
        return None
    return None


def _preferred_name(name_a, name_b):
    """Return the preferred display name when one Anchor has multiple
    aliases. Friendly names (top/bottom/front/back/lside/rside) win
    over axis-sign aliases (+x/-x/+y/-y/+z/-z)."""
    a_is_sign = name_a[:1] in ("+", "-") and len(name_a) == 2
    b_is_sign = name_b[:1] in ("+", "-") and len(name_b) == 2
    if a_is_sign and not b_is_sign:
        return name_b
    if b_is_sign and not a_is_sign:
        return name_a
    return name_a  # both friendly, both sign: keep first


def _same_surface(a, b):
    """Two anchors describe the same surface element: same kind, same
    inner flag, and the surface itself coincident within
    ``coincidence_tol()``.

    Surface identity depends on kind:

    - **planar**: a planar face is identified by position + normal. Used
      to collapse ``"top"`` / ``"+z"`` aliases on bbox faces, or a
      class-scope ``"top"`` with rim metadata alongside the bbox-derived
      ``"-z"`` at the same place.
    - **spherical**: a sphere is identified by ``axis_origin`` (center)
      and ``radius``. The Sphere primitive exposes 6 bbox-face anchors
      plus a ``"surface"`` anchor; all reference the same sphere, so
      all collapse to a single canonical spherical surface.
    - **cylindrical / conical / meridional**: position + normal
      identifies the wall (the standard library produces one anchor per
      wall per side, all at the +X meridian mid-wall).
    """
    from scadwright.api.tolerances import coincidence_tol
    if a.kind != b.kind or bool(a.inner) != bool(b.inner):
        return False
    tol = coincidence_tol()
    if a.kind == "spherical":
        # Spherical surface identity is (center, radius); position on
        # the surface varies across the 6 bbox-face anchors plus the
        # "surface" anchor.
        if a.axis_origin is None or b.axis_origin is None:
            return False
        if a.radius is None or b.radius is None:
            return False
        if abs(a.radius - b.radius) > tol:
            return False
        for i in range(3):
            if abs(a.axis_origin[i] - b.axis_origin[i]) > tol:
                return False
        return True
    for i in range(3):
        if abs(a.position[i] - b.position[i]) > tol:
            return False
        if abs(a.normal[i] - b.normal[i]) > tol:
            return False
    return True


def _surface_param_count(a):
    """Count non-None curved-surface metadata fields on an anchor.

    Used by ``_canonical_anchors`` to prefer the richer of two anchors
    that describe the same surface (a class-scope declaration with
    ``surface_params`` beats a bbox-derived default, regardless of
    dict insertion order or naming).
    """
    fields = (a.axis, a.axis_origin, a.meridian_zero,
              a.radius, a.r1, a.r2, a.length, a.rim_radius,
              a.meridian_r, a.mid_r, a.meridian_s, a.end_r)
    return sum(1 for f in fields if f is not None)


def _canonical_anchors(anchors_dict):
    """Collapse alias entries in an anchor dict.

    Returns ``[(name, anchor), ...]``. When multiple names point to
    the same surface (per ``_same_surface``), one representative is
    kept. Selection rule: richer surface metadata wins first; ties
    break on friendly-name preference (so ``"top"`` is preferred over
    ``"+z"`` when both have the same metadata).
    """
    canonical: list = []
    for name, a in anchors_dict.items():
        merged = False
        for j, (prev_name, prev_a) in enumerate(canonical):
            if _same_surface(a, prev_a):
                prev_richness = _surface_param_count(prev_a)
                new_richness = _surface_param_count(a)
                if new_richness > prev_richness:
                    keep_new = True
                elif new_richness < prev_richness:
                    keep_new = False
                else:
                    keep_new = (_preferred_name(prev_name, name) == name)
                if keep_new:
                    canonical[j] = (name, a)
                merged = True
                break
        if not merged:
            canonical.append((name, a))
    return canonical


def find_contacts(self_anchors, host_anchors):
    """Return all ``ContactMatch``es between ``self`` and ``host``.

    Alias entries on each side (``"top"`` and ``"+z"`` pointing at the
    same bbox face; class-scope ``"top"`` over the bbox-derived
    ``"-z"`` at the same position) are collapsed before matching so
    one surface produces at most one contact. Display names prefer
    friendly aliases. Results are sorted by ``(self_name, host_name)``
    for deterministic error messages and tie-breaks.
    """
    self_canon = _canonical_anchors(self_anchors)
    host_canon = _canonical_anchors(host_anchors)

    results = []
    for s_name, s_anchor in self_canon:
        for h_name, h_anchor in host_canon:
            match = _match_pair(s_anchor, h_anchor)
            if match is None:
                continue
            kind, concentric = match
            results.append(ContactMatch(
                self_name=s_name,
                self_anchor=s_anchor,
                host_name=h_name,
                host_anchor=h_anchor,
                kind=kind,
                concentric=concentric,
            ))
    results.sort(key=lambda m: (m.self_name, m.host_name))
    return results


_CURVED_KINDS = ("cylindrical", "conical", "spherical", "meridional")


def cross_kind_bridge_candidates(self_anchors, host_anchors):
    """Return ``[(self_name, self_anchor, host_name, host_anchor, host_inner), ...]``
    for planar-self + curved-host pairs that would dispatch via
    ``attach(host, bridge=True)`` instead of ``fuse``.

    Called when ``find_contacts`` returns empty, so the zero-matches
    error can point at the right primitive. ``host_inner`` is True
    when the curved host anchor is concave-inner (bore-style bridge);
    False for convex-outer.
    """
    self_canon = _canonical_anchors(self_anchors)
    host_canon = _canonical_anchors(host_anchors)
    out = []
    for s_name, s_anchor in self_canon:
        if s_anchor.kind != "planar":
            continue
        for h_name, h_anchor in host_canon:
            if h_anchor.kind not in _CURVED_KINDS:
                continue
            out.append((s_name, s_anchor, h_name, h_anchor, bool(h_anchor.inner)))
    return out
