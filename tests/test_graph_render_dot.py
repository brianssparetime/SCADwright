"""Tests for the Graphviz DOT renderer.

Covers per-category node shapes, per-kind edge labels, the
``digraph SCADwright`` header / closing brace structure,
identifier quoting (so ``.`` in ids doesn't break DOT parsing),
escape handling for label content, and determinism.
"""

from __future__ import annotations

from scadwright.graph.model import Edge, Graph, Node
from scadwright.graph.render_dot import render_dot


# =============================================================================
# Header / structure
# =============================================================================


def test_header_is_digraph_with_top_to_bottom_rank() -> None:
    out = render_dot(Graph(nodes=(), edges=()))
    assert out.startswith("digraph SCADwright {\n  rankdir=TB;\n")


def test_output_ends_with_closing_brace_and_newline() -> None:
    out = render_dot(Graph(nodes=(), edges=()))
    assert out.endswith("}\n")


def test_empty_graph_minimal_output() -> None:
    out = render_dot(Graph(nodes=(), edges=()))
    assert out == "digraph SCADwright {\n  rankdir=TB;\n}\n"


# =============================================================================
# Node shapes
# =============================================================================


def test_spec_uses_diamond() -> None:
    g = Graph(
        nodes=(Node(id="m.S", label="S", kind="spec"),),
        edges=(),
    )
    assert "shape=diamond" in render_dot(g)


def test_component_uses_rounded_box() -> None:
    g = Graph(
        nodes=(Node(id="m.C", label="C", kind="component"),),
        edges=(),
    )
    out = render_dot(g)
    assert "shape=box" in out
    assert "style=rounded" in out


def test_design_uses_cylinder() -> None:
    g = Graph(
        nodes=(Node(id="m.D", label="D", kind="design"),),
        edges=(),
    )
    assert "shape=cylinder" in render_dot(g)


def test_variant_uses_hexagon() -> None:
    g = Graph(
        nodes=(Node(id="m.D.v", label="v", kind="variant"),),
        edges=(),
    )
    assert "shape=hexagon" in render_dot(g)


# =============================================================================
# Edge labels
# =============================================================================


def test_inherits_edge_no_label() -> None:
    g = Graph(
        nodes=(),
        edges=(Edge(source="m.A", target="m.B", kind="inherits"),),
    )
    out = render_dot(g)
    assert '"m.A" -> "m.B";' in out
    assert "label=" not in out.split("\n  ")[-1]


def test_uses_param_edge_label() -> None:
    g = Graph(
        nodes=(),
        edges=(
            Edge(
                source="m.A", target="m.S", kind="uses_param",
                via_param="spec",
            ),
        ),
    )
    assert 'label="Param(spec)"' in render_dot(g)


def test_reads_attr_edge_label() -> None:
    g = Graph(
        nodes=(),
        edges=(
            Edge(
                source="m.A", target="m.S", kind="reads_attr",
                attrs_read=("height", "width"),
            ),
        ),
    )
    assert 'label="height, width"' in render_dot(g)


def test_contains_edge_label() -> None:
    g = Graph(
        nodes=(),
        edges=(Edge(source="m.A", target="m.B", kind="contains"),),
    )
    assert 'label="contains"' in render_dot(g)


def test_has_variant_edge_label() -> None:
    g = Graph(
        nodes=(),
        edges=(Edge(source="m.D", target="m.D.v", kind="has_variant"),),
    )
    assert 'label="variant"' in render_dot(g)


def test_variant_builds_edge_label() -> None:
    g = Graph(
        nodes=(),
        edges=(Edge(source="m.D.v", target="m.C", kind="variant_builds"),),
    )
    assert 'label="builds"' in render_dot(g)


# =============================================================================
# Identifier quoting & escaping
# =============================================================================


def test_dotted_ids_quoted_in_node_lines() -> None:
    g = Graph(
        nodes=(Node(id="sub.foo.X", label="X", kind="component"),),
        edges=(),
    )
    out = render_dot(g)
    # Node id appears verbatim inside double quotes, dot intact.
    assert '"sub.foo.X"' in out


def test_dotted_ids_quoted_in_edge_lines() -> None:
    g = Graph(
        nodes=(),
        edges=(
            Edge(source="sub.foo.A", target="sub.bar.B", kind="inherits"),
        ),
    )
    out = render_dot(g)
    assert '"sub.foo.A" -> "sub.bar.B";' in out


def test_label_escapes_double_quote() -> None:
    g = Graph(
        nodes=(Node(id="x", label='He said "hi"', kind="component"),),
        edges=(),
    )
    out = render_dot(g)
    # Inner double quotes get backslash-escaped.
    assert r'label="He said \"hi\""' in out


# =============================================================================
# Determinism
# =============================================================================


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
    a = render_dot(g)
    b = render_dot(g)
    assert a == b
