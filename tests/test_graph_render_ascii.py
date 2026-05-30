"""Tests for the ASCII renderer.

Covers the section structure (header, nodes, edges, warnings),
per-kind sort order, edge-extras formatting (uses_param,
reads_attr), label parentheticals for transforms whose registered
name differs from the identifier, path relativization against
project_root, determinism across runs, and empty-section handling.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.graph.model import Edge, Graph, Node
from scadwright.graph.render_ascii import render_ascii


# =============================================================================
# Header
# =============================================================================


def test_header_carries_project_root_and_counts() -> None:
    g = Graph(
        nodes=(Node(id="m.A", label="A", kind="component"),),
        edges=(),
        project_root=Path("/tmp/proj"),
    )
    out = render_ascii(g)
    first_line = out.splitlines()[0]
    assert first_line == "# scadwright graph: /tmp/proj  (1 nodes, 0 edges, 0 warnings)"


def test_header_when_project_root_missing() -> None:
    g = Graph(
        nodes=(),
        edges=(),
    )
    out = render_ascii(g)
    assert "(unknown)" in out.splitlines()[0]


# =============================================================================
# Empty sections
# =============================================================================


def test_empty_graph_shows_none_markers() -> None:
    out = render_ascii(Graph(nodes=(), edges=()))
    assert "## nodes\n(none)" in out
    assert "## edges\n(none)" in out
    assert "## warnings\n(none)" in out


# =============================================================================
# Node section
# =============================================================================


def test_nodes_sorted_by_kind_then_id() -> None:
    g = Graph(
        nodes=(
            Node(id="m.Cc", label="Cc", kind="component"),
            Node(id="m.Aa", label="Aa", kind="component"),
            Node(id="m.S", label="S", kind="spec"),
            Node(id="m.D", label="D", kind="design"),
        ),
        edges=(),
    )
    out = render_ascii(g)
    # Find the order of node identifiers in the output.
    nodes_section = out.split("## nodes\n", 1)[1].split("\n##", 1)[0]
    body = nodes_section.strip().splitlines()
    kinds_in_order = [line.split()[0] for line in body]
    # Alphabetical kind order: component, design, spec.
    assert kinds_in_order == ["component", "component", "design", "spec"]
    # Within component group, ids alphabetize.
    component_lines = [line for line in body if line.startswith("component")]
    assert component_lines[0].endswith("m.Aa")
    assert component_lines[1].endswith("m.Cc")


def test_node_line_includes_path_and_line(tmp_path: Path) -> None:
    file_path = tmp_path / "widget.py"
    g = Graph(
        nodes=(Node(
            id="m.A", label="A", kind="component",
            file_path=file_path, line=42,
        ),),
        edges=(),
        project_root=tmp_path,
    )
    out = render_ascii(g)
    assert "widget.py:42" in out


def test_node_line_without_path() -> None:
    g = Graph(
        nodes=(Node(id="m.A", label="A", kind="component"),),
        edges=(),
    )
    out = render_ascii(g)
    # Bare id with no trailing location component.
    body = out.split("## nodes\n", 1)[1].splitlines()[0]
    assert body == "component  m.A"


def test_transform_label_differing_from_identifier_shown_in_parens() -> None:
    g = Graph(
        nodes=(Node(
            id="m.actual_name", label="alias", kind="transform",
        ),),
        edges=(),
    )
    out = render_ascii(g)
    assert "m.actual_name (alias)" in out


def test_transform_label_matching_identifier_not_parenthesized() -> None:
    g = Graph(
        nodes=(Node(id="m.foo", label="foo", kind="transform"),),
        edges=(),
    )
    out = render_ascii(g)
    assert "m.foo (" not in out


# =============================================================================
# Edge section
# =============================================================================


def test_edges_grouped_by_source_with_header_line() -> None:
    g = Graph(
        nodes=(
            Node(id="m.A", label="A", kind="component"),
            Node(id="m.B", label="B", kind="component"),
        ),
        edges=(
            Edge(source="m.A", target="m.B", kind="contains"),
            Edge(source="m.A", target="m.B", kind="inherits"),
        ),
    )
    out = render_ascii(g)
    edges_section = out.split("## edges\n", 1)[1].split("\n##", 1)[0]
    lines = edges_section.strip().splitlines()
    # Source header on its own line, edges indented.
    assert lines[0] == "m.A"
    assert lines[1].startswith("  ")
    assert lines[2].startswith("  ")


def test_edges_sorted_alphabetically_by_kind_then_target() -> None:
    g = Graph(
        nodes=(
            Node(id="m.A", label="A", kind="component"),
            Node(id="m.B", label="B", kind="component"),
            Node(id="m.C", label="C", kind="component"),
        ),
        edges=tuple(sorted([
            Edge(source="m.A", target="m.C", kind="uses_transform"),
            Edge(source="m.A", target="m.B", kind="contains"),
            Edge(source="m.A", target="m.B", kind="inherits"),
        ], key=lambda e: (e.source, e.target, e.kind))),
    )
    out = render_ascii(g)
    edges_section = out.split("## edges\n", 1)[1].split("\n##", 1)[0]
    lines = [line.strip() for line in edges_section.strip().splitlines() if line.startswith("  ")]
    # contains < inherits < uses_transform alphabetically.
    assert lines[0].startswith("contains")
    assert lines[1].startswith("inherits")
    assert lines[2].startswith("uses_transform")


def test_uses_param_edge_shows_via_paramname() -> None:
    g = Graph(
        nodes=(
            Node(id="m.A", label="A", kind="component"),
            Node(id="m.S", label="S", kind="spec"),
        ),
        edges=(Edge(
            source="m.A", target="m.S", kind="uses_param", via_param="spec",
        ),),
    )
    out = render_ascii(g)
    assert "(via spec)" in out


def test_reads_attr_edge_shows_all_attrs() -> None:
    g = Graph(
        nodes=(
            Node(id="m.A", label="A", kind="component"),
            Node(id="m.S", label="S", kind="spec"),
        ),
        edges=(Edge(
            source="m.A", target="m.S", kind="reads_attr",
            attrs_read=("alpha", "beta", "gamma"),
        ),),
    )
    out = render_ascii(g)
    assert "[alpha, beta, gamma]" in out


def test_uses_transform_edge_target_format() -> None:
    g = Graph(
        nodes=(
            Node(id="m.A", label="A", kind="component"),
            Node(id="m.foo", label="foo", kind="transform"),
        ),
        edges=(Edge(
            source="m.A", target="m.foo", kind="uses_transform",
        ),),
    )
    out = render_ascii(g)
    assert "uses_transform" in out
    assert "m.foo" in out


def test_source_without_outgoing_edges_absent_from_edges_section() -> None:
    g = Graph(
        nodes=(
            Node(id="m.A", label="A", kind="component"),
            Node(id="m.S", label="S", kind="spec"),
        ),
        edges=(Edge(
            source="m.A", target="m.S", kind="contains",
        ),),
    )
    out = render_ascii(g)
    edges_section = out.split("## edges\n", 1)[1].split("\n##", 1)[0]
    # m.S appears as a target but not as a source header.
    assert "m.S" in out
    source_headers = [
        line for line in edges_section.splitlines()
        if line and not line.startswith(" ")
    ]
    assert source_headers == ["m.A"]


# =============================================================================
# Warnings section
# =============================================================================


def test_warnings_section_lists_each_warning() -> None:
    g = Graph(
        nodes=(),
        edges=(),
        warnings=(
            (Path("/tmp/a.py"), "duplicate transform 'foo'"),
            (Path("/tmp/b.py"), "duplicate transform 'bar'"),
        ),
        project_root=Path("/tmp"),
    )
    out = render_ascii(g)
    warnings_section = out.split("## warnings\n", 1)[1]
    assert "a.py: duplicate transform 'foo'" in warnings_section
    assert "b.py: duplicate transform 'bar'" in warnings_section


# =============================================================================
# Path relativization
# =============================================================================


def test_paths_relativized_against_project_root(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    file_path = tmp_path / "sub" / "widget.py"
    file_path.touch()
    g = Graph(
        nodes=(Node(
            id="sub.widget.A", label="A", kind="component",
            file_path=file_path, line=1,
        ),),
        edges=(),
        project_root=tmp_path,
    )
    out = render_ascii(g)
    assert "sub/widget.py:1" in out
    assert str(tmp_path) not in out.split("## nodes\n", 1)[1]


def test_paths_outside_root_use_absolute(tmp_path: Path) -> None:
    outside = Path("/elsewhere/file.py")
    g = Graph(
        nodes=(Node(
            id="elsewhere.file.A", label="A", kind="component",
            file_path=outside, line=10,
        ),),
        edges=(),
        project_root=tmp_path,
    )
    out = render_ascii(g)
    assert "/elsewhere/file.py:10" in out


# =============================================================================
# Determinism
# =============================================================================


def test_render_is_deterministic() -> None:
    g = Graph(
        nodes=(
            Node(id="m.A", label="A", kind="component"),
            Node(id="m.B", label="B", kind="component"),
            Node(id="m.S", label="S", kind="spec"),
        ),
        edges=(
            Edge(source="m.A", target="m.S", kind="reads_attr",
                 attrs_read=("a", "b")),
            Edge(source="m.B", target="m.S", kind="reads_attr",
                 attrs_read=("c",)),
        ),
    )
    assert render_ascii(g) == render_ascii(g)


# =============================================================================
# End-to-end: every node kind + every edge kind
# =============================================================================


def test_all_node_kinds_and_edge_kinds_rendered() -> None:
    g = Graph(
        nodes=(
            Node(id="m.Plate", label="Plate", kind="component"),
            Node(id="m.Box", label="Box", kind="design"),
            Node(id="m.Box.show", label="show", kind="variant"),
            Node(id="m.Box.Sub", label="Sub", kind="component"),
            Node(id="m.Cfg", label="Cfg", kind="spec"),
            Node(id="m.foo", label="foo", kind="transform"),
        ),
        edges=(
            Edge(source="m.Box", target="m.Plate", kind="contains"),
            Edge(source="m.Box", target="m.Box.show", kind="has_variant"),
            Edge(source="m.Box.Sub", target="m.Plate", kind="inherits"),
            Edge(source="m.Box.show", target="m.Plate", kind="variant_builds"),
            Edge(source="m.Plate", target="m.Cfg", kind="reads_attr",
                 attrs_read=("size",)),
            Edge(source="m.Plate", target="m.Cfg", kind="uses_param",
                 via_param="cfg"),
            Edge(source="m.Plate", target="m.foo", kind="uses_transform"),
        ),
    )
    out = render_ascii(g)
    for kind in ("component", "design", "spec", "transform", "variant"):
        assert kind in out
    for kind in (
        "contains", "has_variant", "inherits", "reads_attr",
        "uses_param", "uses_transform", "variant_builds",
    ):
        assert kind in out
    assert "(via cfg)" in out
    assert "[size]" in out
