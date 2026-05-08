"""Tests for the Mermaid renderer.

Covers node-shape selection per category, edge labels per kind,
deterministic output, the empty-graph case, and the id
normalization that protects against dotted module paths.
"""

from __future__ import annotations

from scadwright.graph.model import Edge, Graph, Node
from scadwright.graph.render_mermaid import render_mermaid


# =============================================================================
# Node shapes
# =============================================================================


def test_spec_uses_diamond_shape() -> None:
    graph = Graph(
        nodes=(Node(id="m.S", label="S", kind="spec"),),
        edges=(),
    )
    out = render_mermaid(graph)
    assert "m_S{S}" in out


def test_component_uses_rounded_shape() -> None:
    graph = Graph(
        nodes=(Node(id="m.C", label="C", kind="component"),),
        edges=(),
    )
    out = render_mermaid(graph)
    assert "m_C(C)" in out


def test_design_uses_cylinder_shape() -> None:
    graph = Graph(
        nodes=(Node(id="m.D", label="D", kind="design"),),
        edges=(),
    )
    out = render_mermaid(graph)
    assert "m_D[(D)]" in out


def test_variant_uses_hexagon_shape() -> None:
    graph = Graph(
        nodes=(Node(id="m.D.show", label="show", kind="variant"),),
        edges=(),
    )
    out = render_mermaid(graph)
    assert "m_D_show{{show}}" in out


# =============================================================================
# Edge labels
# =============================================================================


def test_inherits_edge_no_label() -> None:
    graph = Graph(
        nodes=(
            Node(id="m.A", label="A", kind="component"),
            Node(id="m.B", label="B", kind="component"),
        ),
        edges=(Edge(source="m.A", target="m.B", kind="inherits"),),
    )
    out = render_mermaid(graph)
    assert "m_A --> m_B" in out


def test_uses_param_edge_label_includes_param_name() -> None:
    graph = Graph(
        nodes=(
            Node(id="m.A", label="A", kind="component"),
            Node(id="m.S", label="S", kind="spec"),
        ),
        edges=(
            Edge(
                source="m.A", target="m.S", kind="uses_param",
                via_param="spec",
            ),
        ),
    )
    out = render_mermaid(graph)
    assert 'm_A --"Param(spec)"--> m_S' in out


def test_has_variant_edge_label() -> None:
    graph = Graph(
        nodes=(
            Node(id="m.D", label="D", kind="design"),
            Node(id="m.D.show", label="show", kind="variant"),
        ),
        edges=(
            Edge(source="m.D", target="m.D.show", kind="has_variant"),
        ),
    )
    out = render_mermaid(graph)
    assert 'm_D --"variant"--> m_D_show' in out


def test_variant_builds_edge_label() -> None:
    graph = Graph(
        nodes=(
            Node(id="m.D.show", label="show", kind="variant"),
            Node(id="m.C", label="C", kind="component"),
        ),
        edges=(
            Edge(source="m.D.show", target="m.C", kind="variant_builds"),
        ),
    )
    out = render_mermaid(graph)
    assert 'm_D_show --"builds"--> m_C' in out


def test_contains_edge_uses_contains_label() -> None:
    graph = Graph(
        nodes=(
            Node(id="m.Outer", label="Outer", kind="component"),
            Node(id="m.Inner", label="Inner", kind="component"),
        ),
        edges=(
            Edge(source="m.Outer", target="m.Inner", kind="contains"),
        ),
    )
    out = render_mermaid(graph)
    assert 'm_Outer --"contains"--> m_Inner' in out


def test_reads_attr_edge_label_lists_attrs() -> None:
    graph = Graph(
        nodes=(
            Node(id="m.A", label="A", kind="component"),
            Node(id="m.S", label="S", kind="spec"),
        ),
        edges=(
            Edge(
                source="m.A", target="m.S", kind="reads_attr",
                attrs_read=("height", "outer_d"),
            ),
        ),
    )
    out = render_mermaid(graph)
    assert 'm_A --"height, outer_d"--> m_S' in out


# =============================================================================
# Header / structure
# =============================================================================


def test_output_starts_with_graph_td() -> None:
    graph = Graph(nodes=(), edges=())
    out = render_mermaid(graph)
    assert out.startswith("graph TD\n")


def test_output_ends_with_newline() -> None:
    graph = Graph(
        nodes=(Node(id="m.A", label="A", kind="component"),),
        edges=(),
    )
    out = render_mermaid(graph)
    assert out.endswith("\n")


