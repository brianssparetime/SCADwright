"""Parallel structure walker for morph(): pair animated leaves across two
variant ASTs while preserving the variants' CSG structure.

The walker descends both trees in lockstep. Structurally-equivalent nodes
(same type, same arity for CSG containers) match; structural mismatches
raise. As we descend:

- **Spatial transforms** (Translate, Rotate, Scale, Mirror, MultMatrix)
  accumulate into a per-leaf transform matrix. They will be absorbed
  into the animated chain at emit time, not preserved as bare transforms.
- **Structural nodes** (Union, Difference, Intersection, Hull, Minkowski)
  reset the accumulator for each child. They stay in the emit, with their
  children replaced by animated subtrees.
- **Decorations** (Color, WithAnchor, PreviewModifier, ForceRender,
  Resize, Projection, Offset, Echo) act as boundaries too — they preserve
  themselves in the emit and reset the accumulator. ``Color(red,
  Translate(a, self.box))`` becomes ``Color(red, animated_chain(box))``.
- **Components and primitives** are leaves. Components pair across
  variants by Python ``id`` (the same instance backs both variants when
  declared as a class attribute on the Design). Inline primitives (Cube,
  Sphere, Cylinder, etc.) pair by ``tree_hash``; their transform stacks
  may differ, in which case the primitive animates.

For each animated leaf, the walker records the deepest "substitution
root" — the topmost spatial-transform ancestor in the unbroken transform
chain directly above the leaf (or the leaf itself if there are no spatial
transforms in that chain). At emit time, the substitution root in
variant A's tree gets replaced with the animated chain.

Errors raise ``ValidationError`` with the wording referenced by the
user-facing docs for the morph feature's hard limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from scadwright.errors import ValidationError
from scadwright.hashing import tree_hash
from scadwright.matrix import Matrix, to_matrix

if TYPE_CHECKING:
    from scadwright.ast.base import Node
    from scadwright.component.base import Component


_MATRIX_EPS = 1e-9


@dataclass(frozen=True)
class AnimatedLeaf:
    """One animated leaf — either a Component (paired by id) or an inline
    primitive (paired by tree_hash + structural position).

    ``leaf`` is the original AST node from variant A; ``substitution_root``
    is the topmost spatial-transform ancestor in variant A's tree (or
    ``leaf`` itself if no spatial wrapper sits directly above it). Emit
    replaces ``substitution_root`` with the animated chain built from
    ``M_a`` / ``M_b``.

    ``M_a`` and ``M_b`` are the composed spatial transforms between the
    substitution root's parent (a structural node or root) and the leaf
    — i.e., the per-variant pose contribution that the animated chain
    must reproduce at ``$t=0`` and ``$t=1``.
    """

    leaf: "Node"
    substitution_root: "Node"
    M_a: Matrix
    M_b: Matrix
    display_name: str


@dataclass(frozen=True)
class MorphPlan:
    """Walker output. ``tree_a`` is variant A's AST (the structural
    template). ``leaves`` lists every animated leaf, each carrying the
    information needed to build its animated chain.

    Static parts (Components or primitives whose ``M_a`` equals ``M_b``)
    do not appear in ``leaves`` — they remain in ``tree_a`` unchanged.
    """

    tree_a: "Node"
    leaves: tuple[AnimatedLeaf, ...]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_id_to_name(design_instance) -> dict[int, str]:
    from scadwright.component.base import Component
    out: dict[int, str] = {}
    for klass in type(design_instance).__mro__:
        for name, value in vars(klass).items():
            if isinstance(value, Component):
                out.setdefault(id(value), name)
    return out


def _matrices_close(a: Matrix, b: Matrix, eps: float = _MATRIX_EPS) -> bool:
    for ra, rb in zip(a.elements, b.elements):
        for x, y in zip(ra, rb):
            if abs(x - y) > eps:
                return False
    return True


def _scale_close(a: tuple, b: tuple, eps: float = _MATRIX_EPS) -> bool:
    return all(abs(x - y) <= eps for x, y in zip(a, b))


def _is_uniform_scale(s: tuple[float, float, float], eps: float = _MATRIX_EPS) -> bool:
    return abs(s[0] - s[1]) <= eps and abs(s[1] - s[2]) <= eps


def _validate_pair(
    leaf, M_a: Matrix, M_b: Matrix, display_name: str, label_hint: str = "",
) -> None:
    """Run mirror and non-uniform-scale checks on a paired leaf's transforms."""
    try:
        M_diff = M_b @ M_a.invert()
    except ValueError as exc:
        raise ValidationError(
            f"morph: part {display_name!r}{label_hint} has a singular "
            f"transform on the start side; cannot compute the difference. "
            f"Underlying: {exc}"
        )
    det = M_diff.determinant()
    if det < -_MATRIX_EPS:
        raise ValidationError(
            f"morph: part {display_name!r}{label_hint} uses a mirror on one "
            f"side but not the other. Mirrors are reflections (det = -1) "
            f"and can't be smoothly interpolated.\n"
            f"  Replace .flip(...) with .rotate([180, 0, 0]) (or the "
            f"equivalent rotation) — same final pose, and the morph will "
            f"animate it as a single hinge swing."
        )
    s_a = M_a.decompose_scale()
    s_b = M_b.decompose_scale()
    if not _scale_close(s_a, s_b):
        if not (_is_uniform_scale(s_a) and _is_uniform_scale(s_b)):
            raise ValidationError(
                f"morph: part {display_name!r}{label_hint} has non-uniform "
                f"scale that differs between variants.\n"
                f"  start scale: {tuple(round(v, 6) for v in s_a)}\n"
                f"  end scale:   {tuple(round(v, 6) for v in s_b)}\n"
                f"  Only uniform scale changes can be animated; for shape "
                f"morphing, define separate parts."
            )


