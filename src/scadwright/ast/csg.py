"""CSG operation AST nodes."""

from __future__ import annotations

from dataclasses import dataclass

from scadwright.ast.base import Node


@dataclass(frozen=True)
class Union(Node):
    children: tuple[Node, ...]


@dataclass(frozen=True)
class Difference(Node):
    """SCAD difference: first child minus the rest."""

    children: tuple[Node, ...]


@dataclass(frozen=True)
class Intersection(Node):
    children: tuple[Node, ...]


@dataclass(frozen=True)
class Hull(Node):
    """Convex hull of all children."""

    children: tuple[Node, ...]


@dataclass(frozen=True)
class Minkowski(Node):
    """Minkowski sum of all children."""

    children: tuple[Node, ...]
