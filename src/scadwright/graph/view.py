"""Project view: a scadwright-native projection of a :class:`Graph`.

The :class:`Graph` is a generic node-and-edge model. Both human and
machine output want the same scadwright-native shape instead — parts
grouped as Designs / Components / Specs / Transforms, each with its
relationships named in the framework's own terms. :func:`assemble`
builds that shape once so the ASCII and JSON renderers don't each
re-walk the edge list and re-derive the vocabulary.

The view carries each entity's *forward* relationships (what it
depends on) fully resolved to display names, plus the *reverse*
relationships (what depends on it). The JSON renderer serializes the
forward side single-source; the ASCII renderer renders both.

Display names are the bare class / variant name, qualified with the
dotted id only when two nodes share a label — so the common case
reads cleanly and collisions stay unambiguous.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from scadwright.graph.model import Edge, Graph, Node


@dataclass(frozen=True)
class SpecUse:
    """A part's dependency on one Spec: the param it arrives through
    (when declared) and the fields read off it."""
    spec: str
    via_param: str | None
    fields: tuple[str, ...]


@dataclass(frozen=True)
class PartUse:
    """A part's dependency on another Component via a Param and/or
    attribute reads. Uncommon next to Spec use, but valid."""
    part: str
    via_param: str | None
    fields: tuple[str, ...]


@dataclass(frozen=True)
class VariantView:
    """A variant (or morph) of a Design: what it builds, whether it's
    the default, and — for a morph — its ordered stages."""
    name: str
    default: bool
    builds: tuple[str, ...]
    is_morph: bool = False
    stages: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Entity:
    """One Design / Component / Spec / Transform, with its forward and
    reverse relationships resolved to display names."""
    id: str
    name: str
    kind: str
    location: str | None
    # forward
    bases: tuple[str, ...] = ()
    spec_uses: tuple[SpecUse, ...] = ()
    part_uses: tuple[PartUse, ...] = ()
    contains: tuple[str, ...] = ()
    uses_transform: tuple[str, ...] = ()
    variants: tuple[VariantView, ...] = ()
    # reverse
    specialized_by: tuple[str, ...] = ()
    built_by: tuple[str, ...] = ()
    read_by: tuple[tuple[str, tuple[str, ...]], ...] = ()
    used_in: tuple[str, ...] = ()
    used_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectView:
    project: str
    designs: tuple[Entity, ...]
    components: tuple[Entity, ...]
    specs: tuple[Entity, ...]
    transforms: tuple[Entity, ...]
    warnings: tuple[tuple[str, str], ...]


def assemble(graph: Graph) -> ProjectView:
    """Project a :class:`Graph` into the scadwright-native view."""
    nodes = {n.id: n for n in graph.nodes}
    label_counts = Counter(n.label for n in graph.nodes)

    def disp(node_id: str) -> str:
        n = nodes.get(node_id)
        if n is None:
            return node_id
        return n.label if label_counts[n.label] == 1 else n.id

    out_edges: dict[str, list[Edge]] = defaultdict(list)
    in_edges: dict[str, list[Edge]] = defaultdict(list)
    for e in graph.edges:
        out_edges[e.source].append(e)
        in_edges[e.target].append(e)

    def loc(n: Node) -> str | None:
        return _location(n.file_path, n.line, graph.project_root)

    def kind_of(node_id: str) -> str | None:
        n = nodes.get(node_id)
        return n.kind if n is not None else None

    def design_of(variant_id: str) -> str:
        """The design id that owns a variant/morph node id."""
        return variant_id.rsplit(".", 1)[0]

    designs: list[Entity] = []
    components: list[Entity] = []
    specs: list[Entity] = []
    transforms: list[Entity] = []

    for n in sorted(graph.nodes, key=lambda x: disp(x.id).lower()):
        if n.kind == "component":
            components.append(_component(n, disp, loc, kind_of,
                                         out_edges, in_edges, design_of))
        elif n.kind == "spec":
            specs.append(_spec(n, disp, loc, in_edges))
        elif n.kind == "design":
            designs.append(_design(n, nodes, disp, loc, out_edges))
        elif n.kind == "transform":
            transforms.append(_transform(n, disp, loc, kind_of,
                                         out_edges, in_edges))
        # variant/morph nodes are folded into their Design, not listed.

    warnings = tuple(
        (_rel_path(p, graph.project_root), m) for p, m in graph.warnings
    )
    return ProjectView(
        project=graph.project_root.as_posix()
        if graph.project_root is not None else "(unknown)",
        designs=tuple(designs),
        components=tuple(components),
        specs=tuple(specs),
        transforms=tuple(transforms),
        warnings=warnings,
    )


def _component(n, disp, loc, kind_of, out_edges, in_edges, design_of):
    bases: list[str] = []
    # forward Spec/Part use: merge uses_param + reads_attr per target.
    via: dict[str, str] = {}
    fields: dict[str, tuple[str, ...]] = {}
    targets: list[str] = []
    contains: list[str] = []
    uses_tf: list[str] = []
    for e in out_edges.get(n.id, ()):
        if e.kind == "inherits":
            bases.append(disp(e.target))
        elif e.kind == "uses_param":
            if e.target not in via and e.target not in fields:
                targets.append(e.target)
            via[e.target] = e.via_param or ""
        elif e.kind == "reads_attr":
            if e.target not in via and e.target not in fields:
                targets.append(e.target)
            fields[e.target] = tuple(e.attrs_read)
        elif e.kind == "contains":
            contains.append(disp(e.target))
        elif e.kind == "uses_transform":
            uses_tf.append(disp(e.target))

    spec_uses: list[SpecUse] = []
    part_uses: list[PartUse] = []
    for t in targets:
        vp = via.get(t) or None
        fs = fields.get(t, ())
        if kind_of(t) == "spec":
            spec_uses.append(SpecUse(disp(t), vp, fs))
        else:
            part_uses.append(PartUse(disp(t), vp, fs))

    specialized_by: list[str] = []
    built_designs: list[str] = []
    used_in: list[str] = []
    seen_designs: set[str] = set()
    for e in in_edges.get(n.id, ()):
        if e.kind == "inherits":
            specialized_by.append(disp(e.source))
        elif e.kind == "variant_builds":
            did = design_of(e.source)
            if did not in seen_designs:
                seen_designs.add(did)
                built_designs.append(disp(did))
        elif e.kind == "contains":
            used_in.append(disp(e.source))

    return Entity(
        id=n.id, name=disp(n.id), kind="component", location=loc(n),
        bases=tuple(bases),
        spec_uses=tuple(spec_uses),
        part_uses=tuple(part_uses),
        contains=tuple(sorted(set(contains))),
        uses_transform=tuple(sorted(set(uses_tf))),
        specialized_by=tuple(sorted(set(specialized_by))),
        built_by=tuple(sorted(set(built_designs))),
        used_in=tuple(sorted(set(used_in))),
    )


def _spec(n, disp, loc, in_edges):
    field_readers: dict[str, set[str]] = defaultdict(set)
    for e in in_edges.get(n.id, ()):
        if e.kind == "reads_attr":
            for attr in e.attrs_read:
                field_readers[attr].add(disp(e.source))
    read_by = tuple(
        (fld, tuple(sorted(field_readers[fld])))
        for fld in sorted(field_readers)
    )
    return Entity(
        id=n.id, name=disp(n.id), kind="spec", location=loc(n),
        read_by=read_by,
    )


def _design(n, nodes, disp, loc, out_edges):
    variants: list[VariantView] = []
    for e in out_edges.get(n.id, ()):
        if e.kind != "has_variant":
            continue
        vnode = nodes.get(e.target)
        if vnode is None:
            continue
        builds = tuple(sorted(
            disp(ve.target) for ve in out_edges.get(vnode.id, ())
            if ve.kind == "variant_builds"
        ))
        variants.append(VariantView(
            name=vnode.label,
            default=vnode.default,
            builds=builds,
            is_morph=vnode.kind == "morph",
            stages=vnode.stages,
        ))
    # Regular variants first (source order via line), morphs last.
    variants.sort(key=lambda v: (v.is_morph, v.name))
    return Entity(
        id=n.id, name=disp(n.id), kind="design", location=loc(n),
        variants=tuple(variants),
    )


def _transform(n, disp, loc, kind_of, out_edges, in_edges):
    spec_uses: list[SpecUse] = []
    contains: list[str] = []
    uses_tf: list[str] = []
    for e in out_edges.get(n.id, ()):
        if e.kind == "reads_attr" and kind_of(e.target) == "spec":
            spec_uses.append(SpecUse(disp(e.target), None, tuple(e.attrs_read)))
        elif e.kind == "contains":
            contains.append(disp(e.target))
        elif e.kind == "uses_transform":
            uses_tf.append(disp(e.target))
    used_by = sorted({
        disp(e.source) for e in in_edges.get(n.id, ())
        if e.kind == "uses_transform"
    })
    return Entity(
        id=n.id, name=disp(n.id), kind="transform", location=loc(n),
        spec_uses=tuple(spec_uses),
        contains=tuple(sorted(set(contains))),
        uses_transform=tuple(sorted(set(uses_tf))),
        used_by=tuple(used_by),
    )


def _location(file_path: Path | None, line, project_root) -> str | None:
    if file_path is None:
        return None
    path = _rel_path(file_path, project_root)
    return f"{path}:{line}" if line is not None else path


def _rel_path(p: Path | None, project_root: Path | None) -> str:
    if p is None:
        return "(unknown)"
    if project_root is not None:
        try:
            return Path(p).relative_to(project_root).as_posix()
        except ValueError:
            return Path(p).as_posix()
    return Path(p).as_posix()


__all__ = [
    "Entity", "PartUse", "ProjectView", "SpecUse", "VariantView", "assemble",
]
