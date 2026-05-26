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


def _planar_position_on_curved_surface(planar_anchor, curved_anchor):
    """True iff ``planar_anchor.position`` lies on (within
    ``coincidence_tol()`` of) ``curved_anchor``'s surface.

    Used to gate the bridge-case hint in the zero-match error: a
    planar self anchor only suggests ``bridge=True`` when it is
    actually positioned against the curved host's surface. A peg
    sitting in the bore (not on either wall) or two shapes far apart
    in space don't qualify.

    Per-kind geometry:

    - **cylindrical**: project ``planar.position`` onto the host axis;
      axial offset must lie inside the host's length and radial
      distance from the axis must equal ``host.radius``.
    - **conical**: same projection; the expected radius interpolates
      linearly between ``r1`` (at ``-length/2``) and ``r2`` (at
      ``+length/2``).
    - **spherical**: distance from planar position to
      ``host.axis_origin`` equals ``host.radius``.
    - **meridional**: axial extent check + radial distance within the
      ``[min(end_r, mid_r), max(end_r, mid_r)]`` envelope (a loose
      bound — exact arc geometry isn't worth the complexity for a
      diagnostic-only check; the envelope is the smallest box that
      contains every meridian arc with the given endpoints).
    """
    from scadwright.api.tolerances import coincidence_tol
    tol = coincidence_tol()

    kind = curved_anchor.kind
    p = planar_anchor.position

    if kind == "spherical":
        c = curved_anchor.axis_origin
        if c is None or curved_anchor.radius is None:
            return False
        d = _vec_sub(p, c)
        return abs(_length(d) - curved_anchor.radius) <= tol

    # cylindrical / conical / meridional — all share an axis + extent.
    o = axis_origin(curved_anchor)
    axis = curved_anchor.axis
    length = curved_anchor.length
    if o is None or axis is None or length is None:
        return False
    d = _vec_sub(p, o)
    axial = _dot(d, axis)
    half = length / 2.0
    if abs(axial) > half + tol:
        return False
    radial_vec = (d[0] - axial * axis[0],
                  d[1] - axial * axis[1],
                  d[2] - axial * axis[2])
    radial = _length(radial_vec)

    if kind == "cylindrical":
        if curved_anchor.radius is None:
            return False
        return abs(radial - curved_anchor.radius) <= tol

    if kind == "conical":
        r1 = curved_anchor.r1
        r2 = curved_anchor.r2
        if r1 is None or r2 is None:
            return False
        # axial in [-half, +half]; t = (axial + half) / length is fraction along the cone.
        t = (axial + half) / length if length > 0 else 0.5
        expected = r1 * (1.0 - t) + r2 * t
        return abs(radial - expected) <= tol

    if kind == "meridional":
        end_r = curved_anchor.end_r
        mid_r = curved_anchor.mid_r
        if end_r is None or mid_r is None:
            return False
        lo = min(end_r, mid_r) - tol
        hi = max(end_r, mid_r) + tol
        return lo <= radial <= hi

    return False


