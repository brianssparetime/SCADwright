"""Rigid and cosmetic transforms + custom-transform extension API.

Two surfaces live here:

1. **Standalone transform functions** — subject-first functional form of the
   chained methods on Node. Both forms produce the same AST:

       from scadwright.transforms import translate, rotate
       part = translate(rotate(cube(10), [0, 0, 45]), [5, 0, 0])

       # equivalently, chained:
       part = cube(10).rotate([0, 0, 45]).translate([5, 0, 0])

2. **Custom-transform registry** — `transform` decorator + friends for
   registering user-defined transforms.
"""

from scadwright._custom_transforms.base import (
    Transform,
    get_transform,
    list_transforms,
    transform,
)
from scadwright.ast.base import Node


def translate(node: Node, v=None, *, x: float = 0, y: float = 0, z: float = 0) -> Node:
    return node.translate(v, x=x, y=y, z=z)


def rotate(
    node: Node,
    a=None,
    v=None,
    *,
    x: float = 0,
    y: float = 0,
    z: float = 0,
    angle=None,
    axis=None,
) -> Node:
    return node.rotate(a, v, x=x, y=y, z=z, angle=angle, axis=axis)


def scale(node: Node, v=None, *, x: float = 1, y: float = 1, z: float = 1) -> Node:
    return node.scale(v, x=x, y=y, z=z)


def mirror(node: Node, v=None, *, x: float = 0, y: float = 0, z: float = 0) -> Node:
    return node.mirror(v, x=x, y=y, z=z)


def color(node: Node, c, alpha: float = 1.0) -> Node:
    return node.color(c, alpha=alpha)


def resize(node: Node, v, *, auto=False) -> Node:
    return node.resize(v, auto=auto)


def offset(
    node: Node,
    *,
    r: float | None = None,
    delta: float | None = None,
    chamfer: bool = False,
    fn: float | None = None,
    fa: float | None = None,
    fs: float | None = None,
) -> Node:
    return node.offset(r=r, delta=delta, chamfer=chamfer, fn=fn, fa=fa, fs=fs)


def highlight(node: Node) -> Node:
    return node.highlight()


def background(node: Node) -> Node:
    return node.background()


def disable(node: Node) -> Node:
    return node.disable()


def only(node: Node) -> Node:
    return node.only()


def multmatrix(node: Node, matrix) -> Node:
    return node.multmatrix(matrix)


def projection(node: Node, *, cut: bool = False) -> Node:
    return node.projection(cut=cut)


__all__ = [
    "translate",
    "rotate",
    "scale",
    "mirror",
    "color",
    "resize",
    "offset",
    "multmatrix",
    "projection",
    "highlight",
    "background",
    "disable",
    "only",
    "Transform",
    "transform",
    "get_transform",
    "list_transforms",
]
