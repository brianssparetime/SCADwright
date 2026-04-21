"""Directional-helper mixin for Node: up/down/left/right/forward/back/flip.

Each helper wraps `self` in a single-axis ``Translate`` (or ``Mirror`` for
``flip``) and captures the source location at the helper's call site, so
``cube(10).up(5)`` reports the ``.up(5)`` line in error messages rather
than the mixin body. That's why they don't just delegate to
``self.translate(...)``.
"""

from __future__ import annotations


class _DirectionalMixin:
    """Single-axis translation shorthands + flip mirror."""

    def _translate_with_loc(self, v: tuple[float, float, float], loc) -> "Node":
        from scadwright.ast.base import Node  # noqa: F401 — return-type only
        from scadwright.ast.transforms import Translate

        return Translate(v=v, child=self, source_location=loc)

    def up(self, d: float) -> "Node":
        from scadwright.ast.base import SourceLocation
        return self._translate_with_loc((0.0, 0.0, float(d)), SourceLocation.from_caller())

    def down(self, d: float) -> "Node":
        from scadwright.ast.base import SourceLocation
        return self._translate_with_loc((0.0, 0.0, -float(d)), SourceLocation.from_caller())

    def left(self, d: float) -> "Node":
        from scadwright.ast.base import SourceLocation
        return self._translate_with_loc((-float(d), 0.0, 0.0), SourceLocation.from_caller())

    def right(self, d: float) -> "Node":
        from scadwright.ast.base import SourceLocation
        return self._translate_with_loc((float(d), 0.0, 0.0), SourceLocation.from_caller())

    def forward(self, d: float) -> "Node":
        from scadwright.ast.base import SourceLocation
        return self._translate_with_loc((0.0, float(d), 0.0), SourceLocation.from_caller())

    def back(self, d: float) -> "Node":
        from scadwright.ast.base import SourceLocation
        return self._translate_with_loc((0.0, -float(d), 0.0), SourceLocation.from_caller())

    def flip(self, axis: str = "z") -> "Node":
        """Mirror across the given axis plane ("x", "y", or "z")."""
        from scadwright.ast.base import SourceLocation
        from scadwright.ast.transforms import Mirror

        a = axis.lower()
        normal = (1.0 if a == "x" else 0.0, 1.0 if a == "y" else 0.0, 1.0 if a == "z" else 0.0)
        return Mirror(
            normal=normal, child=self, source_location=SourceLocation.from_caller()
        )
