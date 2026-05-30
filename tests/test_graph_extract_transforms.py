"""Tests for transform discovery and usage in the graph.

Covers the three registration shapes (decorator-form free function,
``Transform`` subclass with ``name`` literal, module-level
``register("name", ...)`` call), duplicate-name conflict handling,
chained-call usage detection including across files, and the
end-to-end graph build emitting transform nodes and
``uses_transform`` edges with the right labels and shapes.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.graph.build import build_graph
from scadwright.graph.render_dot import render_dot
from scadwright.graph.render_json import render_json
from scadwright.graph.render_mermaid import render_mermaid
from scadwright.project_index.registry import build_class_registry
from scadwright.project_index.transforms import (
    build_transform_registry,
    extract_transform_uses,
)
from scadwright.project_index.walk import walk_project


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _registry(tmp_path: Path):
    files = walk_project(tmp_path)
    classes = build_class_registry(files, tmp_path)
    return files, classes, build_transform_registry(files, classes, tmp_path)


# =============================================================================
# Decorator form discovery
# =============================================================================


def test_decorator_transform_discovery(tmp_path: Path) -> None:
    _write(tmp_path, "verbs.py", (
        "from scadwright.transforms import transform\n"
        "@transform('port_cutout', inline=True)\n"
        "def port_cutout(node, *, on):\n"
        "    return node\n"
    ))
    _files, _classes, transforms = _registry(tmp_path)
    assert "port_cutout" in transforms.by_name
    t = transforms.by_name["port_cutout"]
    assert t.kind == "decorator"
    assert t.identifier_name == "port_cutout"
    assert t.registered_name == "port_cutout"


def test_decorator_registered_name_can_differ_from_function_name(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "verbs.py", (
        "from scadwright.transforms import transform\n"
        "@transform('alias')\n"
        "def actual_name(node):\n"
        "    return node\n"
    ))
    _files, _classes, transforms = _registry(tmp_path)
    t = transforms.by_name["alias"]
    assert t.identifier_name == "actual_name"
    assert t.registered_name == "alias"


def test_decorator_with_keyword_name(tmp_path: Path) -> None:
    _write(tmp_path, "verbs.py", (
        "from scadwright.transforms import transform\n"
        "@transform(name='kw_named')\n"
        "def fn(node):\n"
        "    return node\n"
    ))
    _files, _classes, transforms = _registry(tmp_path)
    assert "kw_named" in transforms.by_name


def test_decorator_with_non_literal_name_drops(tmp_path: Path) -> None:
    _write(tmp_path, "verbs.py", (
        "from scadwright.transforms import transform\n"
        "NAME = 'computed'\n"
        "@transform(NAME)\n"
        "def fn(node):\n"
        "    return node\n"
    ))
    _files, _classes, transforms = _registry(tmp_path)
    assert transforms.by_name == {}


def test_aliased_transform_import_still_resolves(tmp_path: Path) -> None:
    _write(tmp_path, "verbs.py", (
        "from scadwright.transforms import transform as t\n"
        "@t('aliased_path')\n"
        "def fn(node):\n"
        "    return node\n"
    ))
    _files, _classes, transforms = _registry(tmp_path)
    assert "aliased_path" in transforms.by_name


def test_unrelated_decorator_named_transform_drops(tmp_path: Path) -> None:
    _write(tmp_path, "verbs.py", (
        "def transform(name):\n"
        "    def wrap(fn):\n"
        "        return fn\n"
        "    return wrap\n"
        "@transform('should_not_register')\n"
        "def fn(node):\n"
        "    return node\n"
    ))
    _files, _classes, transforms = _registry(tmp_path)
    assert transforms.by_name == {}


# =============================================================================
# Subclass form discovery
# =============================================================================


def test_subclass_transform_discovery(tmp_path: Path) -> None:
    _write(tmp_path, "verbs.py", (
        "from scadwright.transforms import Transform\n"
        "class MyVerb(Transform):\n"
        "    name = 'my_verb'\n"
        "    def expand(self, child):\n"
        "        return child\n"
    ))
    _files, _classes, transforms = _registry(tmp_path)
    t = transforms.by_name["my_verb"]
    assert t.kind == "subclass"
    assert t.identifier_name == "MyVerb"
    assert t.registered_name == "my_verb"


def test_subclass_without_name_attribute_drops(tmp_path: Path) -> None:
    _write(tmp_path, "verbs.py", (
        "from scadwright.transforms import Transform\n"
        "class NoName(Transform):\n"
        "    def expand(self, child):\n"
        "        return child\n"
    ))
    _files, _classes, transforms = _registry(tmp_path)
    assert transforms.by_name == {}


# =============================================================================
# register-call form discovery
# =============================================================================


def test_register_call_discovery(tmp_path: Path) -> None:
    _write(tmp_path, "verbs.py", (
        "from scadwright._custom_transforms.base import Transform, register\n"
        "class _MyT(Transform):\n"
        "    def expand(self, child):\n"
        "        return child\n"
        "register('register_call_form', _MyT())\n"
    ))
    _files, _classes, transforms = _registry(tmp_path)
    assert "register_call_form" in transforms.by_name
    t = transforms.by_name["register_call_form"]
    assert t.kind == "register_call"


# =============================================================================
# Duplicate name handling
# =============================================================================


def test_duplicate_registration_warns_and_keeps_first(tmp_path: Path) -> None:
    _write(tmp_path, "a.py", (
        "from scadwright.transforms import transform\n"
        "@transform('twice')\n"
        "def first(node):\n"
        "    return node\n"
    ))
    _write(tmp_path, "b.py", (
        "from scadwright.transforms import transform\n"
        "@transform('twice')\n"
        "def second(node):\n"
        "    return node\n"
    ))
    _files, _classes, transforms = _registry(tmp_path)
    assert "twice" in transforms.by_name
    # File 'a.py' sorts before 'b.py'; first wins.
    assert transforms.by_name["twice"].identifier_name == "first"
    assert len(transforms.warnings) == 1
    _path, msg = transforms.warnings[0]
    assert "twice" in msg


# =============================================================================
# extract_transform_uses
# =============================================================================


def test_chained_call_to_known_transform(tmp_path: Path) -> None:
    _write(tmp_path, "verbs.py", (
        "from scadwright.transforms import transform\n"
        "@transform('port_cutout')\n"
        "def port_cutout(node, *, on):\n"
        "    return node\n"
        "from scadwright import Component\n"
        "class Case(Component):\n"
        "    def build(self):\n"
        "        body = None\n"
        "        return body.port_cutout(on='+x')\n"
    ))
    files, classes, transforms = _registry(tmp_path)
    cls = next(c for c in classes.classes.values() if c.name == "Case")
    [used] = extract_transform_uses(cls.ast_node, transforms)
    assert used.registered_name == "port_cutout"


def test_chained_call_to_unknown_name_drops(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component\n"
        "class Widget(Component):\n"
        "    def build(self):\n"
        "        return self.translate([1, 0, 0])\n"
    ))
    files, classes, transforms = _registry(tmp_path)
    cls = next(c for c in classes.classes.values() if c.name == "Widget")
    assert extract_transform_uses(cls.ast_node, transforms) == ()


def test_multiple_uses_of_same_transform_collapse(tmp_path: Path) -> None:
    _write(tmp_path, "design.py", (
        "from scadwright.transforms import transform\n"
        "@transform('foo')\n"
        "def foo(node):\n"
        "    return node\n"
        "from scadwright import Component\n"
        "class C(Component):\n"
        "    def build(self):\n"
        "        x = None\n"
        "        x = x.foo()\n"
        "        x = x.foo()\n"
        "        return x.foo()\n"
    ))
    files, classes, transforms = _registry(tmp_path)
    cls = next(c for c in classes.classes.values() if c.name == "C")
    uses = extract_transform_uses(cls.ast_node, transforms)
    assert len(uses) == 1


# =============================================================================
# End-to-end graph build with transforms
# =============================================================================


def test_graph_emits_transform_node_and_uses_transform_edge(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "design.py", (
        "from scadwright.transforms import transform\n"
        "@transform('port_cutout')\n"
        "def port_cutout(node, *, on):\n"
        "    return node\n"
        "from scadwright import Component\n"
        "class Case(Component):\n"
        "    def build(self):\n"
        "        body = None\n"
        "        return body.port_cutout(on='+x')\n"
    ))
    graph = build_graph(tmp_path)
    transform_nodes = [n for n in graph.nodes if n.kind == "transform"]
    assert len(transform_nodes) == 1
    assert transform_nodes[0].label == "port_cutout"
    uses_edges = [e for e in graph.edges if e.kind == "uses_transform"]
    assert len(uses_edges) == 1
    assert uses_edges[0].source.endswith(".Case")
    assert uses_edges[0].target == transform_nodes[0].id


def test_variant_emits_uses_transform_edge(tmp_path: Path) -> None:
    _write(tmp_path, "design.py", (
        "from scadwright.transforms import transform\n"
        "@transform('chamfer')\n"
        "def chamfer(node, *, depth):\n"
        "    return node\n"
        "from scadwright import variant, Component\n"
        "from scadwright.design import Design\n"
        "class C(Component):\n"
        "    def build(self):\n"
        "        return None\n"
        "class D(Design):\n"
        "    c = C()\n"
        "    @variant(default=True)\n"
        "    def show(self):\n"
        "        return self.c.chamfer(depth=1)\n"
    ))
    graph = build_graph(tmp_path)
    variant_uses = [
        e for e in graph.edges
        if e.kind == "uses_transform" and ".show" in e.source
    ]
    assert len(variant_uses) == 1


def test_subclass_transform_node_and_outgoing_edges(tmp_path: Path) -> None:
    _write(tmp_path, "verbs.py", (
        "from scadwright.transforms import Transform\n"
        "from scadwright import Component\n"
        "class Plate(Component):\n"
        "    def build(self):\n"
        "        return None\n"
        "class MyVerb(Transform):\n"
        "    name = 'my_verb'\n"
        "    def expand(self, child):\n"
        "        return Plate()\n"
    ))
    graph = build_graph(tmp_path)
    transform_nodes = [n for n in graph.nodes if n.kind == "transform"]
    assert len(transform_nodes) == 1
    assert transform_nodes[0].label == "my_verb"
    # Subclass form walks the class body — instantiating Plate
    # should emit a contains edge.
    contains_from_transform = [
        e for e in graph.edges
        if e.kind == "contains" and e.source == transform_nodes[0].id
    ]
    assert len(contains_from_transform) == 1


def test_transform_reads_spec_class_attribute(tmp_path: Path) -> None:
    _write(tmp_path, "design.py", (
        "from scadwright.transforms import transform\n"
        "from scadwright import Spec\n"
        "class Cfg(Spec):\n"
        "    equations = '''\n"
        "        wall_thk = 2\n"
        "    '''\n"
        "@transform('cut')\n"
        "def cut(node):\n"
        "    depth = Cfg.wall_thk\n"
        "    return node\n"
    ))
    graph = build_graph(tmp_path)
    # The transform's outgoing reads_attr edge points at Cfg.
    reads_from_transform = [
        e for e in graph.edges
        if e.kind == "reads_attr" and "cut" in e.source.split(".")[-1]
    ]
    assert len(reads_from_transform) == 1
    assert reads_from_transform[0].attrs_read == ("wall_thk",)


# =============================================================================
# Renderer surface
# =============================================================================


def test_renderers_handle_transform_nodes_and_edges(tmp_path: Path) -> None:
    _write(tmp_path, "design.py", (
        "from scadwright.transforms import transform\n"
        "@transform('foo')\n"
        "def foo(node):\n"
        "    return node\n"
        "from scadwright import Component\n"
        "class C(Component):\n"
        "    def build(self):\n"
        "        return (None).foo()\n"
    ))
    graph = build_graph(tmp_path)
    mermaid = render_mermaid(graph)
    assert "[/foo/]" in mermaid
    assert '--"uses"-->' in mermaid

    dot = render_dot(graph)
    assert "shape=parallelogram" in dot
    assert 'label="uses"' in dot

    rendered_json = render_json(graph)
    assert '"kind": "transform"' in rendered_json
    assert '"kind": "uses_transform"' in rendered_json


# =============================================================================
# Spec class-attribute pattern (s2-evolving's dominant case)
# =============================================================================


def test_spec_consumed_via_class_attribute_across_files(tmp_path: Path) -> None:
    _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class Bayonet(Spec):\n"
        "    equations = '''\n"
        "        cam_barrel_od = 60.5\n"
        "        cam_lug_axial = 1.1\n"
        "    '''\n"
    ))
    _write(tmp_path, "housing.py", (
        "from scadwright import Component\n"
        "from spec import Bayonet\n"
        "class Housing(Component):\n"
        "    outer_d = Bayonet.cam_barrel_od\n"
        "    lug_axial = Bayonet.cam_lug_axial\n"
        "    def build(self):\n"
        "        return None\n"
    ))
    graph = build_graph(tmp_path)
    reads = [
        e for e in graph.edges
        if e.kind == "reads_attr" and "Housing" in e.source
    ]
    assert len(reads) == 1
    assert reads[0].target.endswith(".Bayonet")
    assert sorted(reads[0].attrs_read) == ["cam_barrel_od", "cam_lug_axial"]
