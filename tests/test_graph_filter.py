"""Tests for :func:`scadwright.graph.filter.filter_graph`.

Covers focus-node resolution by label and id, ambiguity errors,
the BFS radius semantics (hop count in either direction, with
``depth=0`` and ``depth=None`` edge cases), edge filtering at
the boundary, and ordering preservation.
"""

from __future__ import annotations

import pytest

from scadwright.graph.filter import FocusNotFound, filter_graph
from scadwright.graph.model import Edge, Graph, Node


def _graph_chain() -> Graph:
    """Linear graph: A -> B -> C -> D."""
    return Graph(
        nodes=(
            Node(id="m.A", label="A", kind="component"),
            Node(id="m.B", label="B", kind="component"),
            Node(id="m.C", label="C", kind="component"),
            Node(id="m.D", label="D", kind="component"),
        ),
        edges=(
            Edge(source="m.A", target="m.B", kind="contains"),
            Edge(source="m.B", target="m.C", kind="contains"),
            Edge(source="m.C", target="m.D", kind="contains"),
        ),
    )


# =============================================================================
# Focus resolution
# =============================================================================


def test_focus_by_label() -> None:
    g = _graph_chain()
    out = filter_graph(g, "B", depth=0)
    assert {n.id for n in out.nodes} == {"m.B"}


def test_focus_by_dotted_id() -> None:
    g = _graph_chain()
    out = filter_graph(g, "m.B", depth=0)
    assert {n.id for n in out.nodes} == {"m.B"}


def test_focus_label_unknown_raises() -> None:
    g = _graph_chain()
    with pytest.raises(FocusNotFound) as exc:
        filter_graph(g, "ZZZ")
    assert "ZZZ" in str(exc.value)


def test_focus_id_unknown_raises() -> None:
    g = _graph_chain()
    with pytest.raises(FocusNotFound) as exc:
        filter_graph(g, "x.Y")
    assert "x.Y" in str(exc.value)


def test_focus_ambiguous_label_raises_with_candidate_list() -> None:
    g = Graph(
        nodes=(
            Node(id="a.Foo", label="Foo", kind="component"),
            Node(id="b.Foo", label="Foo", kind="component"),
        ),
        edges=(),
    )
    with pytest.raises(FocusNotFound) as exc:
        filter_graph(g, "Foo")
    msg = str(exc.value)
    assert "a.Foo" in msg
    assert "b.Foo" in msg


# =============================================================================
# BFS radius
# =============================================================================


def test_depth_zero_keeps_only_focus() -> None:
    out = filter_graph(_graph_chain(), "B", depth=0)
    assert {n.id for n in out.nodes} == {"m.B"}
    assert out.edges == ()


def test_depth_one_keeps_direct_neighbours_both_directions() -> None:
    # B's neighbours are A (incoming) and C (outgoing); D is two hops.
    out = filter_graph(_graph_chain(), "B", depth=1)
    assert {n.id for n in out.nodes} == {"m.A", "m.B", "m.C"}


def test_depth_two_keeps_two_hop_neighbours() -> None:
    out = filter_graph(_graph_chain(), "A", depth=2)
    assert {n.id for n in out.nodes} == {"m.A", "m.B", "m.C"}


def test_depth_unlimited_keeps_full_reachable_subgraph() -> None:
    out = filter_graph(_graph_chain(), "A", depth=None)
    assert {n.id for n in out.nodes} == {"m.A", "m.B", "m.C", "m.D"}


def test_disconnected_components_dropped_with_unlimited_depth() -> None:
    # Two disjoint subgraphs; filtering on one shouldn't leak the other.
    g = Graph(
        nodes=(
            Node(id="m.A", label="A", kind="component"),
            Node(id="m.B", label="B", kind="component"),
            Node(id="m.X", label="X", kind="component"),
            Node(id="m.Y", label="Y", kind="component"),
        ),
        edges=(
            Edge(source="m.A", target="m.B", kind="contains"),
            Edge(source="m.X", target="m.Y", kind="contains"),
        ),
    )
    out = filter_graph(g, "A")
    assert {n.id for n in out.nodes} == {"m.A", "m.B"}


# =============================================================================
# Edge filtering at the boundary
# =============================================================================


def test_edges_outside_kept_set_dropped() -> None:
    out = filter_graph(_graph_chain(), "B", depth=1)
    # B's edges to A and C survive; the C->D edge is gone.
    edge_pairs = {(e.source, e.target) for e in out.edges}
    assert edge_pairs == {("m.A", "m.B"), ("m.B", "m.C")}


def test_edge_attributes_preserved() -> None:
    g = Graph(
        nodes=(
            Node(id="m.A", label="A", kind="component"),
            Node(id="m.S", label="S", kind="spec"),
        ),
        edges=(
            Edge(
                source="m.A", target="m.S", kind="reads_attr",
                attrs_read=("h", "w"),
            ),
            Edge(
                source="m.A", target="m.S", kind="uses_param",
                via_param="spec",
            ),
        ),
    )
    out = filter_graph(g, "A", depth=1)
    by_kind = {e.kind: e for e in out.edges}
    assert by_kind["reads_attr"].attrs_read == ("h", "w")
    assert by_kind["uses_param"].via_param == "spec"


# =============================================================================
# Ordering preserved
# =============================================================================


def test_nodes_and_edges_keep_input_order() -> None:
    g = _graph_chain()
    out = filter_graph(g, "A", depth=None)
    assert [n.id for n in out.nodes] == ["m.A", "m.B", "m.C", "m.D"]
    assert [(e.source, e.target) for e in out.edges] == [
        ("m.A", "m.B"), ("m.B", "m.C"), ("m.C", "m.D"),
    ]


# =============================================================================
# Variant inclusion: the focus is a Design
# =============================================================================


def test_design_focus_pulls_in_variants_at_depth_one() -> None:
    g = Graph(
        nodes=(
            Node(id="m.D", label="D", kind="design"),
            Node(id="m.D.show", label="show", kind="variant"),
            Node(id="m.D.print", label="print", kind="variant"),
            Node(id="m.C", label="C", kind="component"),
        ),
        edges=(
            Edge(source="m.D", target="m.D.show", kind="has_variant"),
            Edge(source="m.D", target="m.D.print", kind="has_variant"),
            Edge(source="m.D.show", target="m.C", kind="variant_builds"),
        ),
    )
    out = filter_graph(g, "D", depth=1)
    # D + both variants are within 1 hop; C is 2 hops out.
    assert {n.id for n in out.nodes} == {"m.D", "m.D.show", "m.D.print"}
