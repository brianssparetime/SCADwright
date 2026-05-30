"""Graphviz DOT renderer for the project dependency graph.

Converts a :class:`scadwright.graph.model.Graph` into a DOT
``digraph`` source string. DOT scales further than Mermaid when
the project grows past a couple dozen nodes — Graphviz's layout
engines (``dot``, ``neato``, ``sfdp``) handle the geometry, and
the rendered SVG/PNG can drop into static documentation.

Node shapes per category, mapped to Graphviz built-ins:

- Spec → ``diamond``.
- Component → ``box`` with rounded style.
- Design → ``cylinder``.
- Variant → ``hexagon``.
- Transform → ``parallelogram``.

Edge labels mirror the Mermaid renderer's labels so the two
formats produce visually-equivalent graphs from the same model.

Identifiers (the ``"<id>"`` form on the LHS of edge declarations
and on node lines) are quoted because :class:`Node` ids contain
``.`` characters; DOT identifiers without quotes can't carry
dots. Labels and quoted strings escape backslashes and double
quotes via :func:`_escape`.
"""

from __future__ import annotations

from scadwright.graph.model import Edge, Graph, Node


_NODE_ATTRS: dict[str, str] = {
    "spec": 'shape=diamond',
    "component": 'shape=box, style=rounded',
    "design": 'shape=cylinder',
    "variant": 'shape=hexagon',
    "transform": 'shape=parallelogram',
}


def render_dot(graph: Graph) -> str:
    """Return a Graphviz DOT ``digraph`` source string for ``graph``.

    Output is deterministic — :class:`Graph` sorts nodes and edges
    upstream. Pipe the result through ``dot -Tsvg`` (or ``-Tpng``)
    to produce a rendered diagram.
    """
    lines: list[str] = ["digraph SCADwright {", "  rankdir=TB;"]
    for node in graph.nodes:
        lines.append(_node_line(node))
    for edge in graph.edges:
        lines.append(_edge_line(edge))
    lines.append("}")
    return "\n".join(lines) + "\n"


def _node_line(node: Node) -> str:
    """Render one node declaration: ``"id" [label="...", shape=...]``."""
    attrs = _NODE_ATTRS.get(node.kind, "shape=box")
    return f'  "{node.id}" [label="{_escape(node.label)}", {attrs}];'


def _edge_line(edge: Edge) -> str:
    """Render one directed edge with its per-kind label.

    Inherits edges have no label. Other kinds spell out the
    relationship — same labels the Mermaid renderer uses.
    """
    src = _escape(edge.source)
    dst = _escape(edge.target)
    label = _edge_label(edge)
    if label is None:
        return f'  "{src}" -> "{dst}";'
    return f'  "{src}" -> "{dst}" [label="{_escape(label)}"];'


def _edge_label(edge: Edge) -> str | None:
    """Compute the label string for an edge, or ``None`` for the
    no-label case (currently only ``inherits``).
    """
    if edge.kind == "inherits":
        return None
    if edge.kind == "uses_param":
        return f"Param({edge.via_param})"
    if edge.kind == "reads_attr":
        return ", ".join(edge.attrs_read)
    if edge.kind == "contains":
        return "contains"
    if edge.kind == "has_variant":
        return "variant"
    if edge.kind == "variant_builds":
        return "builds"
    if edge.kind == "uses_transform":
        return "uses"
    return None


def _escape(text: str) -> str:
    """Escape DOT-quoted-string special characters.

    Backslashes and double quotes are the only characters that
    matter inside a quoted DOT string. Newlines aren't possible in
    our model (ids and labels are derived from Python identifiers
    and class names) so they aren't handled.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')
