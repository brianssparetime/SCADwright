"""JSON renderer for the project dependency graph.

Converts a :class:`scadwright.graph.model.Graph` into a JSON
string suitable for downstream tooling — custom dashboards,
documentation generators, diff-based "what changed" tooling.

The shape is two top-level keys: ``"nodes"`` and ``"edges"``,
each a list. Per-node fields: ``id``, ``label``, ``kind``, plus
``path`` (project-relative, POSIX-style) and ``line`` (1-based)
when source location is available. Per-edge fields: ``source``,
``target``, ``kind``, plus kind-specific extras included only
when present (``via_param`` for ``uses_param`` edges,
``attrs_read`` for ``reads_attr``).

Output is sorted (the :class:`Graph` builder already sorts) and
formatted with two-space indentation so the result is readable
when piped to a file. Use :func:`json.loads` on the output
without surprises — no custom encoder, no dataclass smuggling.
"""

from __future__ import annotations

import json

from scadwright.graph.model import Edge, Graph, Node


def render_json(graph: Graph) -> str:
    """Return a JSON string representation of ``graph``.

    Output ends in a trailing newline so concatenation with other
    text or files-on-disk doesn't need fixup. Two-space indent
    keeps diffs reviewable.
    """
    payload = {
        "nodes": [_node_dict(n, graph.project_root) for n in graph.nodes],
        "edges": [_edge_dict(e) for e in graph.edges],
    }
    return json.dumps(payload, indent=2) + "\n"


def _node_dict(node: Node, project_root) -> dict[str, object]:
    """Serialize one :class:`Node` to its JSON dict shape.

    Source location fields ``path`` and ``line`` are added when
    the node carries them. The path is relativized against
    ``project_root`` when one is set and the file lives under it;
    otherwise the absolute POSIX path is used.
    """
    out: dict[str, object] = {
        "id": node.id, "label": node.label, "kind": node.kind,
    }
    if node.file_path is not None:
        if project_root is not None:
            try:
                rel = node.file_path.relative_to(project_root)
                out["path"] = rel.as_posix()
            except ValueError:
                out["path"] = node.file_path.as_posix()
        else:
            out["path"] = node.file_path.as_posix()
    if node.line is not None:
        out["line"] = node.line
    return out


def _edge_dict(edge: Edge) -> dict[str, object]:
    """Serialize one :class:`Edge` to its JSON dict shape.

    Kind-specific supplemental fields are included only when
    present, so consumers can do ``edge.get("via_param")`` without
    having to know which edge kinds populate which fields.
    """
    out: dict[str, object] = {
        "source": edge.source,
        "target": edge.target,
        "kind": edge.kind,
    }
    if edge.via_param is not None:
        out["via_param"] = edge.via_param
    if edge.attrs_read:
        out["attrs_read"] = list(edge.attrs_read)
    return out
