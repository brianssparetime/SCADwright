"""Per-glyph advance scale override for ``add_text`` on curved walls.

Curved-wall and rim-arc ``add_text`` placements emit one OpenSCAD ``text()``
per glyph and compute the per-glyph advance widths in Python (via
freetype-py when installed). The default scaling reproduces what
OpenSCAD's flat ``text(size=N)`` rendering does — empirically,
``advance_mm = advance_units × size × 1.5 × ascender / units_per_EM²``
for typical Latin fonts. The leading ``1.5`` is the calibration
constant; it isn't documented in OpenSCAD's source but is consistent
across font sizes and at least the fonts we've tested.

This module exposes the ``1.5`` as a context-scoped override. Users
who hit a font where the default doesn't match OpenSCAD's rendering,
or who want to tighten / loosen tracking deliberately, wrap the affected
``add_text`` call in:

    with sw.text_advance_calibration(1.6):
        plate.add_text(label="…", on="outer_wall", …)

We deliberately keep this off the ``add_text`` kwarg surface — it's a
calibration knob, not a per-label parameter, and exposing it on the
factory would tempt users to fiddle with it on every call.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar


# Default value chosen to make per-glyph advances on curved walls match
# OpenSCAD's flat ``text(size=N)`` layout for Liberation Sans and other
# Latin fonts (verified empirically against OpenSCAD's STL output: at
# size=4, advance(i) = 1.205 mm vs. font-em-based 0.889 mm × 1.357).
_DEFAULT_CALIBRATION: float = 1.5


_current: ContextVar[float] = ContextVar(
    "scadwright_text_advance_calibration", default=_DEFAULT_CALIBRATION,
)


def current_calibration() -> float:
    """Return the calibration factor in effect for the current scope."""
    return _current.get()


@contextmanager
def text_advance_calibration(factor: float):
    """Override the OpenSCAD-matching per-glyph advance calibration.

    Default is 1.5 (matches OpenSCAD's flat-text layout for Liberation
    Sans). Pass a different value to tighten (``<1.5``) or loosen
    (``>1.5``) per-glyph spacing on curved walls and rim arcs. Affects
    ``add_text`` calls inside the block; nested blocks inherit the
    enclosing value when nested.

    The factor combines with the font's ``ascender / units_per_EM`` ratio
    to produce the actual mm-per-unit-size scaling — so the *visual*
    effect of a given factor is roughly font-independent. Setting
    ``factor=1.0`` reverts to a bare em-relative scale, which is what
    most other fonts' textmetrics-style helpers return; that produces
    visibly tighter layout than OpenSCAD's flat rendering.

    Has no effect when freetype-py isn't installed (the heuristic
    fallback uses a flat ``0.6 * font_size * spacing`` per glyph and
    isn't tied to a per-font factor).
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
