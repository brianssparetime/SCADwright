"""Display-related mixin for Node: preview modifiers and SVG color shorthands.

Preview modifiers (``#``/``%``/``*``/``!``) and SVG color shorthands
(``.red()``, ``.steelblue(alpha=0.5)``, …) all wrap a node in a single
transform. The shorthand methods are dynamically attached to the mixin
at import time — cheaper than writing out ~140 explicit method bodies.

The attachment targets the mixin class, not the Node class, which keeps
the color-methods module independent of Node itself (no circular
import).
"""

from __future__ import annotations


class _DisplayMixin:
    """Preview modifiers and the color-shorthand infrastructure."""

    # --- preview modifiers ---

    def _preview(self, mode: str, loc) -> "Node":
        from scadwright.ast.transforms import PreviewModifier
        return PreviewModifier(mode=mode, child=self, source_location=loc)

    def highlight(self) -> "Node":
        from scadwright.ast.base import SourceLocation
        return self._preview("highlight", SourceLocation.from_caller())

    def background(self) -> "Node":
        from scadwright.ast.base import SourceLocation
        return self._preview("background", SourceLocation.from_caller())

    def disable(self) -> "Node":
        from scadwright.ast.base import SourceLocation
        return self._preview("disable", SourceLocation.from_caller())

    def only(self) -> "Node":
        from scadwright.ast.base import SourceLocation
        return self._preview("only", SourceLocation.from_caller())

    # --- color helper (used by SVG shorthand methods attached below) ---

    def _color_with_loc(self, name: str, alpha: float, loc) -> "Node":
        from scadwright.ast.transforms import Color
        return Color(c=name, child=self, alpha=alpha, source_location=loc)


def _make_color_shorthand(color_name: str):
    def _color_method(self, alpha: float = 1.0) -> "Node":
        from scadwright.ast.base import SourceLocation
        return self._color_with_loc(
            color_name, float(alpha), SourceLocation.from_caller()
        )

    _color_method.__name__ = color_name
    _color_method.__qualname__ = f"Node.{color_name}"
    _color_method.__doc__ = f"Apply the SVG/X11 color '{color_name}'."
    return _color_method


def _attach_svg_color_methods_to(cls) -> None:
    from scadwright.colors import SVG_COLORS
    for _name in SVG_COLORS:
        setattr(cls, _name, _make_color_shorthand(_name))


_attach_svg_color_methods_to(_DisplayMixin)
