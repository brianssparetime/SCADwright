"""Parallel structure walker for morph(): pair animated leaves across N
variant ASTs while preserving the variants' CSG structure.

The walker descends every stage's tree in lockstep. Structurally-equivalent
nodes (same type, same arity for CSG containers) match across all stages;
structural mismatches raise. As we descend:

- **Spatial transforms** (Translate, Rotate, Scale, Mirror, MultMatrix)
  accumulate into a per-leaf, per-stage transform matrix on each side
  independently. They will be absorbed into each leg's animated chain at
  emit time, not preserved as bare transforms.
- **Structural nodes** (Union, Difference, Intersection, Hull, Minkowski)
  reset the accumulators for each child. They stay in the emit, with
  their children replaced by animated subtrees.
- **Decorations** (Color, WithAnchor, PreviewModifier, ForceRender,
  Resize, Projection, Offset, Echo) act as boundaries too — they
  preserve themselves in the emit and reset the accumulator. Their
  metadata must match across every stage.
- **Components and primitives** are leaves. Components pair across
  stages by Python ``id`` (the same instance backs every stage when
  declared as a class attribute on the Design). Inline primitives
  (Cube, Sphere, Cylinder, etc.) pair by ``tree_hash``; their transform
  stacks may differ per stage, in which case the primitive animates on
  the legs where its matrices differ.

For each animated leaf, the walker records — per leg — an ``AnimatedLeaf``
entry only if the leaf's transform stack differs between that leg's
``(stage_k, stage_{k+1})`` pair. A leaf that's static in some legs and
animates in others appears in the plan only for the legs where it
moves. The substitution root is taken from stage 0's tree (the topmost
spatial-transform ancestor in the unbroken transform chain above the
leaf in stage 0, or the leaf itself if there are no such transforms).

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
    """One animated leaf in one leg of a morph chain.

    ``leaf`` is the original AST node from stage 0; ``substitution_root``
    is the topmost spatial-transform ancestor in stage 0's tree (or
    ``leaf`` itself if no spatial wrapper sits directly above it). Emit
    replaces ``substitution_root`` with the chained animated subtree
    once per leaf — every leg's entry for that leaf shares the same
    substitution root and is composed into the same chain at build time.

    ``M_a`` and ``M_b`` are the composed spatial transforms for this leg
    — the per-stage pose contributions that the animated chain must
    reproduce at the leg's α=0 and α=1 boundaries respectively.
    """

    leaf: "Node"
    substitution_root: "Node"
    M_a: Matrix
    M_b: Matrix
    display_name: str


@dataclass(frozen=True)
class LegPlan:
    """The animated leaves for one consecutive pair of stages.

    ``leaves`` lists every leaf whose transform stack differs between
    this leg's start and end stage. Static leaves (identical M_a and
    M_b) do not appear — they remain in ``ChainPlan.tree_a`` unchanged.
    """

    leaves: tuple[AnimatedLeaf, ...]


@dataclass(frozen=True)
class ChainPlan:
    """Walker output for a morph across N stages.

    ``tree_a`` is stage 0's AST — the structural template that emit
    substitutes into. ``legs`` has length ``N - 1``; ``legs[k]``
    describes which leaves animate between ``stages[k]`` and
    ``stages[k+1]``.
    """

    tree_a: "Node"
    legs: tuple[LegPlan, ...]


# Backwards-compatible alias for the 2-stage entry point. Older callers /
# tests can still construct ``walk(tree_a, tree_b, inst)`` and get a plan
# back; the plan now has a ``.legs[0].leaves`` shape instead of a flat
# ``.leaves`` field. See ``walk_chain`` for the N-stage entry point.


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
                f"scale that differs between stages.\n"
                f"  start scale: {tuple(round(v, 6) for v in s_a)}\n"
                f"  end scale:   {tuple(round(v, 6) for v in s_b)}\n"
                f"  Only uniform scale changes can be animated; for shape "
                f"morphing, define separate parts."
            )


# Type sets for the walker. Decorations preserve themselves and act as
# boundaries; spatial transforms accumulate into M_k.

def _import_ast_types():
    """Late import to avoid circular dependency at module-load time."""
    from scadwright.ast.csg import (
        Difference, Hull, Intersection, Minkowski, Union,
    )
    from scadwright.ast.transforms import (
        Color, Echo, ForceRender, Mirror, MultMatrix, Offset,
        PreviewModifier, Projection, Resize, Rotate, Scale, Translate,
        WithAnchor, WithBBox,
    )
    from scadwright.component.base import Component
    return {
        "Component": Component,
        "spatial_transforms": (Translate, Rotate, Scale, Mirror, MultMatrix),
        "structural": (Union, Difference, Intersection, Hull, Minkowski),
        "decorations": (
            Color, WithAnchor, WithBBox, PreviewModifier, ForceRender,
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
    WithBBox, PreviewModifier, ForceRender, Resize, Projection, Offset,
    Echo, or any new metadata wrapper added later.

    Field comparison uses ``tree_hash`` rather than ``==``: most fields
    are simple scalars where this makes no difference, but some
    decorations (notably ``WithBBox.source``) hold a ``Node`` value, and
    the dataclass-auto ``__eq__`` for a Node includes ``source_location``.
    Two semantically-identical Nodes constructed at different call sites
    would false-mismatch under ``==``. ``tree_hash`` canonicalizes Nodes
    without source_location, giving the right semantic equality.

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
        if tree_hash(va) != tree_hash(vb):
            return False, (
                f"different {cls_name}.{f.name} ({va!r} vs {vb!r})"
            )
    return True, ""


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def walk(tree_a, tree_b, design_instance) -> ChainPlan:
    """Walk two trees and produce a single-leg ChainPlan.

    Thin convenience wrapper over :func:`walk_chain` for the common
    two-stage case. The returned ChainPlan has ``len(legs) == 1``.
    """
    return walk_chain((tree_a, tree_b), design_instance)


def walk_chain(trees: tuple, design_instance) -> ChainPlan:
    """Walk N>=2 variant trees in lockstep; produce a ChainPlan describing
    which leaves animate per leg and at what transforms.

    Each ``trees[k]`` must share the same CSG / decoration skeleton with
    every other stage; only the spatial transforms above each leaf may
    differ between stages. Structural mismatches between any pair of
    stages raise ``ValidationError`` with the offending stage indices
    named.
    """
    n = len(trees)
    if n < 2:
        raise ValidationError(
            f"morph: walk_chain requires at least 2 stages, got {n}"
        )
    types = _import_ast_types()
    id_to_name = _build_id_to_name(design_instance)

    legs_leaves: list[list[AnimatedLeaf]] = [[] for _ in range(n - 1)]

    def _structural_mismatch(nodes, i_other, why: str):
        """Build the right validation error for a structural mismatch
        between stages[0] and stages[i_other]. Detects the specific case
        of "one stage has a decoration wrapper at this position and the
        other has the bare leaf" and gives a fix-it message; otherwise
        falls through to the generic mismatch message.
        """
        node_a = nodes[0]
        node_b = nodes[i_other]
        kind_a = _node_kind(node_a, types)
        kind_b = _node_kind(node_b, types)
        decoration_asymmetry = (
            (kind_a == "decoration" and kind_b in ("component", "primitive"))
            or (kind_b == "decoration" and kind_a in ("component", "primitive"))
        )
        if decoration_asymmetry:
            deco_node = node_a if kind_a == "decoration" else node_b
            deco_stage = 0 if kind_a == "decoration" else i_other
            other_stage = i_other if deco_stage == 0 else 0
            deco_name = type(deco_node).__name__
            return ValidationError(
                f"morph: decoration wrapper present in one stage only.\n"
                f"  stages[{deco_stage}] has: {deco_name}(...) wrapping "
                f"the leaf\n"
                f"  stages[{other_stage}] has: the leaf with no wrapper\n"
                f"  Decorations (Color, WithAnchor, PreviewModifier, "
                f"ForceRender, Resize, etc.) are preserved through the "
                f"morph and must appear in every stage — they aren't "
                f"interpolated. Either add the same {deco_name}(...) "
                f"wrapper to stages[{other_stage}], or remove it from "
                f"stages[{deco_stage}]."
            )
        return ValidationError(
            f"morph: variant ASTs differ in structure between stages[0] "
            f"and stages[{i_other}] — {why}.\n"
            f"  stages[0] has:        {type(node_a).__name__}\n"
            f"  stages[{i_other}] has: {type(node_b).__name__}\n"
            f"  morph requires every stage to share the same CSG / "
            f"decoration skeleton; only the transforms above leaves "
            f"(Components, primitives) may differ."
        )

    def _walk(
        nodes: tuple, ts: list, substitution_root_0,
        inside_resize: bool = False,
    ):
        """Parallel descent across all N stages.

        ``ts[k]`` accumulates the composed spatial transform between the
        most-recent structural-or-decoration boundary and the current
        point in stage k. ``substitution_root_0`` is the topmost
        spatial-transform ancestor in stage 0 within the current
        contiguous transform chain (or None if the immediate parent in
        stage 0 is a structural or decoration node).

        ``inside_resize`` becomes True once descent crosses a Resize
        wrapper; animated leaves below a Resize raise instead of being
        recorded. Resize is bbox-dependent — its scale factor is
        computed from the child's bbox at render time — so wrapping an
        animated subtree would make every frame recompute the scale,
        producing size-jitter as the part rotates / translates.
        """
        new_nodes = list(nodes)
        new_ts = list(ts)
        new_sub = substitution_root_0

        # Absorb spatial transforms on each stage independently. Stage 0
        # also seeds the substitution root for emit-time replacement.
        for i in range(n):
            while isinstance(new_nodes[i], types["spatial_transforms"]):
                new_ts[i] = new_ts[i] @ to_matrix(new_nodes[i])
                if i == 0 and new_sub is None:
                    new_sub = new_nodes[i]
                new_nodes[i] = new_nodes[i].child

        kinds = [_node_kind(nd, types) for nd in new_nodes]
        for i in range(1, n):
            if kinds[i] != kinds[0]:
                raise _structural_mismatch(
                    new_nodes, i, f"kind differs ({kinds[0]} vs {kinds[i]})",
                )

        kind = kinds[0]

        if kind == "component":
            ids = [id(nd) for nd in new_nodes]
            for i in range(1, n):
                if ids[i] != ids[0]:
                    name_0 = id_to_name.get(ids[0], repr(new_nodes[0]))
                    name_i = id_to_name.get(ids[i], repr(new_nodes[i]))
                    raise ValidationError(
                        f"morph: Component leaves differ at the same "
                        f"structural position. stages[0] has {name_0!r}, "
                        f"stages[{i}] has {name_i!r}. Every stage must "
                        f"reference the same Component instance (declared "
                        f"as a class attribute on the Design)."
                    )
            display = id_to_name.get(
                ids[0], f"<{type(new_nodes[0]).__name__} (inline)>",
            )
            sub_root = new_sub if new_sub is not None else new_nodes[0]
            for k in range(n - 1):
                M_k = new_ts[k]
                M_kp1 = new_ts[k + 1]
                if _matrices_close(M_k, M_kp1):
                    continue
                if inside_resize:
                    raise ValidationError(
                        f"morph: part {display!r} animates inside a "
                        f"Resize() wrapper between stages[{k}] and "
                        f"stages[{k + 1}]. Resize is bbox-dependent — "
                        f"its scale factor is computed from the child's "
                        f"bounding box at render time, so a Resize "
                        f"wrapping an animated part would recompute the "
                        f"scale every frame as the part rotates and "
                        f"translates, producing visible size-jitter.\n"
                        f"  Move the Resize outside the morph (apply it "
                        f"to the final unioned result), or drop the "
                        f"Resize and use Scale with explicit factors so "
                        f"the scale is constant."
                    )
                _validate_pair(
                    new_nodes[0], M_k, M_kp1, display,
                    label_hint=f" between stages[{k}] and stages[{k + 1}]",
                )
                legs_leaves[k].append(AnimatedLeaf(
                    leaf=new_nodes[0], substitution_root=sub_root,
                    M_a=M_k, M_b=M_kp1, display_name=display,
                ))
            return

        if kind == "primitive":
            hashes = [tree_hash(nd) for nd in new_nodes]
            for i in range(1, n):
                if hashes[i] != hashes[0]:
                    raise ValidationError(
                        f"morph: inline primitive geometry differs at "
                        f"the same structural position between stages[0] "
                        f"and stages[{i}].\n"
                        f"  stages[0]:  {type(new_nodes[0]).__name__}\n"
                        f"  stages[{i}]: {type(new_nodes[i]).__name__}\n"
                        f"  Inline primitives pair by structural position "
                        f"and tree_hash; their shape and parameters must "
                        f"match across every stage. Either rewrite the "
                        f"stages to use the same primitive, or lift to a "
                        f"Component class attribute for finer control.\n"
                        f"  See docs/morph.md#inline-primitives."
                    )
            display = f"<inline {type(new_nodes[0]).__name__}>"
            sub_root = new_sub if new_sub is not None else new_nodes[0]
            for k in range(n - 1):
                M_k = new_ts[k]
                M_kp1 = new_ts[k + 1]
                if _matrices_close(M_k, M_kp1):
                    continue
                if inside_resize:
                    raise ValidationError(
                        f"morph: inline {type(new_nodes[0]).__name__} "
                        f"animates inside a Resize() wrapper between "
                        f"stages[{k}] and stages[{k + 1}]. Resize is "
                        f"bbox-dependent; wrapping animated geometry "
                        f"would recompute the scale factor every frame, "
                        f"producing visible size-jitter.\n"
                        f"  Move the Resize outside the morph, or drop "
                        f"the Resize and use Scale with explicit factors."
                    )
                _validate_pair(
                    new_nodes[0], M_k, M_kp1, display,
                    label_hint=f" between stages[{k}] and stages[{k + 1}]",
                )
                legs_leaves[k].append(AnimatedLeaf(
                    leaf=new_nodes[0], substitution_root=sub_root,
                    M_a=M_k, M_b=M_kp1, display_name=display,
                ))
            return

        if kind == "structural":
            type0 = type(new_nodes[0])
            for i in range(1, n):
                if type(new_nodes[i]) is not type0:
                    raise _structural_mismatch(
                        new_nodes, i, "different structural node type",
                    )
            arity0 = len(new_nodes[0].children)
            for i in range(1, n):
                ai = len(new_nodes[i].children)
                if ai != arity0:
                    raise ValidationError(
                        f"morph: {type0.__name__}() has {arity0} children "
                        f"in stages[0] but {ai} in stages[{i}]. Structural "
                        f"arities must match — every stage must compose "
                        f"the same CSG skeleton."
                    )
            for child_idx in range(arity0):
                child_nodes = tuple(
                    new_nodes[i].children[child_idx] for i in range(n)
                )
                _walk(
                    child_nodes,
                    [Matrix.identity() for _ in range(n)],
                    None,
                    inside_resize=inside_resize,
                )
            return

        if kind == "decoration":
            for i in range(1, n):
                matches, reason = _decoration_matches(new_nodes[0], new_nodes[i])
                if not matches:
                    raise ValidationError(
                        f"morph: decoration mismatch at the same "
                        f"structural position between stages[0] and "
                        f"stages[{i}] — {reason}. Decorations (color, "
                        f"anchors, highlight, etc.) are preserved in the "
                        f"morph output and must agree across every stage."
                    )
            from scadwright.ast.transforms import Resize
            child_inside_resize = inside_resize or isinstance(new_nodes[0], Resize)
            child_nodes = tuple(nd.child for nd in new_nodes)
            _walk(
                child_nodes,
                [Matrix.identity() for _ in range(n)],
                None,
                inside_resize=child_inside_resize,
            )
            return

        # All five kinds (component, primitive, structural, decoration,
        # spatial) are handled above. Spatial transforms in particular
        # were absorbed in the loop at the top — control flow never
        # reaches here.
        raise AssertionError(
            f"walker reached unreachable branch for node kind {kind!r}; "
            f"node type was {type(new_nodes[0]).__name__}"
        )

    _walk(
        tuple(trees),
        [Matrix.identity() for _ in range(n)],
        None,
    )

    legs = tuple(LegPlan(leaves=tuple(L)) for L in legs_leaves)
    return ChainPlan(tree_a=trees[0], legs=legs)
