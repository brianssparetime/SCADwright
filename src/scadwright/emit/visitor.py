"""Generic visitor base and Emitter ABC for AST traversal.

`Visitor` dispatches `visit_<ClassName>(node)` per AST node type. Subclass it
for read-only traversals (e.g. bbox, validation, debugging tools).

`Emitter` is the contract for anything that turns an AST into serialized
output: it extends `Visitor` and requires an `emit_root(node)` entry point.
`SCADEmitter` is the canonical implementation. Writing a new backend means
subclassing `Emitter`, implementing `emit_root`, and providing a visitor for
every concrete AST node you expect to receive (the base `generic_visit`
raises `NotImplementedError` to flag missing handlers).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from scadwright.ast.base import Node


class Visitor:
    """Dispatches visit_<ClassName>(node). Subclasses implement per-node methods.

    Special case: Component instances don't match visit_<ClassName> (the user's
    subclass name is arbitrary). They're dispatched to visit_component, which
    typically materializes the built tree and recurses.
    """

    def visit(self, node: Node):
        # Late import to avoid a module cycle (component -> ast.base -> ... -> emit).
        from scadwright.component import Component

        if isinstance(node, Component):
            return self.visit_component(node)
        method = getattr(self, f"visit_{type(node).__name__}", None)
        if method is None:
            return self.generic_visit(node)
        return method(node)

    def visit_component(self, node):
        raise NotImplementedError(
            f"{type(self).__name__} has no visit_component handler"
        )

    def generic_visit(self, node: Node):
        raise NotImplementedError(
            f"{type(self).__name__} has no visit_{type(node).__name__}"
        )


class Emitter(Visitor, ABC):
    """Abstract base for AST-to-source emitters.

    Concrete backends (SCAD, hypothetical JSON-IR, pretty-printer for tests,
    etc.) subclass this and implement `emit_root`. The base already provides
    AST dispatch via `Visitor.visit`; the backend fills in `visit_*` for
    every node type it emits.
    """

    @abstractmethod
    def emit_root(self, node: Node) -> None:
        """Emit a full tree rooted at `node` to the backend's output sink."""
        raise NotImplementedError
