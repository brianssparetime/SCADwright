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

    def fuse_extend(self, anchor, eps: float):
        """Recurse into the child with the anchor inverse-translated.

        The anchor is given in the wrapper's local frame (after the
        translate is applied). To pass it to the child, undo the
        translate; if the child can extend along that anchor, re-wrap
        the extended child in the same translate.
        """
        from dataclasses import replace
        inverse_anchor = replace(
            anchor,
            position=(
                anchor.position[0] - self.v[0],
                anchor.position[1] - self.v[1],
                anchor.position[2] - self.v[2],
            ),
        )
        extended_child = self.child.fuse_extend(inverse_anchor, eps)
        if extended_child is None:
            return None
        return Translate(
            v=self.v,
            child=extended_child,
            source_location=self.source_location,
        )


@dataclass(frozen=True)
class Rotate(Node):
    """Either Euler (angles set) or axis-angle (a and v set). Emitter picks based on which is non-None."""

    child: Node
    angles: tuple[float, float, float] | None = None
    a: float | None = None
    v: tuple[float, float, float] | None = None

    def fuse_extend(self, anchor, eps: float):
        """Recurse into the child with the anchor inverse-rotated.

        The anchor is given in the wrapper's local frame (after the
        rotation is applied). To pass it to the child, undo the rotation
        on both position and normal; if the child can extend, re-wrap
        in the same Rotate.
        """
        from dataclasses import replace
        from scadwright.matrix import to_matrix
        inv = to_matrix(self).invert()
        inverse_anchor = replace(
            anchor,
            position=inv.apply_point(anchor.position),
            normal=inv.apply_vector(anchor.normal),
        )
        extended_child = self.child.fuse_extend(inverse_anchor, eps)
        if extended_child is None:
            return None
        return Rotate(
            child=extended_child,
            angles=self.angles,
            a=self.a,
            v=self.v,
            source_location=self.source_location,
        )


@dataclass(frozen=True)
class Scale(Node):
    factor: tuple[float, float, float]
    child: Node


@dataclass(frozen=True)
class Mirror(Node):
    normal: tuple[float, float, float]
    child: Node

    def fuse_extend(self, anchor, eps: float):
        """Recurse into the child with the anchor mirrored.

        Mirror is its own inverse (M @ M == identity), so applying it
        again gives child-frame coordinates. If the child can extend,
        re-wrap in the same Mirror.
        """
        from dataclasses import replace
        from scadwright.matrix import to_matrix
        m = to_matrix(self)
        inverse_anchor = replace(
            anchor,
            position=m.apply_point(anchor.position),
            normal=m.apply_vector(anchor.normal),
        )
        extended_child = self.child.fuse_extend(inverse_anchor, eps)
        if extended_child is None:
            return None
        return Mirror(
            normal=self.normal,
            child=extended_child,
            source_location=self.source_location,
        )


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


@dataclass(frozen=True)
class WithAnchor(Node):
    """Metadata-only wrapper that publishes a named anchor on its child.

    Lets users add a custom anchor to any Node without wrapping in a
    Component. The wrapper is transparent to bbox and emit — the only
    thing it changes is the anchor dict reported by ``get_node_anchors``.

    The anchor's position and normal are in the wrapped child's local
    frame; spatial transforms above the wrapper compose normally.
    """

    child: Node
    anchor_name: str
    anchor: "Anchor"  # type: ignore[name-defined]

    def fuse_extend(self, anchor, eps: float):
        """Pass through to child; re-wrap the extended result.

        WithAnchor is metadata-only — the anchor space is the child's
        own local frame. Recursing lets parametric extension reach the
        underlying primitive (Cube/Cylinder/LinearExtrude) and keeps
        the named anchor attached to the result.
        """
        extended_child = self.child.fuse_extend(anchor, eps)
        if extended_child is None:
            return None
        return WithAnchor(
            child=extended_child,
            anchor_name=self.anchor_name,
            anchor=self.anchor,
            source_location=self.source_location,
        )