def cross_kind_bridge_candidates(self_anchors, host_anchors):
    """Return ``[(self_name, self_anchor, host_name, host_anchor, host_inner), ...]``
    for planar-self + curved-host pairs that would dispatch via
    ``attach(host, bridge=True)`` instead of ``fuse``.

    Called when ``find_contacts`` returns empty, so the zero-matches
    error can point at the right primitive. ``host_inner`` is True
    when the curved host anchor is concave-inner (bore-style bridge);
    False for convex-outer.

    Proximity-gated: a pair is returned only when the planar self
    anchor's position actually sits on (or within ``coincidence_tol()``
    of) the curved host's surface. This keeps the bridge hint out of
    error messages for shapes that aren't anywhere near each other,
    or for cases where the real failure is a planar near-miss on a
    different face.
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
            if not _planar_position_on_curved_surface(s_anchor, h_anchor):
                continue
            out.append((s_name, s_anchor, h_name, h_anchor, bool(h_anchor.inner)))
    return out


def planar_near_miss_candidates(self_anchors, host_anchors):
    """Return ``[(self_name, host_name, offset_mm), ...]`` for planar+
    planar pairs whose planes coincide (anti-parallel normals, no
    out-of-plane component to the position displacement) but whose
    named reference positions don't match within
    ``coincidence_tol()``.

    The bog-standard footgun this catches: ``peg.fuse(plate)`` where
    the peg sits on the plate but off-center — the planes coincide,
    the polygons overlap, the user's intent is obvious, but
    ``planar_coincidence`` rejects because reference points don't
    line up. The right move is ``attach(host, fuse=True)``.
    """
    from scadwright.api.tolerances import PARALLEL_CROSS_TOL, coincidence_tol
    tol = coincidence_tol()
    self_canon = _canonical_anchors(self_anchors)
    host_canon = _canonical_anchors(host_anchors)
    out = []
    for s_name, s_anchor in self_canon:
        if s_anchor.kind != "planar":
            continue
        for h_name, h_anchor in host_canon:
            if h_anchor.kind != "planar":
                continue
            # Normals anti-parallel: n1 + n2 ≈ 0.
            sum_n = (s_anchor.normal[0] + h_anchor.normal[0],
                     s_anchor.normal[1] + h_anchor.normal[1],
                     s_anchor.normal[2] + h_anchor.normal[2])
            if _length(sum_n) > max(PARALLEL_CROSS_TOL * 10, 1e-6):
                continue
            delta = _vec_sub(s_anchor.position, h_anchor.position)
            offset = _length(delta)
            if offset <= tol:
                continue  # already a real match — let find_contacts handle it
            # Out-of-plane component: project delta onto host normal.
            out_of_plane = abs(_dot(delta, h_anchor.normal))
            if out_of_plane > tol:
                continue  # planes don't coincide; this is a real no-match
            out.append((s_name, h_name, offset))
    return out


def diagnose_match_failure(self_anchor, host_anchor):
    """Return a list of human-readable reasons why ``self_anchor`` and
    ``host_anchor`` don't form a coincident-surface match.

    Called by ``_resolve_fuse_match`` when ``_match_pair`` returns
    ``None`` for an explicit (``on=`` + ``from_anchor=``) pair, so the
    user sees which specific rule(s) failed instead of a generic rules
    catalog.

    Empty list iff the pair actually matches (callers should know this
    from the prior ``_match_pair`` call).
    """
    from scadwright.api.tolerances import PARALLEL_CROSS_TOL, coincidence_tol
    tol = coincidence_tol()
    reasons = []

    s_kind = self_anchor.kind
    h_kind = host_anchor.kind

    if s_kind != h_kind:
        if s_kind == "planar" and h_kind in _CURVED_KINDS:
            reasons.append(
                f"kinds differ (self.kind={s_kind!r}, host.kind={h_kind!r}) — "
                f"a planar face against a curved wall is a bridge case, not a "
                f"fuse case. Use self.attach(host, on=<host_anchor>, "
                f"bridge=True, orient=True)."
            )
        elif h_kind == "planar" and s_kind in _CURVED_KINDS:
            reasons.append(
                f"kinds differ (self.kind={s_kind!r}, host.kind={h_kind!r}); "
                f"a curved self surface against a planar host face is a bridge "
                f"case from the wrong direction. Swap self and host so the "
                f"planar shape is self, then use "
                f"self.attach(host, bridge=True, orient=True)."
            )
        else:
            reasons.append(
                f"kinds differ (self.kind={s_kind!r}, host.kind={h_kind!r}); "
                f"fuse requires both anchors to describe the same surface kind."
            )
        return reasons

    if s_kind == "planar":
        sum_n = (self_anchor.normal[0] + host_anchor.normal[0],
                 self_anchor.normal[1] + host_anchor.normal[1],
                 self_anchor.normal[2] + host_anchor.normal[2])
        normals_opposed = _length(sum_n) <= max(PARALLEL_CROSS_TOL * 10, 1e-6)
        if not normals_opposed:
            reasons.append(
                f"normals don't oppose (self.normal={self_anchor.normal}, "
                f"host.normal={host_anchor.normal}); planar fuse requires "
                f"anti-parallel normals so the two faces front each other."
            )
            return reasons
        delta = _vec_sub(self_anchor.position, host_anchor.position)
        offset = _length(delta)
        if offset > tol:
            out_of_plane = abs(_dot(delta, host_anchor.normal))
            if out_of_plane <= tol:
                reasons.append(
                    f"planar positions don't coincide (offset = {offset:.3g} mm) "
                    f"but the planes do; for place-and-fuse, use "
                    f"self.attach(host, fuse=True)."
                )
            else:
                reasons.append(
                    f"planar positions don't coincide (offset = {offset:.3g} mm) "
                    f"and the planes don't either (out-of-plane component = "
                    f"{out_of_plane:.3g} mm); the anchors aren't on the same face."
                )
        return reasons

    # Curved kinds.
    # Special case: same surface, same side. The anchors literally
    # describe the same surface, just both flagged as outer (or both
    # inner). Fuse rejects per the concentric-contact rule, but the
    # right answer is plain union() — the surfaces coincide, so
    # there's no seam to eliminate via eps.
    if (not compatible_inner_flags(self_anchor, host_anchor)
            and _is_same_curved_surface(self_anchor, host_anchor)):
        side_word = "concave-inner" if self_anchor.inner else "convex-outer"
        reasons.append(
            f"both anchors describe the same {s_kind} surface from the "
            f"same side (both {side_word}); fuse needs one inner and one "
            f"outer for concentric contact. For two parts whose surfaces "
            f"literally coincide, use union(self, host) — OpenSCAD "
            f"handles fully-coincident surfaces cleanly without an "
            f"internal seam."
        )
        return reasons

    if not compatible_inner_flags(self_anchor, host_anchor):
        same = "True" if self_anchor.inner else "False"
        reasons.append(
            f"both anchors have inner={same}; for curved coaxial contact, "
            f"one must be inner=True (concave/bore side) and one inner=False "
            f"(convex/outer side)."
        )

    axes_ok = True
    if s_kind in ("cylindrical", "conical", "meridional"):
        if not axis_lines_coincide(self_anchor, host_anchor):
            axes_ok = False
            reasons.append(
                f"axis lines don't coincide; the two curved surfaces aren't "
                f"on the same axis of rotation."
            )

    if s_kind == "cylindrical":
        if not cylindrical_radius_match(self_anchor, host_anchor):
            reasons.append(
                f"radii differ (self.radius={self_anchor.radius}, "
                f"host.radius={host_anchor.radius})."
            )
        if axes_ok and not axial_extents_overlap(self_anchor, host_anchor):
            e1 = axial_extent_in_shared_frame(self_anchor, self_anchor)
            e2 = axial_extent_in_shared_frame(host_anchor, self_anchor)
            reasons.append(
                f"axial extents don't overlap (self spans "
                f"[{e1[0]:.3g}, {e1[1]:.3g}], host spans "
                f"[{e2[0]:.3g}, {e2[1]:.3g}] along the shared axis)."
            )
    elif s_kind == "conical":
        if not conical_radii_match(self_anchor, host_anchor):
            reasons.append(
                f"conical radii differ "
                f"(self.r1={self_anchor.r1}, self.r2={self_anchor.r2}; "
                f"host.r1={host_anchor.r1}, host.r2={host_anchor.r2})."
            )
        if axes_ok and not axial_extents_match_strict(self_anchor, host_anchor):
            e1 = axial_extent_in_shared_frame(self_anchor, self_anchor)
            e2 = axial_extent_in_shared_frame(host_anchor, self_anchor)
            reasons.append(
                f"axial extents don't match endpoint-for-endpoint (self spans "
                f"[{e1[0]:.3g}, {e1[1]:.3g}], host spans "
                f"[{e2[0]:.3g}, {e2[1]:.3g}] along the shared axis); conical "
                f"surfaces have r(z) that varies with axial position, so "
                f"partial overlap isn't a coincident surface."
            )
    elif s_kind == "spherical":
        if self_anchor.axis_origin is None or host_anchor.axis_origin is None:
            reasons.append(
                "spherical anchor is missing axis_origin (sphere center); "
                "can't compare surfaces."
            )
        else:
            delta = _vec_sub(self_anchor.axis_origin, host_anchor.axis_origin)
            center_offset = _length(delta)
            if center_offset > tol:
                reasons.append(
                    f"sphere centers don't coincide (offset = "
                    f"{center_offset:.3g} mm; self.axis_origin="
                    f"{self_anchor.axis_origin}, host.axis_origin="
                    f"{host_anchor.axis_origin})."
                )
        if (self_anchor.radius is not None
                and host_anchor.radius is not None
                and abs(self_anchor.radius - host_anchor.radius) > tol):
            reasons.append(
                f"radii differ (self.radius={self_anchor.radius}, "
                f"host.radius={host_anchor.radius})."
            )
    elif s_kind == "meridional":
        diffs = []
        for attr in ("meridian_r", "mid_r", "end_r"):
            s_val = getattr(self_anchor, attr)
            h_val = getattr(host_anchor, attr)
            if s_val is None or h_val is None or abs(s_val - h_val) > tol:
                diffs.append(f"{attr} (self={s_val}, host={h_val})")
        if self_anchor.meridian_s != host_anchor.meridian_s:
            diffs.append(
                f"meridian_s (self={self_anchor.meridian_s}, "
                f"host={host_anchor.meridian_s})"
            )
        if diffs:
            reasons.append(f"meridian parameters differ: {'; '.join(diffs)}.")
        if axes_ok and not axial_extents_match_strict(self_anchor, host_anchor):
            e1 = axial_extent_in_shared_frame(self_anchor, self_anchor)
            e2 = axial_extent_in_shared_frame(host_anchor, self_anchor)
            reasons.append(
                f"axial extents don't match endpoint-for-endpoint (self spans "
                f"[{e1[0]:.3g}, {e1[1]:.3g}], host spans "
                f"[{e2[0]:.3g}, {e2[1]:.3g}] along the shared axis); "
                f"meridional surfaces have r(z) that varies with axial "
                f"position, so partial overlap isn't a coincident surface."
            )

    return reasons


def _is_same_curved_surface(a, b):
    """True if ``a`` and ``b`` describe the same curved surface
    (same axis line / center, same radii, axial coincidence per kind),
    **ignoring the inner flag**.

    Two anchors that satisfy this and ALSO have opposite inner flags
    are a valid concentric-contact fuse match (see ``_match_pair``).
    Two anchors that satisfy this and have the SAME inner flag are
    the "same surface from the same side" case — fuse rejects, but
    the surfaces literally coincide and ``union()`` is the right tool.
    """
    from scadwright.api.tolerances import coincidence_tol
    if a.kind != b.kind:
        return False
    kind = a.kind
    tol = coincidence_tol()
    if kind == "spherical":
        if a.axis_origin is None or b.axis_origin is None:
            return False
        if a.radius is None or b.radius is None:
            return False
        if abs(a.radius - b.radius) > tol:
            return False
        delta = _vec_sub(a.axis_origin, b.axis_origin)
        return _length(delta) <= tol
    if kind not in ("cylindrical", "conical", "meridional"):
        return False
    if not axis_lines_coincide(a, b):
        return False
    if kind == "cylindrical":
        return (cylindrical_radius_match(a, b)
                and axial_extents_overlap(a, b))
    if kind == "conical":
        return (conical_radii_match(a, b)
                and axial_extents_match_strict(a, b))
    if kind == "meridional":
        return (meridional_radii_match(a, b)
                and axial_extents_match_strict(a, b))
    return False


def curved_near_miss_candidates(self_anchors, host_anchors):
    """Return ``[(self_name, host_name, reasons), ...]`` for same-kind
    curved pairs that share an axis line (or sphere center) but fail
    on a downstream rule (inner-flag compatibility, radius match,
    axial extent).

    Called from the zero-match branch of ``_resolve_fuse_match`` to
    show why a cylindrical/conical/spherical/meridional pair didn't
    match, alongside (not instead of) the bridge-case hint. The user
    sees the specific rule that failed and can fix their anchor
    declaration directly.
    """
    self_canon = _canonical_anchors(self_anchors)
    host_canon = _canonical_anchors(host_anchors)
    out = []
    for s_name, s_anchor in self_canon:
        if s_anchor.kind not in _CURVED_KINDS:
            continue
        for h_name, h_anchor in host_canon:
            if h_anchor.kind != s_anchor.kind:
                continue
            reasons = diagnose_match_failure(s_anchor, h_anchor)
            if reasons:
                out.append((s_name, h_name, reasons))
    return out


def same_side_wall_candidates(self_anchors, host_anchors):
    """Return ``[(self_name, host_name, kind, inner_flag), ...]`` for
    pairs of curved anchors that describe **the same surface from the
    same side** — same axis line (or sphere center), same radii, same
    ``inner`` flag, axial coincidence (overlap for cylindrical; strict
    match for conical / meridional).

    This is the "two parts whose surfaces are literally the same"
    case: telescoping same-OD tubes, two coincident spheres of equal
    radius, end-to-end-but-overlapping cones with identical r1/r2.
    Plain ``union()`` handles these — there's no seam to clean up.
    ``fuse`` rightly rejects (the ``compatible_inner_flags`` rule is
    for *concentric* contact, where one side is bore and one is
    outer), but the user needs to be told ``fuse`` isn't what they
    want here.

    Called from the zero-match branch of ``_resolve_fuse_match`` to
    produce a specific "use union()" hint, suppressing the
    bridge-case hint (which would otherwise fire on bbox face anchors
    incidentally landing on the curved wall).
    """
    self_canon = _canonical_anchors(self_anchors)
    host_canon = _canonical_anchors(host_anchors)
    out = []
    for s_name, s_anchor in self_canon:
        if s_anchor.kind not in _CURVED_KINDS:
            continue
        for h_name, h_anchor in host_canon:
            if bool(s_anchor.inner) != bool(h_anchor.inner):
                continue
            if not _is_same_curved_surface(s_anchor, h_anchor):
                continue
            out.append((s_name, h_name, s_anchor.kind, bool(s_anchor.inner)))
    return out
