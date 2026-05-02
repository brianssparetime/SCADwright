"""Format unexpected ``build()`` return values into actionable diagnostics.

When a Component's ``build()`` returns something that isn't a Node and
isn't a generator yielding Nodes, the framework can't materialize it.
The two helpers here turn whatever was returned into (a) a one-phrase
description of the shape ("None", "list of 4 Nodes", "list with non-
Node items (types: int, str)") and (b) a focused hint for the most
common new-author mistakes (forgot a `return`, returned a list of
parts instead of yielding).

The actual ``raise`` site is in ``Component._invoke_build``; this
module just supplies the message-formatting bricks so that file can
stay short.
"""

from __future__ import annotations

from scadwright.ast.base import Node


def _describe_build_result(result) -> str:
    """One-phrase description of an unexpected ``build()`` return value."""
    if result is None:
        return "None"
    if isinstance(result, (list, tuple)):
        kind = type(result).__name__
        if not result:
            return f"empty {kind}"
        if all(isinstance(x, Node) for x in result):
            return f"{kind} of {len(result)} Nodes"
        bad = [(i, type(x).__name__) for i, x in enumerate(result)
               if not isinstance(x, Node)]
        bad_summary = ", ".join(t for _, t in bad[:3])
        if len(bad) > 3:
            bad_summary += f", ... ({len(bad)} total)"
        return f"{kind} with non-Node items (types: {bad_summary})"
    return type(result).__name__


def _build_return_hint(result) -> str | None:
    """Return a focused hint for the most common new-author mistakes, or
    ``None`` to fall back to the generic message."""
    if result is None:
        return (
            "did you forget a `return` statement? For multiple parts, "
            "use `yield each_part` (auto-unioned by the framework)."
        )
    if isinstance(result, (list, tuple)):
        if not result:
            return (
                "build() must `yield` at least one part, or `return` a "
                "single Node."
            )
        if all(isinstance(x, Node) for x in result):
            return (
                "change `return [a, b, c]` to either `yield a; yield b; "
                "yield c` (preferred — auto-unioned by the framework) "
                "or `return union(a, b, c)`."
            )
        # mixed list/tuple: indices are useful, the description already
        # names the bad types — no extra hint adds value.
        return None
    return None