def test_empty_graph_renders_just_header() -> None:
    out = render_mermaid(Graph(nodes=(), edges=()))
    assert out.strip() == "graph TD"


# =============================================================================
# Determinism
# =============================================================================


def test_render_is_deterministic() -> None:
    graph = Graph(
        nodes=(
            Node(id="m.A", label="A", kind="component"),
            Node(id="m.B", label="B", kind="component"),
            Node(id="m.S", label="S", kind="spec"),
        ),
        edges=(
            Edge(source="m.A", target="m.B", kind="inherits"),
            Edge(
                source="m.A", target="m.S", kind="uses_param",
                via_param="spec",
            ),
        ),
    )
    a = render_mermaid(graph)
    b = render_mermaid(graph)
    assert a == b


# =============================================================================
# Id normalization
# =============================================================================


def test_dotted_ids_normalized_to_underscores() -> None:
    graph = Graph(
        nodes=(
            Node(id="sub.foo.Bracket", label="Bracket", kind="component"),
        ),
        edges=(),
    )
    out = render_mermaid(graph)
    assert "sub_foo_Bracket(Bracket)" in out


def test_id_collision_disambiguated_with_numeric_suffix() -> None:
    # ``foo.bar.Baz`` and ``foo_bar.Baz`` both normalize to
    # ``foo_bar_Baz`` under the simple ``.`` -> ``_`` mapping.
    # The renderer must keep the rendered ids distinct.
    graph = Graph(
        nodes=(
            Node(id="foo.bar.Baz", label="Baz", kind="component"),
            Node(id="foo_bar.Baz", label="Baz", kind="component"),
        ),
        edges=(),
    )
    out = render_mermaid(graph)
    assert "foo_bar_Baz(Baz)" in out
    assert "foo_bar_Baz_2(Baz)" in out


def test_id_collision_propagates_to_edges() -> None:
    # Edges referencing colliding ids must use the disambiguated
    # form too — otherwise an edge points at the wrong node.
    graph = Graph(
        nodes=(
            Node(id="foo.bar.A", label="A", kind="component"),
            Node(id="foo_bar.A", label="A", kind="component"),
        ),
        edges=(
            # Edge from the second-occurrence (collision) node.
            Edge(
                source="foo_bar.A", target="foo.bar.A",
                kind="inherits",
            ),
        ),
    )
    out = render_mermaid(graph)
    # The disambiguated source connects to the original-id target.
    assert "foo_bar_A_2 --> foo_bar_A" in out


def test_three_way_collision_disambiguated() -> None:
    graph = Graph(
        nodes=(
            Node(id="a.b.X", label="X", kind="component"),
            Node(id="a_b.X", label="X", kind="component"),
            Node(id="a.b_X", label="X", kind="component"),
        ),
        edges=(),
    )
    out = render_mermaid(graph)
    assert "a_b_X(X)" in out
    assert "a_b_X_2(X)" in out
    assert "a_b_X_3(X)" in out


def test_module_prefix_disambiguates_same_class_name() -> None:
    # Two classes called "Foo" in different modules — the normalized
    # ids must differ.
    graph = Graph(
        nodes=(
            Node(id="a.Foo", label="Foo", kind="component"),
            Node(id="b.Foo", label="Foo", kind="component"),
        ),
        edges=(),
    )
    out = render_mermaid(graph)
    assert "a_Foo(Foo)" in out
    assert "b_Foo(Foo)" in out


# =============================================================================
# Multi-edge formatting
# =============================================================================


def test_full_graph_layout_sample() -> None:
    graph = Graph(
        nodes=(
            Node(id="m.BatterySpec", label="BatterySpec", kind="spec"),
            Node(id="m.Holder", label="Holder", kind="component"),
        ),
        edges=(
            Edge(
                source="m.Holder", target="m.BatterySpec",
                kind="reads_attr", attrs_read=("outer_d",),
            ),
            Edge(
                source="m.Holder", target="m.BatterySpec",
                kind="uses_param", via_param="spec",
            ),
        ),
    )
    out = render_mermaid(graph)
    expected = (
        "graph TD\n"
        "  m_BatterySpec{BatterySpec}\n"
        "  m_Holder(Holder)\n"
        '  m_Holder --"outer_d"--> m_BatterySpec\n'
        '  m_Holder --"Param(spec)"--> m_BatterySpec\n'
    )
    assert out == expected
