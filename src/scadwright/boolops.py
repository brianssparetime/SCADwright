"""Boolean and set-like composition operators: union, difference, intersection, hull, minkowski."""

from __future__ import annotations

from scadwright.ast.base import Node, SourceLocation
from scadwright.ast.csg import Difference, Hull, Intersection, Minkowski, Union
from scadwright.errors import ValidationError


def _flatten_csg_args(args, op_name: str) -> tuple[Node, ...]:
    """Flatten CSG args: accept Nodes and one-level-deep iterables of Nodes.

    Shared with composition_helpers for the same flattening contract.
    """
    out: list[Node] = []
    for a in args:
        if isinstance(a, Node):
            out.append(a)
        else:
            try:
                items = list(a)
            except TypeError:
                loc = SourceLocation.from_caller()
                raise ValidationError(
                    f"{op_name} argument must be a Node or iterable of Nodes, got {type(a).__name__}",
                    source_location=loc,
                ) from None
            for item in items:
                if not isinstance(item, Node):
                    loc = SourceLocation.from_caller()
                    raise ValidationError(
                        f"{op_name}: iterables are flattened one level only; "
                        f"found nested {type(item).__name__} inside the outer sequence. "
                        f"Pass nodes directly or as a single flat iterable.",
                        source_location=loc,
                    )
                out.append(item)
    if not out:
        loc = SourceLocation.from_caller()
        raise ValidationError(
            f"{op_name} requires at least one operand",
            source_location=loc,
        )
    return tuple(out)


def union(*args) -> Union:
    return Union(
        children=_flatten_csg_args(args, "union"),
        source_location=SourceLocation.from_caller(),
    )


def difference(*args) -> Difference:
    return Difference(
        children=_flatten_csg_args(args, "difference"),
        source_location=SourceLocation.from_caller(),
    )


def intersection(*args) -> Intersection:
    return Intersection(
        children=_flatten_csg_args(args, "intersection"),
        source_location=SourceLocation.from_caller(),
    )


def hull(*args) -> Hull:
    return Hull(
        children=_flatten_csg_args(args, "hull"),
        source_location=SourceLocation.from_caller(),
    )


def minkowski(*args) -> Minkowski:
    return Minkowski(
        children=_flatten_csg_args(args, "minkowski"),
        source_location=SourceLocation.from_caller(),
    )


