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


def fuse(a: Node, b: Node, *, on: str, at: str, bond: str | None = None, eps: float = 0.01) -> Union:
    """Combine ``a`` and ``b`` at coincident anchors with a small overlap.

    ``at`` names an anchor on ``a``; ``on`` names an anchor on ``b``.
    The two anchors' positions are aligned (no shift); the framework
    adds the small overlap that keeps a union manifold-clean against
    OpenSCAD's preview renderer.

    The default (``bond=None``) runs the smart cascade: bridge if either
    side is a convex-outer curved host, otherwise local face extension
    if both anchors are planar, otherwise the bilateral shift. Pass
    ``bond=`` for explicit control:

    - ``bond="overlap"`` — local face extension only (parametric
      ``fuse_extend`` first, cross-section fallback). Preserves the
      user-facing dimensions of the extended side. Raises if either
      anchor is non-planar.
    - ``bond="bridge"`` — inscription bridge for a curved convex-outer
      host on either ``a`` or ``b``. Raises if neither side is a
      qualifying host or if the contact normals aren't coaxial.
    - ``bond="shift"`` — translate ``a`` by ``eps`` along the contact
      normal. Always succeeds; the entire shape moves by eps.

    Symmetric side selection on ``bond="overlap"``: whichever of ``a``
    and ``b`` has a parametric extension lever wins; ties broken by
    simpler output.

    ``disable_eps_fuse()`` short-circuits everything to exact-contact
    union — even explicit ``bond=...`` values collapse, by design.

    Returns ``union(...)``.
    """
    from scadwright.api.fuse_mode import fuse_enabled
    from scadwright.ast.placement import (
        _dispatch_bridge_symmetric,
        _dispatch_overlap_symmetric,
        _dispatch_smart_cascade_fuse,
        _resolve_attach_anchor,
        _shift_for_anchors,
        _validate_bond_value,
    )
    from scadwright.ast.transforms import Translate

    loc = SourceLocation.from_caller()
    bond = _validate_bond_value(bond, loc, context="fuse")
    a_anchor = _resolve_attach_anchor(a, at, "a", loc)
    b_anchor = _resolve_attach_anchor(b, on, "b", loc)

    # disable_eps_fuse() short-circuits everything to exact contact.
    if not fuse_enabled():
        shift = _shift_for_anchors(a_anchor, b_anchor, False, eps)
        placed_a = Translate(v=shift, child=a, source_location=loc)
        return union(placed_a, b)

    if bond == "overlap":
        return _dispatch_overlap_symmetric(a, a_anchor, b, b_anchor, eps, loc)
    if bond == "bridge":
        return _dispatch_bridge_symmetric(a, a_anchor, b, b_anchor, eps, loc)
    if bond == "shift":
        shift = _shift_for_anchors(a_anchor, b_anchor, True, eps)
        placed_a = Translate(v=shift, child=a, source_location=loc)
        return union(placed_a, b)

    # bond=None: smart cascade.
    return _dispatch_smart_cascade_fuse(a, a_anchor, b, b_anchor, eps, loc)


__all__ = ["union", "difference", "intersection", "hull", "minkowski", "fuse"]
