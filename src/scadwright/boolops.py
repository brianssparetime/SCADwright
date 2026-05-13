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


def fuse(
    a: Node, b: Node,
    *,
    on: str,
    using_anchor: str,
    bond: str | None = None,
    bridge: bool = False,
    eps_overlap: bool = True,
    eps: float | None = None,
) -> Union:
    """Combine ``a`` and ``b`` at coincident anchors.

    ``using_anchor`` names an anchor on ``a``; ``on`` names an anchor on
    ``b``. The two anchors' positions are aligned; the framework adds a
    small overlap that keeps a union manifold-clean against OpenSCAD's
    preview renderer.

    The default (``bond=None``, ``bridge=False``) runs the planar cascade:
    local face extension if both anchors are planar, otherwise raises.
    On a convex-outer curved host without ``bridge=True``, the call raises
    and points at ``bridge=True``.

    - ``bond="overlap"`` — local face extension only (parametric
      ``fuse_extend`` first, cross-section fallback). Preserves the
      user-facing dimensions of the extended side. Raises if either
      anchor is non-planar.
    - ``bond="shift"`` — translate ``a`` by ``eps`` along the contact
      normal. Always succeeds; the entire shape moves by eps.
    - ``bridge=True`` — structural bridge for a convex-outer curved
      host on either ``a`` or ``b``. The default ``eps_overlap=True``
      adds an ``eps`` overlap on the peg side (matching today's planar
      ``fuse=True`` behavior, built into the bridge); pass
      ``eps_overlap=False`` for a flush bridge with no overlap. Raises
      if neither side is a qualifying host or if normals aren't coaxial.

    The ``eps_overlap`` parameter is the standalone analog of
    ``attach()``'s ``fuse=`` — same toggle, renamed to avoid shadowing
    the function name.

    Symmetric side selection on ``bond="overlap"``: whichever of ``a``
    and ``b`` has a parametric extension lever wins; ties broken by
    simpler output.

    ``disable_eps_fuse()`` collapses eps to zero — ``eps_overlap``
    becomes False, ``bond=`` is treated as None, and a bridge's
    peg-side eps slice is dropped. The bridge geometry itself persists
    (it's structural, not eps).

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
    from scadwright.errors import ValidationError

    loc = SourceLocation.from_caller()
    if eps is None:
        from scadwright.api.tolerances import default_eps
        eps = default_eps()
    bond = _validate_bond_value(bond, loc, context="fuse")
    if bond is not None and bridge:
        raise ValidationError(
            f"fuse: bond={bond!r} controls the planar eps mechanism and "
            f"doesn't combine with bridge=True (the curved-host structural "
            f"fill). Pass one or the other, not both.",
            source_location=loc,
        )
    if bond is not None and not eps_overlap:
        raise ValidationError(
            f"fuse: eps_overlap=False contradicts bond={bond!r}. Drop "
            f"bond= to get exact-contact union, or keep bond= with the "
            f"default eps_overlap=True.",
            source_location=loc,
        )
    a_anchor = _resolve_attach_anchor(a, using_anchor, "a", loc)
    b_anchor = _resolve_attach_anchor(b, on, "b", loc)

    # disable_eps_fuse() collapses eps to zero: eps_overlap becomes
    # False, bond is dropped, and the bridge's peg-side slice goes
    # away. Bridge geometry itself still builds.
    if not fuse_enabled():
        eps_overlap = False
        bond = None

    if bridge:
        return _dispatch_bridge_symmetric(
            a, a_anchor, b, b_anchor, eps, loc, eps_overlap=eps_overlap,
        )

    if bond == "overlap":
        return _dispatch_overlap_symmetric(a, a_anchor, b, b_anchor, eps, loc)
    if bond == "shift":
        shift = _shift_for_anchors(a_anchor, b_anchor, eps_overlap, eps)
        placed_a = Translate(v=shift, child=a, source_location=loc)
        return union(placed_a, b)

    if not eps_overlap:
        # Exact-contact union (under disable_eps_fuse() or eps_overlap=False).
        shift = _shift_for_anchors(a_anchor, b_anchor, False, eps)
        placed_a = Translate(v=shift, child=a, source_location=loc)
        return union(placed_a, b)

    # bond=None, eps_overlap=True: smart cascade (overlap or raise).
    return _dispatch_smart_cascade_fuse(a, a_anchor, b, b_anchor, eps, loc)


__all__ = ["union", "difference", "intersection", "hull", "minkowski", "fuse"]
