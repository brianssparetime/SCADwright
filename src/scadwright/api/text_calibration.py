"""Per-glyph advance scale override for ``add_text`` on curved walls.

Curved-wall and rim-arc ``add_text`` placements emit one OpenSCAD ``text()``
per glyph and compute the per-glyph advance widths in Python (via
freetype-py when installed). The default scaling already reproduces
OpenSCAD's flat ``text(size=N)`` advance layout (the font-independent
advance constant lives in ``_textmetrics``), so the default factor here is
``1.0`` — a plain multiplier on top of that.

This module exposes that multiplier as a context-scoped override. Users
who want to tighten or loosen per-glyph tracking deliberately wrap the
affected ``add_text`` call in:

    with sw.text_advance_calibration(0.95):
        plate.add_text(label="…", on="outer_wall", …)

We deliberately keep this off the ``add_text`` kwarg surface — it's a
calibration knob, not a per-label parameter, and exposing it on the
factory would tempt users to fiddle with it on every call.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar


# Default 1.0: the advance scaling that matches OpenSCAD's flat text() layout
# is applied in ``_textmetrics`` (a font-independent constant verified against
# OpenSCAD's STL output); this factor is a plain multiplier on top of it.
_DEFAULT_CALIBRATION: float = 1.0


_current: ContextVar[float] = ContextVar(
    "scadwright_text_advance_calibration", default=_DEFAULT_CALIBRATION,
)


def current_calibration() -> float:
    """Return the calibration factor in effect for the current scope."""
    return _current.get()


@contextmanager
def text_advance_calibration(factor: float):
    """Override the per-glyph advance multiplier.

    Default is 1.0, which already matches OpenSCAD's flat-text advance
    layout (the OpenSCAD-matching constant is applied in ``_textmetrics``).
    Pass a value below 1.0 to tighten or above 1.0 to loosen per-glyph
    spacing on curved walls and rim arcs. Affects ``add_text`` calls inside
    the block; nested blocks inherit the enclosing value.

    Has no effect when freetype-py isn't installed (the heuristic fallback
    uses a flat ``0.6 * font_size * spacing`` per glyph, independent of this
    multiplier).
    """
    if not isinstance(factor, (int, float)) or factor <= 0:
        raise ValueError(
            f"text_advance_calibration: factor must be a positive number, "
            f"got {factor!r}"
        )
    token = _current.set(float(factor))
    try:
        yield
    finally:
        _current.reset(token)
