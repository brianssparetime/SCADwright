"""Tests for the top-level graph builder.

Covers each edge kind on synthetic projects, multi-edge dedupe of
``reads_attr`` across equations + build, deterministic ordering,
single-file vs directory inputs, and the unknown-category filter.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.graph.build import build_graph
from scadwright.graph.model import Edge, Graph, Node


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _by_id(graph: Graph) -> dict[str, Node]:
    return {n.id: n for n in graph.nodes}


def _edges_of_kind(graph: Graph, kind: str) -> list[Edge]:
    return [e for e in graph.edges if e.kind == kind]


# =============================================================================
# Nodes per category
# =============================================================================


def test_each_category_emits_a_node(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Spec\n"
        "from scadwright.design import Design\n"
        "class S(Spec):\n"
        "    pass\n"
        "class C(Component):\n"
        "    pass\n"
        "class D(Design):\n"
        "    pass\n"
    ))
    graph = build_graph(tmp_path)
    by_id = _by_id(graph)
    assert by_id["main.S"].kind == "spec"
    assert by_id["main.C"].kind == "component"
    assert by_id["main.D"].kind == "design"


def test_unknown_category_classes_omitted(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "class Plain:\n"
        "    pass\n"
        "class Inner(Plain):\n"
        "    pass\n"
    ))
    graph = build_graph(tmp_path)
    assert graph.nodes == ()
    assert graph.edges == ()


def test_node_label_is_class_name(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class Bracket(Component):\n"
        "    pass\n"
    ))
    [node] = build_graph(tmp_path).nodes
    assert node.label == "Bracket"
    assert node.id == "main.Bracket"


# =============================================================================
# Inherits edges
# =============================================================================


def test_inherits_edge_for_project_local_base(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class _Plate(Component):\n"
        "    pass\n"
        "class Bracket(_Plate):\n"
        "    pass\n"
    ))
    edges = _edges_of_kind(build_graph(tmp_path), "inherits")
    assert len(edges) == 1
    [e] = edges
    assert e.source == "main.Bracket"
    assert e.target == "main._Plate"


def test_no_inherits_edge_for_external_base(tmp_path: Path) -> None:
    # ``class Bracket(Component)`` — Component is external; we don't
    # render scadwright base classes as nodes, so no inherits edge.
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class Bracket(Component):\n"
        "    pass\n"
    ))
    edges = _edges_of_kind(build_graph(tmp_path), "inherits")
    assert edges == []


def test_inherits_edge_across_files(tmp_path: Path) -> None:
    _write(tmp_path, "bases.py", (
        "from scadwright import Component\n"
        "class _Plate(Component):\n"
        "    pass\n"
    ))
    _write(tmp_path, "widget.py", (
        "from bases import _Plate\n"
        "class Bracket(_Plate):\n"
        "    pass\n"
    ))
    edges = _edges_of_kind(build_graph(tmp_path), "inherits")
    assert len(edges) == 1
    [e] = edges
    assert e.source == "widget.Bracket"
    assert e.target == "bases._Plate"


# =============================================================================
# uses_param edges
# =============================================================================


def test_uses_param_edge_to_spec(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Spec, Param\n"
        "class BatterySpec(Spec):\n"
        "    pass\n"
        "class Holder(Component):\n"
        "    spec = Param(BatterySpec)\n"
    ))
    edges = _edges_of_kind(build_graph(tmp_path), "uses_param")
    assert len(edges) == 1
    [e] = edges
    assert e.source == "main.Holder"
    assert e.target == "main.BatterySpec"
    assert e.via_param == "spec"


def test_uses_param_edge_to_component(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Param\n"
        "class Inner(Component):\n"
        "    pass\n"
        "class Outer(Component):\n"
        "    inner = Param(Inner)\n"
    ))
    edges = _edges_of_kind(build_graph(tmp_path), "uses_param")
    assert len(edges) == 1
    [e] = edges
    assert e.target == "main.Inner"
    assert e.via_param == "inner"


def test_uses_param_skips_primitive_types(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Param\n"
        "class Bracket(Component):\n"
        "    width = Param(float)\n"
        "    height = Param(int)\n"
    ))
    edges = _edges_of_kind(build_graph(tmp_path), "uses_param")
    assert edges == []


# =============================================================================
# reads_attr edges
# =============================================================================


def test_reads_attr_edge_from_equations(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        '    equations = "x = spec.outer_d"\n'
    ))
    edges = _edges_of_kind(build_graph(tmp_path), "reads_attr")
    [e] = edges
    assert e.source == "main.Cam"
    assert e.target == "main.CamSpec"
    assert e.attrs_read == ("outer_d",)


def test_reads_attr_edge_from_build(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        "    def build(self):\n"
        "        return self.spec.height\n"
    ))
    edges = _edges_of_kind(build_graph(tmp_path), "reads_attr")
    [e] = edges
    assert e.attrs_read == ("height",)


def test_reads_attr_merges_equations_and_build(tmp_path: Path) -> None:
    # Reads from both equations and build collapse into a single
    # edge with the union of attribute names.
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        '    equations = "x = spec.outer_d"\n'
        "    def build(self):\n"
        "        return self.spec.height\n"
    ))
    edges = _edges_of_kind(build_graph(tmp_path), "reads_attr")
    assert len(edges) == 1
    [e] = edges
    assert e.attrs_read == ("height", "outer_d")


def test_reads_attr_dedupe_across_equations_and_build(tmp_path: Path) -> None:
    # Same attribute read in BOTH equations and build appears once.
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Spec, Param\n"
        "class S(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(S)\n"
        '    equations = "x = spec.attr"\n'
        "    def build(self):\n"
        "        return self.spec.attr\n"
    ))
    edges = _edges_of_kind(build_graph(tmp_path), "reads_attr")
    [e] = edges
    assert e.attrs_read == ("attr",)


# =============================================================================
# contains edges (composition)
# =============================================================================


def test_contains_edge_for_build_instantiation(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class Inner(Component):\n"
        "    pass\n"
        "class Outer(Component):\n"
        "    def build(self):\n"
        "        return Inner()\n"
    ))
    edges = _edges_of_kind(build_graph(tmp_path), "contains")
    assert len(edges) == 1
    [e] = edges
    assert e.source == "main.Outer"
    assert e.target == "main.Inner"


def test_contains_edge_dedupes_repeats(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class Inner(Component):\n"
        "    pass\n"
        "class Outer(Component):\n"
        "    def build(self):\n"
        "        return [Inner(), Inner(), Inner()]\n"
    ))
    edges = _edges_of_kind(build_graph(tmp_path), "contains")
    assert len(edges) == 1


def test_no_contains_edge_for_curated_factories(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "from scadwright.primitives import cube\n"
        "class A(Component):\n"
        "    def build(self):\n"
        "        return cube([1,1,1])\n"
    ))
    assert _edges_of_kind(build_graph(tmp_path), "contains") == []


def test_contains_edge_only_from_components(tmp_path: Path) -> None:
    # Specs have no build() method, so no contains edges originate
    # from them even if their bodies syntactically call something.
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Spec\n"
        "class Inner(Component):\n"
        "    pass\n"
        "class S(Spec):\n"
        "    pass\n"
        "class Outer(Component):\n"
        "    def build(self):\n"
        "        return Inner()\n"
    ))
    contains = _edges_of_kind(build_graph(tmp_path), "contains")
    sources = {e.source for e in contains}
    assert sources == {"main.Outer"}


# =============================================================================
# Robustness: parse errors and missing optional deps
# =============================================================================


def test_parse_errors_surfaced_in_graph(tmp_path: Path) -> None:
    _write(tmp_path, "good.py", (
        "from scadwright import Component\n"
        "class Bracket(Component):\n"
        "    pass\n"
    ))
    _write(tmp_path, "broken.py", (
        "from scadwright import Component\n"
        "class Bad(Component):\n"
        "    def build(self):\n"
        "        return foo(\n"
    ))
    graph = build_graph(tmp_path)
    # Good file's class still in the graph.
    assert any(n.id == "good.Bracket" for n in graph.nodes)
    # Broken file shows up in parse_errors, not silently swallowed.
    assert len(graph.parse_errors) == 1
    err_path, err_msg = graph.parse_errors[0]
    assert err_path.name == "broken.py"
    assert "(" in err_msg or "line" in err_msg


def test_no_parse_errors_field_empty(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class A(Component):\n"
        "    pass\n"
    ))
    assert build_graph(tmp_path).parse_errors == ()


def test_graph_builds_without_sympy(
    tmp_path: Path, monkeypatch,
) -> None:
    # A project with equations should still produce a graph when
    # sympy isn't available — equation-derived edges drop, but
    # the rest of the graph (Param, build, inheritance) survives.
    import sys

    _write(tmp_path, "main.py", (
        "from scadwright import Component, Spec, Param\n"
        "class S(Spec):\n"
        "    pass\n"
        "class Holder(Component):\n"
        "    spec = Param(S)\n"
        '    equations = "wall = spec.cells * 2"\n'
    ))
    # Block sympy: setting sys.modules entry to None makes
    # subsequent ``import sympy`` raise ImportError.
    monkeypatch.setitem(sys.modules, "sympy", None)
    graph = build_graph(tmp_path)
    # Param edge survives (doesn't touch sympy).
    assert any(
        e.kind == "uses_param" for e in graph.edges
    )
    # No equation-derived attribute-read edge.
    assert not any(
        e.kind == "reads_attr" for e in graph.edges
    )


# =============================================================================
# Variant nodes + edges
# =============================================================================


def test_variant_nodes_emitted_under_design(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import variant, Component\n"
        "from scadwright.design import Design\n"
        "class C(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    c = C()\n"
        "    @variant(default=True)\n"
        "    def show(self):\n"
        "        return self.c\n"
    ))
    graph = build_graph(tmp_path)
    by_id = _by_id(graph)
    assert "main.Box.show" in by_id
    assert by_id["main.Box.show"].kind == "variant"
    assert by_id["main.Box.show"].label == "show"


def test_has_variant_edge(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import variant, Component\n"
        "from scadwright.design import Design\n"
        "class C(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    c = C()\n"
        "    @variant()\n"
        "    def show(self):\n"
        "        return self.c\n"
    ))
    edges = _edges_of_kind(build_graph(tmp_path), "has_variant")
    assert len(edges) == 1
    [e] = edges
    assert e.source == "main.Box"
    assert e.target == "main.Box.show"


def test_variant_builds_edge(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import variant, Component\n"
        "from scadwright.design import Design\n"
        "class C(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    c = C()\n"
        "    @variant()\n"
        "    def show(self):\n"
        "        return self.c\n"
    ))
    edges = _edges_of_kind(build_graph(tmp_path), "variant_builds")
    [e] = edges
    assert e.source == "main.Box.show"
    assert e.target == "main.C"


def test_design_with_no_variants_still_emits_design_node(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright.design import Design\n"
        "class Box(Design):\n"
        "    pass\n"
    ))
    graph = build_graph(tmp_path)
    by_id = _by_id(graph)
    assert by_id["main.Box"].kind == "design"
    # No variant nodes, no variant-related edges.
    assert all(n.kind != "variant" for n in graph.nodes)
    assert _edges_of_kind(graph, "has_variant") == []
    assert _edges_of_kind(graph, "variant_builds") == []


# =============================================================================
# Determinism
# =============================================================================


def test_nodes_sorted_by_id(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class Zeta(Component):\n"
        "    pass\n"
        "class Alpha(Component):\n"
        "    pass\n"
        "class Mu(Component):\n"
        "    pass\n"
    ))
    ids = [n.id for n in build_graph(tmp_path).nodes]
    assert ids == sorted(ids)


def test_edges_sorted_deterministically(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Spec, Param\n"
        "class S1(Spec):\n"
        "    pass\n"
        "class S2(Spec):\n"
        "    pass\n"
        "class Holder(Component):\n"
        "    a = Param(S2)\n"
        "    b = Param(S1)\n"
    ))
    edges = build_graph(tmp_path).edges
    keys = [(e.source, e.target, e.kind) for e in edges]
    assert keys == sorted(keys)


# =============================================================================
# Single-file input
# =============================================================================


def test_build_graph_on_single_file(tmp_path: Path) -> None:
    f = _write(tmp_path, "widget.py", (
        "from scadwright import Component\n"
        "class Bracket(Component):\n"
        "    pass\n"
    ))
    graph = build_graph(f)
    assert len(graph.nodes) == 1
    # Module path uses the file's parent as the implicit root.
    assert graph.nodes[0].label == "Bracket"


# =============================================================================
# End-to-end on a richer scenario
# =============================================================================


def test_full_graph_with_all_edge_kinds(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Spec, Param\n"
        "class BatterySpec(Spec):\n"
        "    pass\n"
        "class _PlatedComponent(Component):\n"
        "    pass\n"
        "class Holder(_PlatedComponent):\n"
        "    spec = Param(BatterySpec)\n"
        '    equations = "x = spec.outer_d"\n'
        "    def build(self):\n"
        "        return self.spec.height\n"
    ))
    graph = build_graph(tmp_path)
    by_id = _by_id(graph)
    assert set(by_id.keys()) == {
        "main.BatterySpec", "main._PlatedComponent", "main.Holder",
    }
    inherits = _edges_of_kind(graph, "inherits")
    uses_param = _edges_of_kind(graph, "uses_param")
    reads_attr = _edges_of_kind(graph, "reads_attr")
    # Holder inherits _PlatedComponent.
    assert any(
        e.source == "main.Holder" and e.target == "main._PlatedComponent"
        for e in inherits
    )
    # Holder uses Param of BatterySpec.
    assert any(
        e.source == "main.Holder" and e.target == "main.BatterySpec"
        for e in uses_param
    )
    # Holder reads outer_d + height from BatterySpec.
    assert any(
        e.source == "main.Holder" and e.target == "main.BatterySpec"
        and set(e.attrs_read) == {"outer_d", "height"}
        for e in reads_attr
    )
