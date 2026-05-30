"""Mermaid renderer for the project dependency graph.

Converts a :class:`scadwright.graph.model.Graph` into a Mermaid
``graph TD`` source string suitable for embedding in a Markdown
README (GitHub renders Mermaid natively) or rendering with the
Mermaid CLI / live editor.

Node shapes per category:

- Spec → diamond (``{Label}``).
- Component → rounded box (``(Label)``).
- Design → cylinder (``[(Label)]``).
- Variant → hexagon (``{{Label}}``), one per ``@variant`` method.
- Transform → parallelogram (``[/Label/]``), one per project-
  registered transform; label is the registered name.

Edge labels per kind:

- ``inherits`` → no label, plain ``-->``.
- ``uses_param`` → ``"Param(name)"`` showing which Param routes
  the dependency.
- ``reads_attr`` → comma-separated list of attribute names read.
- ``contains`` → ``"contains"`` label distinguishing it from a
  bare inheritance arrow.
- ``has_variant`` → ``"variant"`` linking a Design to one of its
  variant sub-nodes.
- ``variant_builds`` → ``"builds"`` linking a Variant to a
  Component it produces.
- ``uses_transform`` → ``"uses"`` linking a Component, transform,
  or variant to a project-registered transform it invokes.

Mermaid identifiers can't contain ``.``, so the dotted node ids
from :class:`Graph` are normalized: every non-alphanumeric is
replaced with ``_``. Two distinct ids that normalize to the same
string (e.g., ``foo.bar.Baz`` and ``foo_bar.Baz``) get
disambiguated with a numeric suffix on the second-and-later
collision in iteration order — so the rendered Mermaid is
guaranteed to keep distinct nodes distinct.
"""

from __future__ import annotations

from scadwright.graph.model import Edge, Graph, Node


_NODE_SHAPES: dict[str, tuple[str, str]] = {
    "spec": ("{", "}"),
    "component": ("(", ")"),
    "design": ("[(", ")]"),
    "variant": ("{{", "}}"),
    "transform": ("[/", "/]"),
}


def render_mermaid(graph: Graph) -> str:
    """Return a Mermaid ``graph TD`` source string for ``graph``.

    Output is deterministic — :class:`Graph` already sorts nodes
    and edges, and the id-disambiguation step processes nodes in
    that sorted order. Two classes in different modules with the
    same name survive disambiguation through the normalized id;
    their labels show the bare class name (the dotted module
    prefix only enters the id, not the visible label).
    """
    id_map = _build_id_map(graph.nodes)
    lines: list[str] = ["graph TD"]
    for node in graph.nodes:
        lines.append(_node_line(node, id_map))
    for edge in graph.edges:
        lines.append(_edge_line(edge, id_map))
    return "\n".join(lines) + "\n"


def _build_id_map(nodes: tuple[Node, ...]) -> dict[str, str]:
    """Map raw node ids to collision-free Mermaid identifiers.

    Iteration order is the input order (already sorted by
    :class:`Graph`), so the disambiguation suffix is deterministic
    across runs: the first-encountered raw id keeps the bare
    normalized form; subsequent collisions get ``_2``, ``_3``, etc.
    """
    used: set[str] = set()
    out: dict[str, str] = {}
    for node in nodes:
        candidate = _normalize(node.id)
        if candidate in used:
            i = 2
            while f"{candidate}_{i}" in used:
                i += 1
            candidate = f"{candidate}_{i}"
        used.add(candidate)
        out[node.id] = candidate
    return out


def _node_line(node: Node, id_map: dict[str, str]) -> str:
    """Render one node declaration: ``<id><open><label><close>``.

    For example, a Spec named ``BatterySpec`` in module ``main``
    renders as ``main_BatterySpec{BatterySpec}``.
    """
    open_, close = _NODE_SHAPES.get(node.kind, ("[", "]"))
    return f"  {id_map[node.id]}{open_}{node.label}{close}"


def _edge_line(edge: Edge, id_map: dict[str, str]) -> str:
    """Render one directed edge with the per-kind label."""
    src = id_map[edge.source]
    dst = id_map[edge.target]
    if edge.kind == "inherits":
        return f"  {src} --> {dst}"
    if edge.kind == "uses_param":
        return f'  {src} --"Param({edge.via_param})"--> {dst}'
    if edge.kind == "reads_attr":
        attrs = ", ".join(edge.attrs_read)
        return f'  {src} --"{attrs}"--> {dst}'
    if edge.kind == "contains":
        return f'  {src} --"contains"--> {dst}'
    if edge.kind == "has_variant":
        return f'  {src} --"variant"--> {dst}'
    if edge.kind == "variant_builds":
        return f'  {src} --"builds"--> {dst}'
    if edge.kind == "uses_transform":
        return f'  {src} --"uses"--> {dst}'
    return f"  {src} --> {dst}"


def _normalize(node_id: str) -> str:
    """Normalize a :class:`Node` id into a Mermaid-safe identifier.

    Replaces every non-alphanumeric character with ``_``. Dotted
    paths (``main.sub.Bracket``) become underscore-joined
    (``main_sub_Bracket``). Class names that already contain
    underscores survive unchanged. Collision disambiguation is
    handled separately in :func:`_build_id_map`.
    """
    return "".join(c if c.isalnum() else "_" for c in node_id)