# Type sets for the walker. Decorations preserve themselves and act as
# boundaries; spatial transforms accumulate into M_a.

def _import_ast_types():
    """Late import to avoid circular dependency at module-load time."""
    from scadwright.ast.csg import (
        Difference, Hull, Intersection, Minkowski, Union,
    )
    from scadwright.ast.transforms import (
        Color, Echo, ForceRender, Mirror, MultMatrix, Offset,
        PreviewModifier, Projection, Resize, Rotate, Scale, Translate,
        WithAnchor,
    )
    from scadwright.component.base import Component
    return {
        "Component": Component,
        "spatial_transforms": (Translate, Rotate, Scale, Mirror, MultMatrix),
        "structural": (Union, Difference, Intersection, Hull, Minkowski),
        "decorations": (
            Color, WithAnchor, PreviewModifier, ForceRender,
            Resize, Projection, Offset, Echo,
        ),
    }


def _node_kind(node, types) -> str:
    """Return one of: 'component', 'structural', 'spatial', 'decoration',
    'primitive'. Used for structural-match decisions."""
    if isinstance(node, types["Component"]):
        return "component"
    if isinstance(node, types["structural"]):
        return "structural"
    if isinstance(node, types["spatial_transforms"]):
        return "spatial"
    if isinstance(node, types["decorations"]):
        return "decoration"
    return "primitive"


