"""User-facing API surface — shorthand, resolution context.

Factories live in the top-level public modules (``scadwright.primitives``,
``scadwright.boolops``, ``scadwright.extrusions``, ``scadwright.composition_helpers``).
"""

from scadwright.primitives import cube

__all__ = ["cube"]
