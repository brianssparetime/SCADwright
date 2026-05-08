"""High-level project-graph builder.

:func:`build_graph` is the top-level entry: walk a project, build
the class registry, run the per-class extractors, and emit a
:class:`Graph` of nodes and edges. The CLI subcommand calls this
once per invocation; renderers consume the result.

The builder skips classes whose category resolves to ``"unknown"``
— third-party bases, generic-only inheritance, or unresolvable
chains. Those classes don't contribute nodes; their absence keeps
the graph focused on the project's scadwright-derived structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scadwright.graph.extract import (
    AttributeRead,
    extract_build_attribute_reads,
    extract_build_instantiations,
    extract_equations_attribute_reads,
    extract_params,
    extract_variants,
)
from scadwright.graph.model import Edge, Graph, Node
from scadwright.graph.registry import (
    ClassRegistry,
    ResolvedClass,
    build_class_registry,
    resolve_name_in_file,
)
from scadwright.graph.walk import FileInfo, walk_project


def build_graph(project_root: str | Path) -> Graph:
    """Walk a project and produce a :class:`Graph`.

    ``project_root`` may be a directory (recursed) or a single
    ``.py`` file. For a single-file run, the file's parent acts as
    the implicit project root for module-path computation; the
    graph contains only the classes in that file.

    Returns a graph with sorted nodes and edges so consumers
    (renderers, diff tooling) get deterministic output.
    """
    root = Path(project_root)
    base_root = root if root.is_dir() else root.parent
    files = walk_project(root)
    registry = build_class_registry(files, base_root)
    files_by_path: dict[Path, FileInfo] = {f.path: f for f in files}

    nodes: list[Node] = []
    edges: list[Edge] = []

    for cls in registry.classes.values():
        if cls.category == "unknown":
            continue
        nodes.append(_node_for(cls))
        file_info = files_by_path.get(cls.file_path)
        if file_info is None:
            continue
        edges.extend(_edges_for_class(
            cls, file_info, registry, base_root,
        ))
        if cls.category == "design":
            v_nodes, v_edges = _variant_nodes_and_edges(
                cls, file_info, registry, base_root,
            )
            nodes.extend(v_nodes)
            edges.extend(v_edges)

    parse_errors = tuple(sorted(
        (
            (f.path, f.parse_error) for f in files
            if f.parse_error is not None
        ),
        key=lambda pair: pair[0],
    ))
    return Graph(
        nodes=tuple(sorted(nodes, key=lambda n: n.id)),
        edges=tuple(sorted(
            edges, key=lambda e: (e.source, e.target, e.kind),
        )),
        parse_errors=parse_errors,
    )


def _node_for(cls: ResolvedClass) -> Node:
    """Build the :class:`Node` for one class. Id combines module
    path and class name for global uniqueness."""
    node_id = (
        f"{cls.module_path}.{cls.name}"
        if cls.module_path else cls.name
    )
    return Node(id=node_id, label=cls.name, kind=cls.category)


def _edges_for_class(
    cls: ResolvedClass,
    file_info: FileInfo,
    registry: ClassRegistry,
    project_root: Path,
) -> list[Edge]:
    """Emit every outgoing edge for a single class.

    Order: ``inherits`` edges first (one per resolved base), then
    ``uses_param`` (one per Param whose type resolves to a known
    Component or Spec), then ``reads_attr`` (one per (source, target)
    pair, with attribute names from equations and build merged into
    the label).
    """
    out: list[Edge] = []
    source_id = _node_id(cls)

    # Inheritance edges.
    for base_node in cls.ast_node.bases:
        target = _resolve_base_target(
            base_node, file_info, registry, project_root,
        )
        if target is None or target.category == "unknown":
            continue
        if target.category not in ("component", "spec", "design"):
            continue
        out.append(Edge(
            source=source_id,
            target=_node_id(target),
            kind="inherits",
        ))

    # Param-driven and read-driven edges only fire on Components
    # and Specs (Designs don't declare Params or equations directly).
    if cls.category not in ("component", "spec"):
        return out

    params = extract_params(cls, file_info, registry, project_root)

    # uses_param edges.
    for p in params:
        if (
            p.type_resolves_to is not None
            and p.type_resolves_to.category in ("component", "spec")
        ):
            out.append(Edge(
                source=source_id,
                target=_node_id(p.type_resolves_to),
                kind="uses_param",
                via_param=p.name,
            ))

    # reads_attr edges, merged across equations + build paths.
    eq_reads = extract_equations_attribute_reads(cls, file_info, params)
    build_reads = extract_build_attribute_reads(cls, params)
    out.extend(_collapsed_attr_edges(source_id, eq_reads + build_reads))

    # contains edges from OtherComponent(...) instantiation in
    # build(). Components only — Specs don't have build() methods.
    if cls.category == "component":
        for ref in extract_build_instantiations(
            cls, file_info, registry, project_root,
        ):
            out.append(Edge(
                source=source_id,
                target=_node_id(ref.target),
                kind="contains",
            ))

    return out


def _variant_nodes_and_edges(
    cls: ResolvedClass,
    file_info: FileInfo,
    registry: ClassRegistry,
    project_root: Path,
) -> tuple[list[Node], list[Edge]]:
    """Build the Variant sub-nodes and their edges for one Design.

    For each ``@variant``-decorated method on the Design, emit one
    Variant node (id ``<design_id>.<method>``, kind ``"variant"``)
    and a ``has_variant`` edge linking the Design to the Variant.
    For each Component the variant builds, emit one
    ``variant_builds`` edge from the Variant to the Component.

    Designs with no variants produce empty lists; the surrounding
    builder handles that gracefully.
    """
    design_id = _node_id(cls)
    nodes: list[Node] = []
    edges: list[Edge] = []
    for v in extract_variants(cls, file_info, registry, project_root):
        variant_id = f"{design_id}.{v.method_name}"
        nodes.append(Node(
            id=variant_id, label=v.method_name, kind="variant",
        ))
        edges.append(Edge(
            source=design_id, target=variant_id, kind="has_variant",
        ))
        for target in v.builds:
            edges.append(Edge(
                source=variant_id,
                target=_node_id(target),
                kind="variant_builds",
            ))
    return nodes, edges


def _collapsed_attr_edges(
    source_id: str,
    reads: tuple[AttributeRead, ...],
) -> list[Edge]:
    """Collapse multiple ``AttributeRead`` entries with the same
    target into one ``reads_attr`` edge whose ``attrs_read`` is the
    sorted-unique set of attribute names.

    Reads with ``target=None`` (primitive Params, unresolvable
    bases) are dropped — they don't correspond to a node in the
    graph.
    """
    by_target: dict[str, set[str]] = {}
    for read in reads:
        if read.target is None:
            continue
        target_id = _node_id(read.target)
        by_target.setdefault(target_id, set()).add(read.attr)
    out: list[Edge] = []
    for target_id, attrs in by_target.items():
        out.append(Edge(
            source=source_id,
            target=target_id,
            kind="reads_attr",
            attrs_read=tuple(sorted(attrs)),
        ))
    return out


def _resolve_base_target(
    base_node, file_info: FileInfo, registry: ClassRegistry,
    project_root: Path,
) -> ResolvedClass | None:
    """Resolve a base-class expression to its :class:`ResolvedClass`,
    or ``None`` for shapes the resolver can't handle / external
    bases.
    """
    from scadwright.graph.registry import _base_to_dotted_name

    name = _base_to_dotted_name(base_node)
    if name is None:
        return None
    return resolve_name_in_file(name, file_info, registry, project_root)


def _node_id(cls: ResolvedClass) -> str:
    """Compute the Node id for a :class:`ResolvedClass` — same shape
    as :func:`_node_for`'s id construction.
    """
    return (
        f"{cls.module_path}.{cls.name}"
        if cls.module_path else cls.name
    )