def _decoration_matches(node_a, node_b) -> tuple[bool, str]:
    """Two decoration nodes must carry the same metadata to align.

    Compares every dataclass field except ``child`` (recursed into
    elsewhere) and ``source_location`` (line-number drift isn't semantic).
    Works for any frozen-dataclass decoration node — Color, WithAnchor,
    PreviewModifier, ForceRender, Resize, Projection, Offset, Echo,
    or any new metadata wrapper added later.

    Returns ``(matches, reason_if_not)``. ``reason_if_not`` is empty
    when ``matches`` is True.
    """
    from dataclasses import fields, is_dataclass

    if type(node_a) is not type(node_b):
        return False, (
            f"different decoration types "
            f"({type(node_a).__name__} vs {type(node_b).__name__})"
        )
    if not is_dataclass(node_a):
        # Not a dataclass — type match is the strongest check we have.
        return True, ""
    cls_name = type(node_a).__name__
    for f in fields(node_a):
        if f.name in ("child", "source_location"):
            continue
        va = getattr(node_a, f.name)
        vb = getattr(node_b, f.name)
        if va != vb:
            return False, (
                f"different {cls_name}.{f.name} ({va!r} vs {vb!r})"
            )
    return True, ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def walk(tree_a, tree_b, design_instance) -> MorphPlan:
    """Parallel-walk both variant trees; produce a MorphPlan describing
    which leaves animate and at what transforms.

    Raises ``ValidationError`` for any structural mismatch or per-leaf
    constraint violation (mirror, non-uniform scale change).
    """
    types = _import_ast_types()
    id_to_name = _build_id_to_name(design_instance)

    leaves: list[AnimatedLeaf] = []

    def _structural_mismatch(node_a, node_b, why: str):
        # Detect the specific case of "one side has a decoration wrapper
        # (Color, anchors, Resize, etc.) and the other side has the bare
        # leaf at the same position." This is one of the easier mistakes
        # to make and the generic error doesn't quite say how to fix it.
        kind_a = _node_kind(node_a, types)
        kind_b = _node_kind(node_b, types)
        decoration_asymmetry = (
            (kind_a == "decoration" and kind_b in ("component", "primitive"))
            or (kind_b == "decoration" and kind_a in ("component", "primitive"))
        )
        if decoration_asymmetry:
            deco_node = node_a if kind_a == "decoration" else node_b
            deco_side = "start" if kind_a == "decoration" else "end"
            other_side = "end" if deco_side == "start" else "start"
            deco_name = type(deco_node).__name__
            return ValidationError(
                f"morph: decoration wrapper present in one variant only.\n"
                f"  {deco_side} has: {deco_name}(...) wrapping the leaf\n"
                f"  {other_side} has: the leaf with no wrapper\n"
                f"  Decorations (Color, WithAnchor, PreviewModifier, "
                f"ForceRender, Resize, etc.) are preserved through the "
                f"morph and must appear on both sides — they aren't "
                f"interpolated. Either add the same {deco_name}(...) "
                f"wrapper to the {other_side} variant, or remove it from "
                f"the {deco_side} variant."
            )
        return ValidationError(
            f"morph: variant ASTs differ in structure — {why}.\n"
            f"  start has: {type(node_a).__name__}\n"
            f"  end has:   {type(node_b).__name__}\n"
            f"  morph requires both variants to share the same CSG / "
            f"decoration skeleton; only the transforms above leaves "
            f"(Components, primitives) may differ."
        )

    def _walk(
        node_a, node_b,
        t_a: Matrix, t_b: Matrix,
        substitution_root_a,
        inside_resize: bool = False,
    ):
        """Parallel descent.

        ``t_a`` / ``t_b`` accumulate the composed spatial transform
        between the most-recent structural-or-decoration boundary and
        the current point. ``substitution_root_a`` is the topmost
        spatial-transform ancestor in variant A within the current
        contiguous transform chain (or None if the immediate parent is
        a structural or decoration node).

        ``inside_resize`` becomes True once descent crosses a ``Resize``
        wrapper; animated leaves below a Resize raise instead of being
        recorded. Resize is bbox-dependent — its scale factor is computed
        from the child's bbox at render time — so wrapping an animated
        subtree would make every frame recompute the scale, producing
        size-jitter as the part rotates / translates.
        """
        # Skip past spatial transforms on each side independently. This
        # lets `self.box` align with `Translate(5, self.box)` — the
        # transform on one side accumulates into t_b without requiring
        # the other side to have a matching wrapper. Mirrors are
        # spatial-transforms too; det < 0 in M_diff catches the mirror
        # error per-pair in _validate_pair.
        while isinstance(node_a, types["spatial_transforms"]):
            t_a = t_a @ to_matrix(node_a)
            if substitution_root_a is None:
                substitution_root_a = node_a
            node_a = node_a.child
        while isinstance(node_b, types["spatial_transforms"]):
            t_b = t_b @ to_matrix(node_b)
            node_b = node_b.child

        kind_a = _node_kind(node_a, types)
        kind_b = _node_kind(node_b, types)
        if kind_a != kind_b:
            raise _structural_mismatch(node_a, node_b, f"kind differs ({kind_a} vs {kind_b})")

        if kind_a == "component":
            # Same Component instance must back both sides.
            if id(node_a) != id(node_b):
                name_a = id_to_name.get(id(node_a), repr(node_a))
                name_b = id_to_name.get(id(node_b), repr(node_b))
                raise ValidationError(
                    f"morph: Component leaves differ at the same structural "
                    f"position. start has {name_a!r}, end has {name_b!r}. "
                    f"Both variants must reference the same Component instance "
                    f"(declared as a class attribute on the Design)."
                )
            display = id_to_name.get(id(node_a), f"<{type(node_a).__name__} (inline)>")
            sub_root = substitution_root_a if substitution_root_a is not None else node_a
            # Only emit an entry if the part actually animates.
            if not _matrices_close(t_a, t_b):
                if inside_resize:
                    raise ValidationError(
                        f"morph: part {display!r} animates inside a Resize() "
                        f"wrapper. Resize is bbox-dependent — its scale factor "
                        f"is computed from the child's bounding box at render "
                        f"time, so a Resize wrapping an animated part would "
                        f"recompute the scale every frame as the part rotates "
                        f"and translates, producing visible size-jitter.\n"
                        f"  Move the Resize outside the morph (apply it to the "
                        f"final unioned result), or drop the Resize and use "
                        f"Scale with explicit factors so the scale is constant."
                    )
                _validate_pair(node_a, t_a, t_b, display)
                leaves.append(AnimatedLeaf(
                    leaf=node_a, substitution_root=sub_root,
                    M_a=t_a, M_b=t_b, display_name=display,
                ))
            # else: static — original tree carries the leaf at its existing
            # transform stack. No substitution needed.
            return

        if kind_a == "primitive":
            # Inline primitive. Must match by tree_hash.
            if tree_hash(node_a) != tree_hash(node_b):
                raise ValidationError(
                    f"morph: inline primitive geometry differs at the same "
                    f"structural position.\n"
                    f"  start: {type(node_a).__name__}\n"
                    f"  end:   {type(node_b).__name__}\n"
                    f"  Inline primitives pair by structural position and "
                    f"tree_hash; their shape and parameters must match. "
                    f"Either rewrite both variants to use the same primitive, "
                    f"or lift to a Component class attribute for finer control.\n"
                    f"  See docs/morph.md#inline-primitives."
                )
            display = f"<inline {type(node_a).__name__}>"
            sub_root = substitution_root_a if substitution_root_a is not None else node_a
            if not _matrices_close(t_a, t_b):
                if inside_resize:
                    raise ValidationError(
                        f"morph: inline {type(node_a).__name__} animates "
                        f"inside a Resize() wrapper. Resize is bbox-dependent; "
                        f"wrapping animated geometry would recompute the scale "
                        f"factor every frame, producing visible size-jitter.\n"
                        f"  Move the Resize outside the morph, or drop the "
                        f"Resize and use Scale with explicit factors."
                    )
                _validate_pair(node_a, t_a, t_b, display)
                leaves.append(AnimatedLeaf(
                    leaf=node_a, substitution_root=sub_root,
                    M_a=t_a, M_b=t_b, display_name=display,
                ))
            return

        if kind_a == "structural":
            # Same structural-node type and arity required.
            if type(node_a) is not type(node_b):
                raise _structural_mismatch(node_a, node_b, "different structural node type")
            if len(node_a.children) != len(node_b.children):
                raise ValidationError(
                    f"morph: {type(node_a).__name__}() has {len(node_a.children)} "
                    f"children in the start variant but {len(node_b.children)} "
                    f"in the end variant. Structural arities must match — "
                    f"both variants must compose the same CSG skeleton."
                )
            # Reset accumulators and substitution-root for each child.
            # ``inside_resize`` propagates through structural nodes — a Union
            # under a Resize keeps every leaf below it inside-Resize.
            for child_a, child_b in zip(node_a.children, node_b.children):
                _walk(
                    child_a, child_b,
                    Matrix.identity(), Matrix.identity(),
                    None,
                    inside_resize=inside_resize,
                )
            return

        if kind_a == "decoration":
            # Decoration must match metadata; child is recursed with reset
            # accumulators and reset substitution-root.
            matches, reason = _decoration_matches(node_a, node_b)
            if not matches:
                raise ValidationError(
                    f"morph: decoration mismatch at the same structural "
                    f"position — {reason}. Decorations (color, anchors, "
                    f"highlight, etc.) are preserved in the morph output "
                    f"and must agree across variants."
                )
            # Resize specifically marks descent into a bbox-dependent
            # wrapper. Any animated leaf below this point will raise.
            from scadwright.ast.transforms import Resize
            child_inside_resize = inside_resize or isinstance(node_a, Resize)
            _walk(
                node_a.child, node_b.child,
                Matrix.identity(), Matrix.identity(),
                None,
                inside_resize=child_inside_resize,
            )
            return

        # All five kinds (component, primitive, structural, decoration,
        # spatial) are handled above. Spatial transforms in particular
        # were absorbed in the loop at the top — control flow never
        # reaches here.
        raise AssertionError(
            f"walker reached unreachable branch for node kind {kind_a!r}; "
            f"node type was {type(node_a).__name__}"
        )

    _walk(tree_a, tree_b, Matrix.identity(), Matrix.identity(), None)
    return MorphPlan(tree_a=tree_a, leaves=tuple(leaves))
