"""Subgraph extraction by focus node + radius.

:func:`filter_graph` produces a smaller :class:`Graph` containing
the focus node plus every node within ``depth`` hops in either
direction. The result is useful for ``scadwright graph --filter
SomeComponent --depth 1`` — show this Component's immediate
neighbourhood, hide the rest of the project.

The matcher resolves a user-supplied focus string to a single
:class:`Node` in the input graph. Bare names (``"Holder"``) match
on :attr:`Node.label`; dotted strings (``"main.Holder"``) match
on :attr:`Node.id`. A bare-name match collapses ambiguity by
raising :class:`FocusNotFound` with a helpful list of candidate
ids.
"""

from __future__ import annotations

from collections import defaultdict, deque

from scadwright.graph.model import Edge, Graph, Node


class FocusNotFound(Exception):
    """Raised when ``--filter NAME`` doesn't resolve to a single node.

    The exception message names the missing label (or, for
    ambiguous bare names, the candidate ids the user should pick
    among). The CLI surfaces the message verbatim and exits non-
    zero rather than producing a misleading partial graph.
    """


def filter_graph(
    graph: Graph,
    focus: str,
    depth: int | None = None,
) -> Graph:
    """Return the subgraph rooted at ``focus`` within ``depth`` hops.

    ``focus`` resolves to one node by label match, or by dotted-id
    match if the string contains a ``.``. Ambiguous label matches
    raise :class:`FocusNotFound` listing the candidate ids.

    ``depth`` is hop count in either edge direction (``0`` = just
    the focus node; ``1`` = focus plus direct neighbours;
    ``None`` = unlimited, full reachable subgraph). Edges within
    the kept node set survive; edges crossing the boundary drop.

    Output preserves the input graph's node and edge ordering —
    the input is already sorted, and a stable filter keeps that
    intact for renderer determinism.
    """
    focus_node = _resolve_focus(graph, focus)
    kept_ids = _bfs_within_radius(graph, focus_node.id, depth)
    nodes = tuple(n for n in graph.nodes if n.id in kept_ids)
    edges = tuple(
        e for e in graph.edges
        if e.source in kept_ids and e.target in kept_ids
    )
    return Graph(
        nodes=nodes, edges=edges,
        parse_errors=graph.parse_errors,
        warnings=graph.warnings,
        project_root=graph.project_root,
    )


def _resolve_focus(graph: Graph, focus: str) -> Node:
    """Map a user-supplied focus string to a unique :class:`Node`.

    Strings containing ``.`` are treated as full ids — they
    typically come from a previous run's output. Bare strings
    match labels; one match returns it, multiple candidates raise
    :class:`FocusNotFound` with the disambiguation list.
    """
    if "." in focus:
        for node in graph.nodes:
            if node.id == focus:
                return node
        raise FocusNotFound(
            f"no node with id {focus!r} in graph"
        )
    matches = [n for n in graph.nodes if n.label == focus]
    if not matches:
        raise FocusNotFound(
            f"no node named {focus!r} in graph"
        )
    if len(matches) > 1:
        candidates = ", ".join(sorted(n.id for n in matches))
        raise FocusNotFound(
            f"label {focus!r} matches multiple nodes; "
            f"specify by id (one of: {candidates})"
        )
    return matches[0]


def _bfs_within_radius(
    graph: Graph,
    start_id: str,
    depth: int | None,
) -> set[str]:
    """BFS from ``start_id`` over the undirected projection of the
    edge set, collecting every node within ``depth`` hops.

    ``depth=None`` means no radius cap — the BFS exhausts the
    connected component. ``depth=0`` returns only the start node.
    """
    neighbours: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        neighbours[edge.source].add(edge.target)
        neighbours[edge.target].add(edge.source)

    visited: set[str] = {start_id}
    if depth == 0:
        return visited
    frontier: deque[tuple[str, int]] = deque([(start_id, 0)])
    while frontier:
        current, dist = frontier.popleft()
        if depth is not None and dist >= depth:
            continue
        for nxt in neighbours.get(current, ()):
            if nxt in visited:
                continue
            visited.add(nxt)
            frontier.append((nxt, dist + 1))
    return visited


__all__ = ["FocusNotFound", "filter_graph"]
