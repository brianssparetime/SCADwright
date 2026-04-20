"""Debugging and diagnostic helpers that emit SCAD-side constructs.

Most users never need this. It exists for:
- `force_render(node)` — force full CGAL rendering of a subtree in preview
  mode, to squash preview artifacts for very complex geometry.
- `echo(...)` — emit a SCAD `echo(...)` statement for diagnostic output
  visible at SCAD render time. For Python-side debugging, use `print()` or
  logging — this is for diagnostics that must live in the emitted SCAD.
"""

from scadwright.ast.base import Node, SourceLocation
from scadwright.ast.transforms import Echo


def force_render(node: Node, *, convexity: int | None = None) -> Node:
    return node.force_render(convexity=convexity)


def echo(*args, _node: Node | None = None, **kwargs) -> Node:
    """Build a SCAD echo(...) statement.

    Positional args become `echo(a, b, c)`; keyword args become
    `echo(name=value)`. Pass `_node=...` to wrap a subtree; otherwise emits
    as a bare statement with no child.
    """
    values = tuple((None, v) for v in args) + tuple(sorted(kwargs.items()))
    return Echo(
        values=values,
        child=_node,
        source_location=SourceLocation.from_caller(),
    )


__all__ = ["force_render", "echo"]
