"""AST node for user-registered custom transforms.

A `Custom` node carries the transform's registered name, its kwargs, and the
child it wraps. The emitter dispatches via the transform registry.

`ChildrenMarker` is a singleton placeholder: when the emitter renders a hoisted
module body, it calls the transform's expand() with the marker as the child,
so the rendered body uses SCAD's `children()` mechanism and the module can be
re-used across many real children.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scadwright.ast.base import Node


@dataclass(frozen=True)
class Custom(Node):
    """A user-registered transform applied to a child node."""

    name: str
    # Frozen tuple of (kwarg_name, value) sorted by name — keeps the node hashable
    # and gives a stable identity for SCAD module hoisting.
    kwargs: tuple[tuple[str, Any], ...]
    child: Node

    def __post_init__(self):
        names = [name for name, _ in self.kwargs]
        if names != sorted(names):
            raise ValueError(
                f"Custom.kwargs must be sorted by name for stable "
                f"module-hoisting hashes. Got: {names!r}. "
                f"Use tuple(sorted(kwargs.items())) when constructing Custom directly."
            )

    def kwargs_dict(self) -> dict[str, Any]:
        return dict(self.kwargs)


@dataclass(frozen=True)
class ChildrenMarker(Node):
    """Singleton placeholder used while rendering a hoisted module body.

    The emitter renders this as SCAD's `children();`. Custom transform expand()
    functions must treat their `child` argument opaquely (just compose around
    it) — they cannot inspect child attributes, because the marker has none.
    Use `inline=True` on `@sc.transform` if you need to inspect the child.
    """

    def __getattr__(self, name: str):
        # Dunder lookups get Python's default behavior so repr/class/etc. work.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        # Let transform dispatch work — a transform's expand() may compose
        # other registered transforms on the placeholder.
        from scadwright._custom_transforms.base import _registry

        if name in _registry:
            return super().__getattr__(name)
        raise AttributeError(
            f"cannot access .{name} on the CHILDREN placeholder. Non-inline "
            f"transforms cannot inspect their child (the child is a "
            f"placeholder at expand time). If your transform needs to read "
            f"child attributes, register it with @transform(name, inline=True)."
        )


# Module-level singleton — equality/hash via dataclass(frozen=True).
CHILDREN = ChildrenMarker()
