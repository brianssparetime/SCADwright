"""Pre-pass: count Component references and pick hoist candidates.

When the same Component instance is referenced more than once in the
emitted AST, inlining its `_get_built_tree()` at every site bloats the
SCAD output and forces OpenSCAD's preview to re-evaluate the duplicated
subtree per Boolean per frame. This pass walks the tree once, counts
identity-based references, and reports which Components warrant
hoisting into a top-level SCAD module.

Identity is the cache: `Component._get_built_tree()` runs `build()`
inside an ExitStack that pushes the Component's class-attr fn/fa/fs
and Clearances, and primitives bake $fn/$fa/$fs at construction time.
The cached subtree is therefore a monomorphic snapshot per Component
instance; `id(component)` is automatically context-correct as a dedup
key. Modifiers (color/disable/background/highlight) and chained
transforms wrap the Component reference at the call site — they never
mutate the cached subtree, so they compose around the hoisted module
call without further work.
"""

from __future__ import annotations

from dataclasses import dataclass

from scadwright.ast.base import Node
from scadwright.ast.primitives import (
    Circle,
    Cube,
    Cylinder,
    Polygon,
    Polyhedron,
    ScadImport,
    Sphere,
    Square,
    Surface,
    Text,
)

_PRIMITIVE_TYPES: tuple[type, ...] = (
    Cube, Sphere, Cylinder, Polyhedron,
    Square, Circle, Polygon,
    ScadImport, Surface, Text,
)

# A repeated Component is only worth hoisting if its cached subtree is
# substantial enough that the duplication would meaningfully bloat the
# SCAD output and slow OpenSCAD's preview. Below this many primitive
# leaves, hoisting trades inline brevity for module-call indirection
# without payoff. Edit here to retune; the value isn't part of any
# user-facing API.
_PRIM_THRESHOLD: int = 5


@dataclass
class _DedupEntry:
    component: object
    refcount: int
    prim_count: int


def collect_component_dedup_plan(root: Node) -> dict[int, _DedupEntry]:
    """Walk `root` and return per-Component reference + primitive counts.

    Returns a dict keyed on `id(component)`. `refcount` is the number of
    times that exact Component instance appears anywhere reachable from
    `root` (top-level AST plus inside other Components' built trees).
    `prim_count` is the number of primitive leaves directly inside the
    Component's own `_get_built_tree()` — nested Components count as one
    op (they're separately considered for their own hoist decision).
    """
    from scadwright.component.base import Component

    plan: dict[int, _DedupEntry] = {}
    # Components whose built-tree we've already walked for nested-component
    # discovery; prevents quadratic walks when the same Component is
    # referenced many times.
    walked_built: set[int] = set()
    # Roots we still need to walk for Component refcounts. Each entry is a
    # bare AST node (the top-level emit tree, or a Component's _built_tree).
    pending_walks: list[Node] = [root]

    while pending_walks:
        sub = pending_walks.pop()
        stack: list[object] = [sub]
        while stack:
            n = stack.pop()
            if isinstance(n, Component):
                cid = id(n)
                entry = plan.get(cid)
                if entry is None:
                    prim_count = _count_primitives(n._get_built_tree())
                    entry = _DedupEntry(component=n, refcount=1, prim_count=prim_count)
                    plan[cid] = entry
                else:
                    entry.refcount += 1
                # Walk the built tree exactly once per Component to find
                # any inner Components that are themselves dedup candidates.
                if cid not in walked_built:
                    walked_built.add(cid)
                    pending_walks.append(n._get_built_tree())
                # Do not descend into the Component's own subtree from here:
                # that subtree's primitives belong to the hoisted module body,
                # not to the surrounding tree's reference graph.
                continue
            for slot in ("child", "children"):
                if hasattr(n, slot):
                    c = getattr(n, slot)
                    if isinstance(c, (list, tuple)):
                        stack.extend(c)
                    elif c is not None:
                        stack.append(c)

    return plan


def select_hoists(plan: dict[int, _DedupEntry]) -> set[int]:
    """Return the set of `id(component)` values that should be hoisted.

    A Component qualifies when its instance is referenced at least twice
    AND its cached subtree contains at least `_PRIM_THRESHOLD` primitives.
    """
    return {
        cid for cid, entry in plan.items()
        if entry.refcount >= 2 and entry.prim_count >= _PRIM_THRESHOLD
    }


def _count_primitives(node: Node) -> int:
    """Count primitive leaves directly inside `node`'s subtree.

    Stops at nested Components — they're independent dedup candidates and
    are counted as one op (the module call) regardless of their interior
    primitive count. Inline Custom transforms expand at emit time; we
    treat them here as one op without expanding (cheap approximation;
    fine for a threshold check).
    """
    from scadwright.component.base import Component
    from scadwright.ast.custom import Custom

    count = 0
    stack: list[object] = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, _PRIMITIVE_TYPES):
            count += 1
            continue
        if isinstance(n, Component):
            count += 1
            continue
        if isinstance(n, Custom):
            count += 1
            continue
        for slot in ("child", "children"):
            if hasattr(n, slot):
                c = getattr(n, slot)
                if isinstance(c, (list, tuple)):
                    stack.extend(c)
                elif c is not None:
                    stack.append(c)
    return count
