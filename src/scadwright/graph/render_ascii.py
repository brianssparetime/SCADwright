"""ASCII renderer for the project dependency graph.

Converts a :class:`scadwright.graph.model.Graph` into a
section-structured plain-text representation. Designed for
terminal viewing, scripting, grep, and AI assistants — the format
is line-oriented, deterministic, and self-describing.

Three sections under a one-line header::

    # scadwright graph: <path>  (N nodes, M edges, W warnings)

    ## nodes
    <kind>  <id>  <path:line>
    <kind>  <id> (<label>)  <path:line>      # when label differs from id's tail
    ...

    ## edges
    <source_id>
      <kind>  <target_id>  <extras>
      ...

    ## warnings
    <path>: <message>
    ...

Node lines are sorted by ``(kind, id)`` with the kind column
padded so identifiers align. Sources that have outgoing edges
get a section in ``## edges``; their edges are sorted by
``(kind, target)`` with the edge-kind column padded the same way.
Edge extras follow each line as ``[attrs]`` for ``reads_attr`` or
``(via name)`` for ``uses_param``.

Empty sections show ``(none)`` rather than being omitted, so the
structure stays predictable regardless of project size.

The renderer is the default format for the CLI: it's the most
useful output in a terminal, the most token-efficient for an AI
consumer, and the most diff-friendly for tracking changes across
runs.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.graph.model import Edge, Graph, Node


_NODE_KIND_WIDTH = max(len(k) for k in (
    "spec", "component", "design", "variant", "transform",
))
_EDGE_KIND_WIDTH = max(len(k) for k in (
    "inherits", "uses_param", "reads_attr", "contains",
    "has_variant", "variant_builds", "uses_transform",
))


def render_ascii(graph: Graph) -> str:
    """Return the ASCII representation of ``graph``.

    Output is deterministic — :class:`Graph` already sorts nodes
    and edges, and per-section sorts inside this renderer are
    stable secondary keys. Output ends with a trailing newline.
    """
    lines: list[str] = []
    lines.append(_header(graph))
    lines.append("")
    lines.append("## nodes")
    lines.extend(_node_lines(graph))
    lines.append("")
    lines.append("## edges")
    lines.extend(_edge_lines(graph))
    lines.append("")
    lines.append("## warnings")
    lines.extend(_warning_lines(graph))
    lines.append("")
    return "\n".join(lines)


def _header(graph: Graph) -> str:
    """Build the one-line header summarizing project + counts."""
    if graph.project_root is not None:
        root = graph.project_root.as_posix()
    else:
        root = "(unknown)"
    n = len(graph.nodes)
    m = len(graph.edges)
    w = len(graph.warnings)
    return (
        f"# scadwright graph: {root}  "
        f"({n} nodes, {m} edges, {w} warnings)"
    )


def _node_lines(graph: Graph) -> list[str]:
    """Format the per-node section.

    Nodes sort by ``(kind, id)`` so kinds group together within
    the section. The kind column is padded to a fixed width;
    labels that differ from the id's tail segment appear in
    parentheses after the id; the source location, when known,
    follows after two spaces.
    """
    if not graph.nodes:
        return ["(none)"]
    out: list[str] = []
    sorted_nodes = sorted(graph.nodes, key=lambda n: (n.kind, n.id))
    for node in sorted_nodes:
        out.append(_node_line(node, graph.project_root))
    return out


def _node_line(node: Node, project_root: Path | None) -> str:
    """Format one node line."""
    kind = node.kind.ljust(_NODE_KIND_WIDTH)
    body = node.id
    tail = node.id.rsplit(".", 1)[-1]
    if node.label != tail:
        body = f"{node.id} ({node.label})"
    location = _format_location(node.file_path, node.line, project_root)
    if location is None:
        return f"{kind}  {body}"
    return f"{kind}  {body}  {location}"


def _format_location(
    file_path: Path | None, line: int | None, project_root: Path | None,
) -> str | None:
    """Return ``"<path>:<line>"`` for a node's source location, or
    ``None`` when file_path isn't known.

    Paths are relativized against ``project_root`` when possible
    and converted to POSIX form so output reads the same on every
    OS.
    """
    if file_path is None:
        return None
    if project_root is not None:
        try:
            rel = file_path.relative_to(project_root)
            path_str = rel.as_posix()
        except ValueError:
            path_str = file_path.as_posix()
    else:
        path_str = file_path.as_posix()
    if line is None:
        return path_str
    return f"{path_str}:{line}"


def _edge_lines(graph: Graph) -> list[str]:
    """Format the per-source edges section.

    Walks the edge list (already sorted by ``Graph`` upstream) and
    groups consecutive same-source edges into a section with the
    source id as a header line followed by indented edges. Sources
    that don't appear in the edge list are absent from this
    section — the reader can confirm a node has no outgoing edges
    by its absence here.
    """
    if not graph.edges:
        return ["(none)"]
    out: list[str] = []
    current_source: str | None = None
    for edge in graph.edges:
        if edge.source != current_source:
            if current_source is not None:
                out.append("")
            out.append(edge.source)
            current_source = edge.source
        out.append("  " + _edge_line(edge))
    return out


def _edge_line(edge: Edge) -> str:
    """Format one edge line: ``<kind>  <target>  <extras>``."""
    kind = edge.kind.ljust(_EDGE_KIND_WIDTH)
    extras = _edge_extras(edge)
    if extras is None:
        return f"{kind}  {edge.target}"
    return f"{kind}  {edge.target}  {extras}"


def _edge_extras(edge: Edge) -> str | None:
    """Return the kind-specific extras suffix, or ``None`` for
    edge kinds that carry no extras.
    """
    if edge.kind == "uses_param":
        return f"(via {edge.via_param})"
    if edge.kind == "reads_attr":
        return "[" + ", ".join(edge.attrs_read) + "]"
    return None


def _warning_lines(graph: Graph) -> list[str]:
    """Format the warnings section. Warnings come pre-sorted from
    the builder; this renderer just emits them one per line.
    """
    if not graph.warnings:
        return ["(none)"]
    out: list[str] = []
    for path, message in graph.warnings:
        if graph.project_root is not None:
            try:
                rel = Path(path).relative_to(graph.project_root)
                path_str = rel.as_posix()
            except ValueError:
                path_str = Path(path).as_posix()
        else:
            path_str = Path(path).as_posix()
        out.append(f"{path_str}: {message}")
    return out
