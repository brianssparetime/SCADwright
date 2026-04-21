"""Higher-order composition helpers: multi_hull, sequential_hull, linear/rotate/mirror_copy, halve."""

from __future__ import annotations

from scadwright.api._vectors import _as_vec3
from scadwright.ast.base import Node, SourceLocation
from scadwright.ast.csg import Hull, Union
from scadwright.ast.transforms import Mirror, Rotate, Translate
from scadwright.boolops import _flatten_csg_args
from scadwright.errors import ValidationError


def mirror_copy(*args, normal=None) -> Union:
    """Keep all children AND a mirrored copy of the group.

    Two equivalent forms:

        mirror_copy([1, 0, 0], a, b, c)        # SCAD-style: normal first, then shapes
        mirror_copy(a, b, c, normal=[1, 0, 0]) # kwargs-style: shapes first, keyword normal

    The second form is recommended for new code — it reads "these shapes,
    mirrored across this plane" and catches typos in the kwarg name.
    """
    loc = SourceLocation.from_caller()

    # Disambiguate positional vs kwarg form:
    # - If `normal=` kwarg is given: all positional args are children.
    # - Otherwise: first positional arg is the normal vector, rest are children.
    if normal is not None:
        if not args:
            raise ValidationError(
                "mirror_copy: pass at least one shape",
                source_location=loc,
            )
        children = args
        normal_val = normal
    else:
        if len(args) < 2:
            raise ValidationError(
                "mirror_copy: expected (normal, *shapes) or (*shapes, normal=...)",
                source_location=loc,
            )
        normal_val, *children = args

    normal_vec = _as_vec3(normal_val, name="mirror_copy normal", default_scalar_broadcast=False)
    flat = _flatten_csg_args(children, "mirror_copy")
    mirrored = tuple(
        Mirror(normal=normal_vec, child=c, source_location=loc) for c in flat
    )
    return Union(children=flat + mirrored, source_location=loc)


def rotate_copy(angle: float, *children, n: int = 4, axis=(0.0, 0.0, 1.0)) -> Union:
    """Rotate the group `n` total times around `axis` by `angle` degrees per step."""
    loc = SourceLocation.from_caller()
    axis_vec = _as_vec3(axis, name="rotate_copy axis", default_scalar_broadcast=False)
    flat = _flatten_csg_args(children, "rotate_copy")
    out: list[Node] = list(flat)
    for i in range(1, int(n)):
        for c in flat:
            out.append(
                Rotate(child=c, a=float(angle) * i, v=axis_vec, source_location=loc)
            )
    return Union(children=tuple(out), source_location=loc)


def linear_copy(offset, n: int, *children) -> Union:
    """Translate the group `n` total times by `offset` per step."""
    loc = SourceLocation.from_caller()
    off = _as_vec3(offset, name="linear_copy offset", default_scalar_broadcast=False)
    flat = _flatten_csg_args(children, "linear_copy")
    out: list[Node] = list(flat)
    for i in range(1, int(n)):
        for c in flat:
            out.append(
                Translate(
                    v=(off[0] * i, off[1] * i, off[2] * i),
                    child=c,
                    source_location=loc,
                )
            )
    return Union(children=tuple(out), source_location=loc)


def multi_hull(first: Node, *others) -> Union:
    """Hull connecting `first` to each of `others`. Then unioned.

    Each `hull(first, other_i)` produces a swept volume between two shapes.
    Useful for fan-shaped bridges from a hub to many endpoints.
    """
    loc = SourceLocation.from_caller()
    flat_others = _flatten_csg_args(others, "multi_hull")
    if not isinstance(first, Node):
        raise ValidationError(
            f"multi_hull first arg must be a Node, got {type(first).__name__}",
            source_location=loc,
        )
    pieces = tuple(
        Hull(children=(first, other), source_location=loc) for other in flat_others
    )
    return Union(children=pieces, source_location=loc)


def sequential_hull(*children) -> Union:
    """Chain of hulls between consecutive children: hull(c0, c1), hull(c1, c2), ..."""
    loc = SourceLocation.from_caller()
    flat = _flatten_csg_args(children, "sequential_hull")
    if len(flat) < 2:
        raise ValidationError(
            "sequential_hull requires at least 2 operands",
            source_location=loc,
        )
    pieces = tuple(
        Hull(children=(a, b), source_location=loc)
        for a, b in zip(flat, flat[1:])
    )
    return Union(children=pieces, source_location=loc)


def halve(node: Node, v=None, *, x: float = 0, y: float = 0, z: float = 0, size: float = 1e4) -> Node:
    """Standalone form of `node.halve(v, ...)`. See `Node.halve` for details."""
    return node.halve(v, x=x, y=y, z=z, size=size)


__all__ = [
    "multi_hull",
    "sequential_hull",
    "linear_copy",
    "rotate_copy",
    "mirror_copy",
    "halve",
]
