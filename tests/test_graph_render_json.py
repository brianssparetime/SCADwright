"""Tests for the JSON renderer.

Covers per-node + per-edge serialization, kind-specific
supplemental fields (only present when set), determinism, and
the empty-graph case.
"""

from __future__ import annotations

import json

from scadwright.graph.model import Edge, Graph, Node
from scadwright.graph.render_json import render_json


def _parsed(graph: Graph) -> dict:
    """Render and round-trip through ``json.loads`` so tests assert
    against the structural payload rather than the textual form."""
    return json.loads(render_json(graph))


# =============================================================================
# Node serialization
# =============================================================================


def test_node_keys_are_id_label_kind() -> None:
    g = Graph(
        nodes=(Node(id="m.A", label="A", kind="component"),),
        edges=(),
    )
    [node] = _parsed(g)["nodes"]
    assert node == {"id": "m.A", "label": "A", "kind": "component"}


def test_each_node_kind_round_trips() -> None:
    g = Graph(
        nodes=(
            Node(id="m.S", label="S", kind="spec"),
            Node(id="m.C", label="C", kind="component"),
            Node(id="m.D", label="D", kind="design"),
            Node(id="m.D.show", label="show", kind="variant"),
        ),
        edges=(),
    )
    kinds = {n["kind"] for n in _parsed(g)["nodes"]}
    assert kinds == {"spec", "component", "design", "variant"}


# =============================================================================
# Edge serialization (per-kind extras)
# =============================================================================


def test_inherits_edge_minimal_keys() -> None:
    g = Graph(
        nodes=(),
        edges=(Edge(source="m.A", target="m.B", kind="inherits"),),
    )
    [edge] = _parsed(g)["edges"]
    assert edge == {"source": "m.A", "target": "m.B", "kind": "inherits"}
    assert "via_param" not in edge
    assert "attrs_read" not in edge


def test_uses_param_edge_includes_via_param() -> None:
    g = Graph(
        nodes=(),
        edges=(
            Edge(
                source="m.A", target="m.S",
                kind="uses_param", via_param="spec",
            ),
        ),
    )
    [edge] = _parsed(g)["edges"]
    assert edge["via_param"] == "spec"
    assert "attrs_read" not in edge


def test_reads_attr_edge_includes_attrs_list() -> None:
    g = Graph(
        nodes=(),
        edges=(
            Edge(
                source="m.A", target="m.S",
                kind="reads_attr", attrs_read=("height", "width"),
            ),
        ),
    )
    [edge] = _parsed(g)["edges"]
    assert edge["attrs_read"] == ["height", "width"]
    assert "via_param" not in edge


def test_contains_edge_minimal_keys() -> None:
    g = Graph(
        nodes=(),
        edges=(Edge(source="m.A", target="m.B", kind="contains"),),
    )
    [edge] = _parsed(g)["edges"]
    assert edge == {"source": "m.A", "target": "m.B", "kind": "contains"}


def test_has_variant_and_variant_builds_minimal_keys() -> None:
    g = Graph(
        nodes=(),
        edges=(
            Edge(source="m.D", target="m.D.show", kind="has_variant"),
            Edge(source="m.D.show", target="m.C", kind="variant_builds"),
        ),
    )
    edges = _parsed(g)["edges"]
    assert {e["kind"] for e in edges} == {"has_variant", "variant_builds"}
    for e in edges:
        assert "via_param" not in e
        assert "attrs_read" not in e


# =============================================================================
# Output shape
# =============================================================================


def test_output_is_valid_json() -> None:
    g = Graph(
        nodes=(Node(id="m.A", label="A", kind="component"),),
        edges=(),
    )
    # Round-trips without error.
    json.loads(render_json(g))


def test_top_level_keys() -> None:
    payload = _parsed(Graph(nodes=(), edges=()))
    assert set(payload.keys()) == {"nodes", "edges"}


def test_empty_graph_payload() -> None:
    assert _parsed(Graph(nodes=(), edges=())) == {"nodes": [], "edges": []}


def test_output_ends_with_newline() -> None:
    assert render_json(Graph(nodes=(), edges=())).endswith("\n")


def test_render_is_deterministic() -> None:
    g = Graph(
        nodes=(
            Node(id="m.A", label="A", kind="component"),
            Node(id="m.B", label="B", kind="component"),
        ),
        edges=(
            Edge(source="m.A", target="m.B", kind="inherits"),
        ),
    )
    a = render_json(g)
    b = render_json(g)
    assert a == b
