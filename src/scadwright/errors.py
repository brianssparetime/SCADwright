"""scadwright exception hierarchy.

All library-raised exceptions inherit from SCADwrightError. Subclasses:

- ValidationError: bad factory arguments (wrong shape, negative radius, etc.).
- BuildError: a Component.build() raised an exception.
- EmitError: the emitter encountered something it couldn't render.

Each carries an optional source_location attribute for programmatic access;
the formatted message includes it when present.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scadwright.ast.base import SourceLocation


class SCADwrightError(Exception):
    """Base class for all scadwright-raised errors."""

    def __init__(self, message: str, *, source_location: "SourceLocation | None" = None):
        self.source_location = source_location
        if source_location is not None:
            message = f"{message} (at {source_location})"
        super().__init__(message)


class ValidationError(SCADwrightError):
    """Raised when a factory is given arguments it can't turn into a valid AST node.

    When the error originates from an ``equations`` block at class-
    definition time, the optional ``equations_source_index`` attribute
    holds the 0-based index of the offending logical line within the
    class's equations list. ``equations_node`` is set to the specific
    ``ast.AST`` sub-node that triggered the error when one is in scope
    at the raise site. ``equations_colmap`` is the cleaned-col →
    input-col mapping for that line (the third return value of
    :func:`scadwright.component.equations.lex._extract_name_annotations_with_colmap`),
    populated by :func:`scadwright.component.resolver.parse_equations_unified`
    so the LSP diagnostic builder can reach it without recomputing.
    All three default to ``None`` for non-equations errors and for
    equations errors where no narrower position info is available.
    Programmatic consumers can read these directly rather than parsing
    the formatted message.
    """

    def __init__(
        self,
        message: str,
        *,
        source_location: "SourceLocation | None" = None,
        equations_source_index: int | None = None,
        equations_node: ast.AST | None = None,
        equations_colmap: tuple[int, ...] | None = None,
    ):
        super().__init__(message, source_location=source_location)
        self.equations_source_index = equations_source_index
        self.equations_node = equations_node
        self.equations_colmap = equations_colmap


class BuildError(SCADwrightError):
    """Raised when a Component's build() method itself raises. Wraps the original via __cause__."""


class EmitError(SCADwrightError):
    """Raised when the emitter encounters something it can't render."""
