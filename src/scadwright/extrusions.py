"""Standalone functional extrusions.

Both forms produce the same AST — use whichever reads better at the call site:

    from scadwright.extrusions import linear_extrude
    part = linear_extrude(circle(r=5), height=10)

    # equivalently, via the chained method on Node:
    part = circle(r=5).linear_extrude(height=10)
"""

from scadwright.api.factories import (
    linear_extrude as _linear_extrude,
    rotate_extrude as _rotate_extrude,
)
from scadwright.ast.base import Node


def linear_extrude(node: Node, **kwargs) -> Node:
    return _linear_extrude(node, **kwargs)


def rotate_extrude(node: Node, **kwargs) -> Node:
    return _rotate_extrude(node, **kwargs)


__all__ = ["linear_extrude", "rotate_extrude"]
