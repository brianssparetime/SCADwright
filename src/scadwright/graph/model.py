"""Graph data model: nodes, edges, and the assembled :class:`Graph`.

The renderer modules (Mermaid, DOT, JSON) consume this shape and
produce their respective output formats. The model is rendering-
agnostic — labels are plain strings, ids are deterministic, and
the structure is fully serializable.

A node's ``id`` is its module path joined with its class name
(``"sub.foo.Bracket"``). Module-less files (a single-file project
where the file is itself the project root) get the bare class
name. Ids are stable across runs, sortable, and distinguishable
when two classes in different modules share a name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


NodeKind = Literal["component", "spec", "design", "variant"]
EdgeKind = Literal[
    "uses_param", "reads_attr", "inherits", "contains",
    "has_variant", "variant_builds",
]


@dataclass(frozen=True)
class Node:
    """A graph node — one per Component / Spec / Design class, plus
    one per ``@variant`` method on each Design.

    ``id`` is the dotted module path joined with the class name
    (and, for variants, the method name appended:
    ``"main.BatteryBox.print"``). ``label`` is the display name
    (the class name, or just the variant method name).
    """
    id: str
    label: str
    kind: NodeKind


@dataclass(frozen=True)
class Edge:
    """A directed edge between two :class:`Node`s.

    ``kind`` distinguishes the relationship:

    - ``"uses_param"``: the source has ``via_param = Param(target)``.
      ``via_param`` carries the Param name for the edge label.
    - ``"reads_attr"``: the source reads attribute(s) of an instance
      whose type is the target. ``attrs_read`` carries the
      sorted-unique attribute names (``"outer_d"``, ``"height"``,
      etc.) — possibly several per edge since multiple reads on the
      same target collapse into one labeled edge.
    - ``"inherits"``: the source class's MRO includes the target.
      No supplemental fields needed.
    - ``"contains"``: the source's ``build`` method instantiates the
      target Component. No supplemental fields needed; the edge's
      mere presence is the information.
    - ``"has_variant"``: the source Design hosts the target Variant
      sub-node. No supplemental fields.
    - ``"variant_builds"``: the source Variant produces the target
      Component (return / yield path). No supplemental fields.

    The unused supplemental fields default to empty so
    ``dataclass(frozen=True)`` instances are comparable across edge
    kinds.
    """
    source: str
    target: str
    kind: EdgeKind
    via_param: str | None = None
    attrs_read: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Graph:
    """A built graph: nodes plus the edges between them.

    ``nodes`` is sorted by ``id``; ``edges`` is sorted by
    ``(source, target, kind)`` so renderers produce deterministic
    output across runs.

    ``parse_errors`` lists any ``.py`` files the walker couldn't
    parse, as ``(path, error_message)`` pairs. Files with parse
    errors contribute nothing to the graph; the field is the
    machine-readable signal that the graph may be missing classes
    a CLI / downstream tool should warn about. Sorted by path for
    determinism.
    """
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    parse_errors: tuple[tuple[Path, str], ...] = field(
        default_factory=tuple,
    )
