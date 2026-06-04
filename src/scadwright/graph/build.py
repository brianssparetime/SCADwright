"""High-level project-graph builder.

:func:`build_graph` is the top-level entry: walk a project, build
the class and transform registries, run the per-class and
per-transform extractors, and emit a :class:`Graph` of nodes and
edges. The CLI subcommand calls this once per invocation;
renderers consume the result.

The builder skips classes whose category resolves to ``"unknown"``
— third-party bases, generic-only inheritance, or unresolvable
chains. Those classes don't contribute nodes; their absence keeps
the graph focused on the project's scadwright-derived structure.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from scadwright.graph.extract import (
    AttributeRead,
    ancestor_classes,
    build_effective_params_by_class,
    build_params_by_class,
    extract_build_attribute_reads,
    extract_build_instantiations,
    extract_class_attribute_reads,
    extract_component_instantiations,
    extract_equations_attribute_reads,
    extract_params,
    extract_transform_uses,
    extract_variants,
    one_hop_param_reads,
)
from scadwright.graph.model import Edge, Graph, Node
from scadwright.project_index.registry import (
    ClassRegistry,
    ResolvedClass,
    build_class_registry,
    resolve_name_in_file,
)
from scadwright.project_index.transforms import (
    ResolvedTransform,
    TransformRegistry,
    build_transform_registry,
)
from scadwright.project_index.walk import FileInfo, walk_project


def build_graph(
    project_root: str | Path,
    *,
    exclude: Iterable[str] = (),
) -> Graph:
    """Walk a project and produce a :class:`Graph`.

    ``project_root`` may be a directory (recursed) or a single
    ``.py`` file. For a single-file run, the file's parent acts as
    the implicit project root for module-path computation; the
    graph contains only the classes in that file.

    ``exclude`` is a sequence of glob patterns passed through to
    :func:`scadwright.project_index.walk.walk_project`; matched
    files don't contribute classes, transforms, or edges to the
    result. See that function's docstring for pattern semantics.

    Returns a graph with sorted nodes and edges so consumers
    (renderers, diff tooling) get deterministic output.
    """
    root = Path(project_root)
    base_root = root if root.is_dir() else root.parent
    files = walk_project(root, exclude=exclude)
    registry = build_class_registry(files, base_root)
    transforms = build_transform_registry(files, registry, base_root)
    files_by_path: dict[Path, FileInfo] = {f.path: f for f in files}
    params_by_class = build_params_by_class(registry, files_by_path, base_root)
    effective_params, local_bindings, invalid_bindings = (
        build_effective_params_by_class(registry, files_by_path, base_root)
    )

    nodes: list[Node] = []
    edges: list[Edge] = []
    emitted_node_ids: set[str] = set()

    def add_node(node: Node) -> None:
        if node.id in emitted_node_ids:
            return
        emitted_node_ids.add(node.id)
        nodes.append(node)

    for cls in registry.classes.values():
        if cls.category == "unknown":
            continue
        # Transform-category classes get their node emitted by the
        # transform loop below (so the label is the registered name,
        # not the class name). Edges still emit here — the class is
        # in class_registry and its body is the scope we walk.
        if cls.category != "transform":
            add_node(_node_for(cls))
        file_info = files_by_path.get(cls.file_path)
        if file_info is None:
            continue
        edges.extend(_edges_for_class(
            cls, file_info, registry, transforms, base_root,
            params_by_class, effective_params, local_bindings, files_by_path,
        ))
        if cls.category == "design":
            v_nodes, v_edges = _variant_nodes_and_edges(
                cls, file_info, registry, transforms, base_root,
            )
            for n in v_nodes:
                add_node(n)
            edges.extend(v_edges)

    # Transform nodes + outgoing edges for decorator-form transforms.
    # Subclass-form transforms emit their outgoing edges via the
    # class loop above; register-call-form transforms have no body
    # to walk and contribute only the node.
    for transform in transforms.by_name.values():
        add_node(_node_for_transform(transform))
        if transform.kind != "decorator":
            continue
        file_info = files_by_path.get(transform.file_path)
        if file_info is None:
            continue
        edges.extend(_edges_for_transform(
            transform, file_info, registry, transforms, base_root,
        ))

    parse_errors = tuple(sorted(
        (
            (f.path, f.parse_error) for f in files
            if f.parse_error is not None
        ),
        key=lambda pair: pair[0],
    ))
    warnings = tuple(sorted(
        list(transforms.warnings) + _binding_warnings(
            invalid_bindings, registry, base_root,
        ),
        key=lambda pair: (str(pair[0]), pair[1]),
    ))
    return Graph(
        nodes=tuple(sorted(nodes, key=lambda n: n.id)),
        edges=tuple(sorted(
            edges, key=lambda e: (e.source, e.target, e.kind),
        )),
        parse_errors=parse_errors,
        warnings=warnings,
        project_root=base_root,
    )


def _node_for(cls: ResolvedClass) -> Node:
    """Build the :class:`Node` for one class. Id combines module
    path and class name for global uniqueness; file_path and line
    carry the source location. Transform-category classes are
    emitted by :func:`_node_for_transform` instead, so the node
    label can carry the registered name rather than the class
    name."""
    node_id = _node_id(cls)
    return Node(
        id=node_id,
        label=cls.name,
        kind=cls.category,
        file_path=cls.file_path,
        line=cls.line + 1,
    )


def _node_for_transform(t: ResolvedTransform) -> Node:
    """Build the :class:`Node` for one project-defined transform.

    Node id is ``<module>.<identifier>`` for decorator and subclass
    forms (parallel to class node ids) and a synthesized
    ``<module>.register_<registered_name>`` for the bare
    register-call form (which has no identifier of its own).
    The label is always the registered name — the verb users invoke.
    """
    return Node(
        id=_transform_node_id(t),
        label=t.registered_name,
        kind="transform",
        file_path=t.file_path,
        line=t.line + 1,
    )


def _transform_node_id(t: ResolvedTransform) -> str:
    """Canonical node id for a :class:`ResolvedTransform`."""
    if t.kind == "register_call":
        identifier = f"register_{t.registered_name}"
    else:
        identifier = t.identifier_name
    return f"{t.module_path}.{identifier}" if t.module_path else identifier


def _edges_for_class(
    cls: ResolvedClass,
    file_info: FileInfo,
    registry: ClassRegistry,
    transforms: TransformRegistry,
    project_root: Path,
    params_by_class: dict,
    effective_params: dict,
    local_bindings: dict,
    files_by_path: dict,
) -> list[Edge]:
    """Emit every outgoing edge for a single class.

    Order: ``inherits`` edges first (one per resolved base), then
    ``uses_param`` (one per Param whose type resolves to a project
    Component or Spec), then ``reads_attr`` (merged from equations,
    ``self.<param>.<attr>`` reads, and direct class-attribute reads
    like ``SpecName.attr``), then ``contains`` (Component
    instantiations), then ``uses_transform`` (chained calls into
    project transforms).

    Two parameter maps are in play. ``params_by_class`` is the class's
    own-body Params; the ``uses_param`` loop reads it so a typed Param
    draws its edge from the class that declares it, not from every
    descendant. ``effective_params`` is the MRO-merged, override-applied
    map; the read extractors read it so a subclass resolves attributes
    off a Param its base declared. ``local_bindings`` carries the Params
    a class rebinds to a project class via a plain class attribute (the
    ``spec = PentaconSixMount`` shape), which emit through
    :func:`_override_binding_edges`.
    """
    out: list[Edge] = []
    source_id = _node_id(cls)

    # Inheritance edges. Targets in any project category (Component,
    # Spec, Design, transform-subclass) get an edge.
    for base_node in cls.ast_node.bases:
        target = _resolve_base_target(
            base_node, file_info, registry, project_root,
        )
        if target is None or target.category == "unknown":
            continue
        if target.category not in (
            "component", "spec", "design", "transform",
        ):
            continue
        out.append(Edge(
            source=source_id,
            target=_target_node_id(target, transforms),
            kind="inherits",
        ))

    # Param-driven edges fire only on Components and Specs — Designs
    # compose Components via class attributes, transforms via free
    # functions; neither uses Params.
    params: tuple = ()
    if cls.category in ("component", "spec"):
        params = params_by_class.get((cls.file_path, cls.name), ())
        for p in params:
            if (
                p.type_resolves_to is not None
                and p.type_resolves_to.category in ("component", "spec")
            ):
                out.append(Edge(
                    source=source_id,
                    target=_target_node_id(p.type_resolves_to, transforms),
                    kind="uses_param",
                    via_param=p.name,
                ))

    # reads_attr edges, merged across equations, self.<chain>.<attr>,
    # and direct ClassName.<attr> reads. The exclude set keeps the
    # last source from double-emitting reads the first two already
    # handled. Param-mediated reads have priority for the Component/Spec
    # case (their AttributeRead carries the resolved target class);
    # bare ``self`` references and own-Param names skip the class-attr
    # extractor regardless of category.
    eq_reads = ()
    build_reads = ()
    if cls.category in ("component", "spec"):
        eq_reads = extract_equations_attribute_reads(
            cls, file_info, effective_params,
        )
        build_reads = extract_build_attribute_reads(cls, effective_params)
    exclude_names = frozenset({"self"} | {p.name for p in params})
    class_reads = extract_class_attribute_reads(
        cls.ast_node, file_info, registry, project_root, exclude_names,
    )

    # Override-binding edges: a Param this class rebinds to a project
    # Spec / Component via a plain class attribute. The reads live in the
    # inherited equations and build body, resolved here to the bound class.
    out.extend(_override_binding_edges(
        cls, source_id, local_bindings, registry, files_by_path,
        project_root, transforms,
    ))

    out.extend(_collapsed_attr_edges(
        source_id, eq_reads + build_reads + class_reads, transforms,
    ))

    # contains edges from OtherComponent(...) instantiation. Components
    # use the build()-method-aware extractor (also picks up class-level
    # composition shapes); transforms walk the whole class body.
    if cls.category == "component":
        for ref in extract_build_instantiations(
            cls, file_info, registry, project_root,
        ):
            out.append(Edge(
                source=source_id,
                target=_target_node_id(ref.target, transforms),
                kind="contains",
            ))
    elif cls.category == "transform":
        for target in extract_component_instantiations(
            cls.ast_node, file_info, registry, project_root,
        ):
            out.append(Edge(
                source=source_id,
                target=_target_node_id(target, transforms),
                kind="contains",
            ))

    # uses_transform edges from chained `.X(...)` calls where X is a
    # project-registered transform. All class categories participate —
    # Components, Specs (rare), Designs (uncommon at class scope),
    # and subclass-form transforms calling other transforms.
    for target in extract_transform_uses(cls.ast_node, transforms):
        out.append(Edge(
            source=source_id,
            target=_transform_node_id(target),
            kind="uses_transform",
        ))

    return out


def _override_binding_edges(
    cls: ResolvedClass,
    source_id: str,
    local_bindings: dict,
    registry: ClassRegistry,
    files_by_path: dict[Path, FileInfo],
    project_root: Path,
    transforms: TransformRegistry,
) -> list[Edge]:
    """Emit ``uses_param`` and ``reads_attr`` for the Params ``cls``
    rebinds to a project Spec / Component via a plain class attribute.

    The binding lives on ``cls`` but the reads live in the inherited
    equations and ``build`` body, so the attribute names are gathered
    one hop off the bound Param across ``cls`` and every ancestor, then
    resolved to the bound class. A binding with no reads still emits its
    ``uses_param`` edge: the dependency is real even if no attribute is
    read off it yet.
    """
    binds: dict = local_bindings.get((cls.file_path, cls.name), {})
    if not binds:
        return []

    param_names = frozenset(binds)
    reads: dict[str, set[str]] = {}
    for c in [cls, *ancestor_classes(
        cls, registry, files_by_path, project_root,
    )]:
        c_file = files_by_path.get(c.file_path)
        if c_file is None:
            continue
        for name, attrs in one_hop_param_reads(
            c.ast_node, c_file.source, param_names,
        ).items():
            reads.setdefault(name, set()).update(attrs)

    out: list[Edge] = []
    for name, target in binds.items():
        target_id = _target_node_id(target, transforms)
        out.append(Edge(
            source=source_id, target=target_id,
            kind="uses_param", via_param=name,
        ))
        attrs = reads.get(name)
        if attrs:
            out.append(Edge(
                source=source_id, target=target_id,
                kind="reads_attr", attrs_read=tuple(sorted(attrs)),
            ))
    return out


def _binding_warnings(
    invalid_bindings: list,
    registry: ClassRegistry,
    project_root: Path,
) -> list[tuple[Path, str]]:
    """Render the invalid bare-class bindings as graph warnings.

    A Component class or a parameterized Spec class bound to an inherited
    Param raises at runtime (see ``_reject_class_valued_override``). On
    source that hasn't been run, the graph would otherwise omit the
    dependency in silence; this surfaces it instead, naming the binding
    and the fix.
    """
    out: list[tuple[Path, str]] = []
    for b in invalid_bindings:
        cls_name = b.source.name
        target = b.target.name
        if b.reason == "component":
            msg = (
                f"{cls_name}.{b.name}: binds the Component class "
                f"`{target}` to a parameter; this raises at runtime. "
                f"Bind an instance `{b.name} = {target}(...)`, or declare "
                f"`Param({target})` for a caller-supplied parameter."
            )
        else:
            msg = (
                f"{cls_name}.{b.name}: binds the parameterized Spec class "
                f"`{target}`; this raises at runtime. Bind an instance "
                f"`{b.name} = {target}(...)`."
            )
        out.append((b.source.file_path, msg))
    return out


def _edges_for_transform(
    t: ResolvedTransform,
    file_info: FileInfo,
    registry: ClassRegistry,
    transforms: TransformRegistry,
    project_root: Path,
) -> list[Edge]:
    """Emit outgoing edges for a decorator-form transform.

    Subclass-form transforms get their edges through
    :func:`_edges_for_class` since they have a class entry in the
    class registry; register-call-form transforms have no body to
    walk and emit no outgoing edges. This helper handles the
    decorator-form free-function body.

    Edge kinds: ``reads_attr`` (project-class attribute access in
    the function body), ``contains`` (Component instantiations),
    ``uses_transform`` (chained calls into other project transforms).
    """
    out: list[Edge] = []
    source_id = _transform_node_id(t)
    scope = t.ast_node  # the FunctionDef

    class_reads = extract_class_attribute_reads(
        scope, file_info, registry, project_root,
    )
    out.extend(_collapsed_attr_edges(source_id, class_reads, transforms))

    for target in extract_component_instantiations(
        scope, file_info, registry, project_root,
    ):
        out.append(Edge(
            source=source_id,
            target=_target_node_id(target, transforms),
            kind="contains",
        ))

    for target in extract_transform_uses(scope, transforms):
        if _transform_node_id(target) == source_id:
            # Don't emit self-loops from a transform that recursively
            # invokes itself (rare, but the chained-call walk would
            # otherwise produce a noisy self-edge).
            continue
        out.append(Edge(
            source=source_id,
            target=_transform_node_id(target),
            kind="uses_transform",
        ))

    return out


def _target_node_id(
    target: ResolvedClass,
    transforms: TransformRegistry,
) -> str:
    """Compute the node id for a target ResolvedClass, taking
    transform-category classes through the transform-node-id path
    so subclass-form transforms get the same id whether referenced
    via inherits, contains, or the transform registry.
    """
    if target.category != "transform":
        return _node_id(target)
    # Look up the corresponding transform entry; subclass-form
    # transforms register under their class name as identifier.
    for t in transforms.by_name.values():
        if (
            t.kind == "subclass"
            and t.file_path == target.file_path
            and t.identifier_name == target.name
        ):
            return _transform_node_id(t)
    # A transform-category class without a discoverable registration
    # (no string-literal ``name``) still gets a node id parallel to
    # other classes; the transform registry just won't have it.
    return _node_id(target)


def _variant_nodes_and_edges(
    cls: ResolvedClass,
    file_info: FileInfo,
    registry: ClassRegistry,
    transforms: TransformRegistry,
    project_root: Path,
) -> tuple[list[Node], list[Edge]]:
    """Build the Variant sub-nodes and their edges for one Design.

    For each ``@variant``-decorated method on the Design, emit one
    Variant node (id ``<design_id>.<method>``, kind ``"variant"``)
    and a ``has_variant`` edge linking the Design to the Variant.
    For each Component the variant builds, emit one
    ``variant_builds`` edge from the Variant to the Component;
    direct ``ProjectClass.attr`` reads in the variant body emit
    ``reads_attr`` edges; chained calls into project transforms
    emit ``uses_transform`` edges.

    Variants are full participants in the graph — when a variant
    body reads a Spec's class attribute or calls a transform, that
    dependency surfaces from the variant sub-node rather than
    being rolled up into the parent Design.

    Designs with no variants produce empty lists; the surrounding
    builder handles that gracefully.
    """
    design_id = _node_id(cls)
    nodes: list[Node] = []
    edges: list[Edge] = []
    for v in extract_variants(cls, file_info, registry, project_root):
        variant_id = f"{design_id}.{v.method_name}"
        method = _find_variant_method(cls.ast_node, v.method_name)
        variant_line = method.lineno if method is not None else cls.line + 1
        nodes.append(Node(
            id=variant_id, label=v.method_name, kind="variant",
            file_path=cls.file_path, line=variant_line,
        ))
        edges.append(Edge(
            source=design_id, target=variant_id, kind="has_variant",
        ))
        for target in v.builds:
            edges.append(Edge(
                source=variant_id,
                target=_target_node_id(target, transforms),
                kind="variant_builds",
            ))

        # Walk the variant method body for reads_attr and uses_transform.
        if method is None:
            continue
        class_reads = extract_class_attribute_reads(
            method, file_info, registry, project_root,
            exclude_names=frozenset({"self"}),
        )
        edges.extend(
            _collapsed_attr_edges(variant_id, class_reads, transforms),
        )
        for target in extract_transform_uses(method, transforms):
            edges.append(Edge(
                source=variant_id,
                target=_transform_node_id(target),
                kind="uses_transform",
            ))
    return nodes, edges


def _find_variant_method(
    class_node, method_name: str,
):
    """Return the ``FunctionDef`` for a named method on a class, or
    ``None`` if not present. Used to scope variant-body extraction
    to the right method.
    """
    for stmt in class_node.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if stmt.name == method_name:
                return stmt
    return None


def _collapsed_attr_edges(
    source_id: str,
    reads: tuple[AttributeRead, ...] | list[AttributeRead],
    transforms: TransformRegistry,
) -> list[Edge]:
    """Collapse multiple ``AttributeRead`` entries with the same
    target into one ``reads_attr`` edge whose ``attrs_read`` is the
    sorted-unique set of attribute names.

    Reads with ``target=None`` (primitive Params, unresolvable
    bases) are dropped — they don't correspond to a node in the
    graph. Self-reads (source and target the same node) drop too:
    a class reading its own class attributes isn't a cross-class
    dependency.
    """
    by_target: dict[str, set[str]] = {}
    for read in reads:
        if read.target is None:
            continue
        target_id = _target_node_id(read.target, transforms)
        if target_id == source_id:
            continue
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
    from scadwright.project_index.registry import _base_to_dotted_name

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