def fuse(a: Node, b: Node, *, on: str, at: str, eps: float = 0.01) -> Union:
    """Combine ``a`` and ``b`` at coincident anchors with a small overlap.

    ``at`` names an anchor on ``a``; ``on`` names an anchor on ``b``.
    The two anchors' positions are aligned (no shift), and one side is
    locally extended by ``eps`` along its anchor's normal so the union
    stays manifold-clean against OpenSCAD's preview renderer.

    Local extension preserves the user-facing dimensions and anchors of
    the extended shape elsewhere — only the contact face moves. Symmetric
    side selection: if ``a`` supports local extension along ``at``, that
    side is extended; otherwise ``b`` is extended along ``on``.

    When neither side supports local extension (the anchors aren't
    planar, or the shapes lack a parametric extension lever — e.g. raw
    Polyhedra, complex CSG results), falls back to translating ``a`` by
    ``eps`` along ``b``'s anchor normal so they overlap. This matches
    the legacy ``attach(fuse=True)`` behavior.

    Returns ``union(extended_a, b)`` (or the symmetric / fallback form).
    """
    from scadwright.api.fuse_mode import fuse_enabled
    from scadwright.ast.placement import _resolve_attach_anchor, _shift_for_anchors
    from scadwright.ast.transforms import Translate

    loc = SourceLocation.from_caller()
    a_anchor = _resolve_attach_anchor(a, at, "a", loc)
    b_anchor = _resolve_attach_anchor(b, on, "b", loc)

    # Scope-wide ``disable_eps_fuse()``: skip all fuse machinery, do
    # exact-contact union at the unshifted anchor positions.
    if not fuse_enabled():
        shift = _shift_for_anchors(a_anchor, b_anchor, False, eps)
        placed_a = Translate(v=shift, child=a, source_location=loc)
        return union(placed_a, b)

    # Curved-host bridge dispatch. By convention ``b`` is the host (the
    # ``on`` side); if b's on-anchor is convex-outer curved, bridge from
    # a (the peg). Concave inner falls through (natural inscription);
    # curved a with planar b also falls through (caller can swap args).
    from scadwright.ast._fuse_bridge import build_curved_bridge, coaxial_normals
    b_curved = b_anchor.kind in ("cylindrical", "conical", "spherical")
    b_inner = bool(b_anchor.surface_param("inner", default=False))
    if b_curved and not b_inner:
        if not coaxial_normals(a_anchor.normal, b_anchor.normal):
            from scadwright.errors import ValidationError
            raise ValidationError(
                f"fuse on a {b_anchor.kind} host (b) requires coaxial "
                f"normals (a's at-anchor anti-parallel to b's on-anchor). "
                f"Got a normal {a_anchor.normal}, b normal {b_anchor.normal}.",
                source_location=loc,
            )
        unfused_shift = _shift_for_anchors(a_anchor, b_anchor, False, eps)
        bridge = build_curved_bridge(a, a_anchor, b, b_anchor, unfused_shift, eps)
        if bridge is not None:
            placed_a = Translate(v=unfused_shift, child=a, source_location=loc)
            return union(placed_a, b, bridge)

    # Local extension only when both anchors are planar.
    if a_anchor.kind == "planar" and b_anchor.kind == "planar":
        # Tier 1: parametric extension wins on either side. Pick the
        # side with the cleaner output (no Translate wrapper).
        extended_a = a.fuse_extend(a_anchor, eps)
        extended_b = b.fuse_extend(b_anchor, eps)
        chosen = _pick_simpler_extension(extended_a, extended_b)
        if chosen == "a":
            shift = _shift_for_anchors(a_anchor, b_anchor, False, eps)
            placed_a = Translate(v=shift, child=extended_a, source_location=loc)
            return union(placed_a, b)
        if chosen == "b":
            shift = _shift_for_anchors(a_anchor, b_anchor, False, eps)
            placed_a = Translate(v=shift, child=a, source_location=loc)
            return union(placed_a, extended_b)

        # Tier 2: neither side has parametric extension. Try the
        # generic cross-section path on each side. cross_section_extend
        # raises on degenerate contact, so a passing call is non-None.
        extended_a = a.cross_section_extend(a_anchor, eps)
        extended_b = b.cross_section_extend(b_anchor, eps)
        chosen = _pick_simpler_extension(extended_a, extended_b)
        if chosen == "a":
            shift = _shift_for_anchors(a_anchor, b_anchor, False, eps)
            placed_a = Translate(v=shift, child=extended_a, source_location=loc)
            return union(placed_a, b)
        if chosen == "b":
            shift = _shift_for_anchors(a_anchor, b_anchor, False, eps)
            placed_a = Translate(v=shift, child=a, source_location=loc)
            return union(placed_a, extended_b)
        # Both cross_section_extend calls returned None (defensive;
        # should be unreachable for planar anchors). Fall through.

    # Shift fallback: non-planar anchors land here.
    shift = _shift_for_anchors(a_anchor, b_anchor, True, eps)
    placed_a = Translate(v=shift, child=a, source_location=loc)
    return union(placed_a, b)


def _pick_simpler_extension(extended_a, extended_b):
    """Pick the side whose fuse_extend output is simpler. Returns 'a',
    'b', or None (neither qualified)."""
    if extended_a is None and extended_b is None:
        return None
    if extended_a is None:
        return "b"
    if extended_b is None:
        return "a"
    # Both qualified. Prefer the one that's a leaf (no Translate
    # wrapper); when both are leaves or both are wrapped, prefer ``a``.
    from scadwright.ast.transforms import Translate as _Translate
    a_wrapped = isinstance(extended_a, _Translate)
    b_wrapped = isinstance(extended_b, _Translate)
    if a_wrapped and not b_wrapped:
        return "b"
    return "a"


__all__ = ["union", "difference", "intersection", "hull", "minkowski", "fuse"]
