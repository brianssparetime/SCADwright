"""scadwright exception hierarchy.

All library-raised exceptions inherit from SCADwrightError. Subclasses:

- ValidationError: bad factory arguments (wrong shape, negative radius, etc.).
- BuildError: a Component.build() raised an exception.
- EmitError: the emitter encountered something it couldn't render.

Each carries an optional source_location attribute for programmatic access;
the formatted message includes it when present.
"""

from __future__ import annotations

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
    """Raised when a factory is given arguments it can't turn into a valid AST node."""


class BuildError(SCADwrightError):
    """Raised when a Component's build() method itself raises. Wraps the original via __cause__."""


class EmitError(SCADwrightError):
    """Raised when the emitter encounters something it can't render."""
