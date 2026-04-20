"""Transform AST nodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from scadwright.ast.base import Node

if TYPE_CHECKING:
    from scadwright.matrix import Matrix


@dataclass(frozen=True)
class Translate(Node):
    v: tuple[float, float, float]
    child: Node


@dataclass(frozen=True)
class Rotate(Node):
    """Either Euler (angles set) or axis-angle (a and v set). Emitter picks based on which is non-None."""

    child: Node
    angles: tuple[float, float, float] | None = None
    a: float | None = None
    v: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class Scale(Node):
    factor: tuple[float, float, float]
    child: Node


@dataclass(frozen=True)
class Mirror(Node):
    normal: tuple[float, float, float]
    child: Node


@dataclass(frozen=True)
class Color(Node):
    c: str | tuple[float, ...]
    child: Node
    alpha: float = 1.0


@dataclass(frozen=True)
class Resize(Node):
    new_size: tuple[float, float, float]
    child: Node
    auto: tuple[bool, bool, bool] = (False, False, False)


@dataclass(frozen=True)
class PreviewModifier(Node):
    """OpenSCAD preview-modifier sigil wrapping a child.

    mode:
        "highlight"  -> '#' (debug highlight; child rendered translucent red)
        "background" -> '%' (child rendered but excluded from final output)
        "disable"    -> '*' (child treated as if absent)
        "only"       -> '!' (render ONLY this subtree; ignore siblings)
    """

    mode: str
    child: Node


@dataclass(frozen=True)
class MultMatrix(Node):
    """Apply an arbitrary 4x4 transform matrix to a child."""

    matrix: "Matrix"
    child: Node


@dataclass(frozen=True)
class Projection(Node):
    """3D -> 2D: flatten onto XY (cut=False) or cross-section at z=0 (cut=True)."""

    child: Node
    cut: bool = False


@dataclass(frozen=True)
class ForceRender(Node):
    """SCAD's render(convexity=...) — forces full CGAL rendering for a subtree.

    Debug/performance tool. No effect on emitted geometry.
    """

    child: Node
    convexity: int | None = None


@dataclass(frozen=True)
class Echo(Node):
    """SCAD's echo(...). Prints at SCAD evaluation time.

    `values` is a tuple of (name, value) pairs. name is None for positional
    args, a string for kwargs. `child` is optional: None → bare statement;
    present → wraps a subtree.
    """

    values: tuple
    child: Node | None = None


@dataclass(frozen=True)
class Offset(Node):
    """2D offset: expands or contracts a 2D shape.

    Exactly one of r or delta is set. chamfer only applies with delta.
    """

    child: Node
    r: float | None = None
    delta: float | None = None
    chamfer: bool = False
    fn: float | None = None
    fa: float | None = None
    fs: float | None = None
