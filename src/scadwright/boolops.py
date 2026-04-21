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


__all__ = ["union", "difference", "intersection", "hull", "minkowski"]
