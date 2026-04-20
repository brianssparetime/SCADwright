"""Extrusion AST nodes."""

from __future__ import annotations

from dataclasses import dataclass

from scadwright.ast.base import Node


@dataclass(frozen=True)
class LinearExtrude(Node):
    child: Node
    height: float
    center: bool = False
    twist: float = 0.0
    slices: int | None = None
    scale: tuple[float, float] | float = 1.0
    convexity: int | None = None
    fn: float | None = None
    fa: float | None = None
    fs: float | None = None


@dataclass(frozen=True)
class RotateExtrude(Node):
    child: Node
    angle: float = 360.0
    convexity: int | None = None
    fn: float | None = None
    fa: float | None = None
    fs: float | None = None
