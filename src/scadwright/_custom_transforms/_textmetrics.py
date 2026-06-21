"""Per-glyph advance widths for curved-wall ``add_text``.

``get_advances(chars, font=, size=, spacing=)`` returns per-character advance
widths in millimetres. On any failure (freetype-py missing, font unresolved,
exotic kwarg) it returns the legacy ``0.6 * size * spacing`` heuristic for
every char and logs one warning per ``(font_string, cause)`` pair so the
user knows their spacing won't be proportional.

Why a separate module: ``add_text`` on cylindrical/conical/meridional/rim-arc
hosts emits one OpenSCAD ``text()`` call per character so each glyph can be
rotated to follow the surface — which forces scadwright to compute glyph
advances itself rather than letting OpenSCAD handle layout. Without real
font metrics, every glyph occupies the same arc-length slot and proportional
fonts look wrong (a narrow ``i`` floats in a slot sized for ``W``). With
freetype-py installed, this module reads advances straight from the font
file at emit time. Without it, falls back to the same uniform heuristic
scadwright used before.

Resolution policy for the ``font`` argument (the same namespace OpenSCAD
renders from — a fontconfig family name, never a file path):

- ``None`` — search known system locations for Liberation Sans Regular
  (OpenSCAD's bundled default font), then ``fc-match "Liberation Sans"``.
- ``"Family"`` / ``"Family:style=Bold"`` — resolved to a file with
  ``fc-match`` (the same fontconfig OpenSCAD uses), so one name drives both
  the render and the metrics. A one-time warning fires if fontconfig reports
  a different family than requested.

Either step needs both ``fc-match`` (system fontconfig) and freetype-py (the
``scadwright[curved-text]`` extra). When either is missing, or the name
can't be resolved, callers fall back to the conservative heuristic with a
one-time warning; OpenSCAD still renders the label via its own fontconfig.
File paths are rejected upstream (in ``text()``), since OpenSCAD's ``text()``
resolves only by name.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from collections import OrderedDict
from typing import Any, NamedTuple

from scadwright._logging import get_logger
from scadwright.api.text_calibration import current_calibration


_log = get_logger("scadwright.add_text.metrics")


# Today's font-agnostic average advance, expressed as a fraction of size.
# Kept in this module so ``add_text``'s curved-wall fallback stays consistent
# with the value users have seen historically.
_HEURISTIC_AVG_ADVANCE: float = 0.6

# OpenSCAD's text(size=N) scales a glyph's outline and its advance by two
# different, font-independent constants (the EM and the font's ascender both
# cancel out — verified against OpenSCAD's STL output across Liberation Sans,
# Arial, Verdana, Times New Roman, and Courier New). For a metric expressed as
# a fraction of EM, the millimetre value is ``K * size * em_fraction``:
#   - outline coordinates (ink extents, side bearings, cap/descender heights)
#     use K_OUTLINE;
#   - advances (pen movement) use the slightly smaller K_ADVANCE.
# Measured from flat-topped glyphs (no curve flattening) so they are exact.
_K_OUTLINE: float = 1.3888
_K_ADVANCE: float = 1.3563


class GlyphMetric(NamedTuple):
    """Unitless (per-EM) outline metrics for one glyph.

    All fields are font units divided by ``units_per_EM``: size- and
    calibration-independent, so they cache cleanly across calls.
    """

    advance_em: float
    ink_left_em: float
    ink_right_em: float
    ink_bottom_em: float   # negative below the baseline
    ink_top_em: float


class GlyphBox(NamedTuple):
    """Per-glyph extents in millimetres, in the glyph's pen-origin/baseline
    frame. ``advance`` includes ``spacing``; ``ink_*`` are the glyph outline
    extents (side bearings included), baseline at 0.
    """

    advance: float
    ink_left: float
    ink_right: float
    ink_bottom: float
    ink_top: float


# --- Module-level state (guarded by _LOCK) ---


_LOCK = threading.Lock()

# LRU keyed on ``(font_key, char)`` storing the unitless ``GlyphMetric``.
# Scaled to mm by ``size``/``spacing``/calibration at lookup time. Bounded so
# a long-running session can't grow without limit.
_CACHE: "OrderedDict[tuple[str, str], GlyphMetric]" = OrderedDict()
_CACHE_MAX = 256

# Cached freetype.Face for each resolved font key. ``None`` marks an
# unresolvable font so we don't retry resolution on every call.
_FACE_CACHE: dict[str, Any] = {}

# (font_key, cause) → already-warned. One warning per pair per process.
_WARNED: set[tuple[str, str]] = set()

# Memoised import probe. ``None`` = not yet attempted; the freetype module on
# success; ``False`` on import failure.
_FREETYPE_AVAILABLE: Any = None

# Memoised ``fc-match`` lookup. ``None`` = not yet probed; the resolved exe
# path on success; ``False`` when fontconfig's CLI isn't installed.
_FC_MATCH_EXE: Any = None


# --- Public API ---


def get_advances(
    chars: tuple[str, ...],
    *,
    font: str | None,
    size: float,
    spacing: float,
) -> list[float]:
    """Return per-character advance widths in millimetres.

    Same length as ``chars``. Never raises. Each advance is ``advance_em *
    size * spacing`` when real metrics are available, else the heuristic
    ``_HEURISTIC_AVG_ADVANCE * size * spacing`` for every char.

    The caller cannot tell from the return value whether the result is real
    or heuristic — that's deliberate. Detection (and the user-facing
    warning) happens here, once per ``(font, cause)`` pair.
    """
    if not chars:
        return []
    heuristic_advance = _HEURISTIC_AVG_ADVANCE * size * spacing

    face = _resolve_face(font)
    if face is None:
        return [heuristic_advance] * len(chars)

    font_key = _font_key_for_warnings(font)
    metrics = _metrics_for(face, font_key, chars)
    if metrics is None:
        return [heuristic_advance] * len(chars)

    # Curved-wall advances honour the live ``text_advance_calibration``
    # override (default 1.0) so callers can tighten/loosen per-glyph tracking.
    scale = _K_ADVANCE * size * current_calibration()
    return [m.advance_em * scale * spacing for m in metrics]


def get_glyph_boxes(
    chars: tuple[str, ...],
    *,
    font: str | None,
    size: float,
    spacing: float,
) -> "list[GlyphBox] | None":
    """Return per-glyph mm-space boxes for ``chars``, or ``None``.

    ``None`` means real metrics are unavailable (freetype-py missing,
    font unresolved, or a glyph read failed) — the caller should fall back
    to its own heuristic. ``[]`` is returned for empty input.

    Each ``GlyphBox`` is in the glyph's pen-origin / baseline frame, so the
    caller pen-walks the advances and unions the ink extents to lay out a
    line. Outline extents (``ink_*``) use the outline scale; ``advance`` uses
    the advance scale, both font-independent. The curved-wall
    ``text_advance_calibration`` override is deliberately ignored here, so a
    flat-text bbox doesn't move because some tracking context is active.
    """
    if not chars:
        return []
    face = _resolve_face(font)
    if face is None:
        return None
    font_key = _font_key_for_warnings(font)
    metrics = _metrics_for(face, font_key, chars)
    if metrics is None:
        return None
    # OpenSCAD scales the glyph outline and the advance by two different
    # constants (see _K_OUTLINE / _K_ADVANCE). ``advance`` additionally scales
    # by spacing; intra-glyph ink does not.
    outline = _K_OUTLINE * size
    advance = _K_ADVANCE * size * spacing
    return [
        GlyphBox(
            advance=m.advance_em * advance,
            ink_left=m.ink_left_em * outline,
            ink_right=m.ink_right_em * outline,
            ink_bottom=m.ink_bottom_em * outline,
            ink_top=m.ink_top_em * outline,
        )
        for m in metrics
    ]


# --- Internals ---


def _fc_match_exe() -> "str | None":
    """Cached path to the ``fc-match`` binary, or None when it isn't installed."""
    global _FC_MATCH_EXE
    if _FC_MATCH_EXE is None:
        _FC_MATCH_EXE = shutil.which("fc-match") or False
    return _FC_MATCH_EXE or None


def _fc_match(name: str) -> "str | None":
    """Resolve a fontconfig name to a font file with ``fc-match``, or None.

    Uses the same fontconfig OpenSCAD renders through, so the file we read
    metrics from is (modulo a differently-configured bundled fontconfig) the
    face OpenSCAD draws. Never raises.
    """
    exe = _fc_match_exe()
    if exe is None:
        return None
    try:
        result = subprocess.run(
            [exe, "--format=%{file}", name],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    path = result.stdout.strip()
    if path and os.path.isfile(path):
        return path
    return None


def _family_of(font: str) -> str:
    """The family part of a fontconfig pattern: drop ``:style=…`` and any
    comma-separated alternates."""
    return font.split(":", 1)[0].split(",", 1)[0].strip()


def _warn_if_substituted(font: str, face: Any) -> None:
    """Warn once if fontconfig resolved ``font`` to a different family."""
    requested = _family_of(font)
    actual = getattr(face, "family_name", None)
    if isinstance(actual, bytes):
        actual = actual.decode("utf-8", "replace")
    if not requested or not actual:
        return
    if requested.casefold() != actual.casefold():
        _warn_once(
            font, "font-substituted",
            f"add_text: font {font!r} resolved via fontconfig to {actual!r}; "
            f"metrics use that face and OpenSCAD may substitute differently. "
            f"Install the requested font or check the name.",
        )


def _metrics_for(face: Any, font_key: str, chars) -> "list[GlyphMetric] | None":
    """Per-glyph ``GlyphMetric`` for ``chars``, cached on ``(font_key, char)``.

    Returns ``None`` (after warning once and marking the face bad) if any
    glyph read raises, so the caller drops to its heuristic for this font.
    """
    out: list[GlyphMetric] = []
    failed_char = None
    failed_exc: Exception | None = None
    with _LOCK:
        for ch in chars:
            cache_key = (font_key, ch)
            cached = _CACHE.get(cache_key)
            if cached is None:
                try:
                    cached = _glyph_metric(face, ch)
                except Exception as exc:  # noqa: BLE001 — any read failure → heuristic
                    failed_char, failed_exc = ch, exc
                    break
                if len(_CACHE) >= _CACHE_MAX:
                    _CACHE.popitem(last=False)
                _CACHE[cache_key] = cached
            else:
                _CACHE.move_to_end(cache_key)
            out.append(cached)
    if failed_char is not None:
        # Warn and mark the face bad outside the lock — ``_warn_once`` also
        # takes ``_LOCK`` and it is not reentrant.
        with _LOCK:
            _FACE_CACHE[font_key] = None
        _warn_once(
            font_key, "char-load-failed",
            f"add_text: failed to read metrics for {failed_char!r} from "
            f"font {font_key!r} ({failed_exc.__class__.__name__}); "
            f"using heuristic for this font.",
        )
        return None
    return out


def _try_import_freetype() -> Any:
    """Lazy import + memoise. Returns the freetype module or None."""
    global _FREETYPE_AVAILABLE
    if _FREETYPE_AVAILABLE is not None:
        return _FREETYPE_AVAILABLE if _FREETYPE_AVAILABLE is not False else None
    try:
        import freetype  # type: ignore[import-not-found]
        _FREETYPE_AVAILABLE = freetype
        return freetype
    except ImportError:
        _FREETYPE_AVAILABLE = False
        return None


def _resolve_face(font: str | None) -> Any:
    """Return a cached freetype.Face for ``font``, or ``None`` on failure.

    Failure is sticky per (font_key) — we cache the negative result so we
    don't reopen and re-warn on every call. The fallback path on the caller
    side is the heuristic.
    """
    font_key = _font_key_for_warnings(font)

    with _LOCK:
        if font_key in _FACE_CACHE:
            return _FACE_CACHE[font_key]

    ft = _try_import_freetype()
    if ft is None:
        _warn_once(
            font_key, "freetype-missing",
            "add_text: install scadwright[curved-text] for proportional "
            "glyph spacing on curved walls; falling back to 0.6*size heuristic.",
        )
        with _LOCK:
            _FACE_CACHE[font_key] = None
        return None

    path = _resolve_font_path(font)
    if path is None:
        with _LOCK:
            _FACE_CACHE[font_key] = None
        return None  # _resolve_font_path emitted the appropriate warning

    try:
        face = ft.Face(path)
    except Exception as exc:
        _warn_once(
            font_key, "face-load-failed",
            f"add_text: cannot load font file {path!r} "
            f"({exc.__class__.__name__}: {exc}); falling back to heuristic.",
        )
        with _LOCK:
            _FACE_CACHE[font_key] = None
        return None

    if font is not None:
        _warn_if_substituted(font, face)

    with _LOCK:
        _FACE_CACHE[font_key] = face
    return face


def _resolve_font_path(font: str | None) -> str | None:
    """Resolve the ``font`` kwarg to a font file via fontconfig, or None.

    ``font`` is a fontconfig family name, or None for OpenSCAD's default
    (Liberation Sans). File paths are rejected upstream in ``text()``. Returns
    None (after a one-time warning) when fontconfig isn't available or the
    name can't be resolved; the caller then uses the heuristic.
    """
    if font is None:
        # The curated search finds OpenSCAD's *own* bundled Liberation Sans
        # file, the most faithful match for the default render; fall back to
        # fontconfig only if that misses.
        path = _find_default_liberation_sans()
        if path is not None:
            return path
        path = _fc_match("Liberation Sans")
        if path is not None:
            return path
        _warn_once(
            "<default>", "no-default-font-found",
            "add_text: could not locate Liberation Sans Regular (OpenSCAD's "
            "default font), and fontconfig didn't resolve it either. Install "
            "fonts-liberation or the OpenSCAD app bundle for real metrics; "
            "falling back to the 0.6*size heuristic.",
        )
        return None

    if _fc_match_exe() is None:
        _warn_once(
            font, "fontconfig-unavailable",
            f"add_text: fontconfig's `fc-match` isn't on PATH, so scadwright "
            f"can't resolve {font!r} to a font file for metrics; falling back "
            f"to the 0.6*size heuristic. OpenSCAD still renders the label via "
            f"its own fontconfig. Install fontconfig for real metrics.",
        )
        return None

    path = _fc_match(font)
    if path is None:
        _warn_once(
            font, "fc-match-failed",
            f"add_text: fontconfig could not resolve {font!r} to a usable "
            f"font file; falling back to the 0.6*size heuristic.",
        )
        return None
    return path


# Where Liberation Sans Regular tends to live, in priority order. OpenSCAD
# bundles it on macOS/Windows; Linux distros usually package it. Patterns
# with wildcards expand via ``glob`` so version-numbered Homebrew Cellar
# paths and similar are reachable without re-pinning. Order matters — we
# return the first hit, so app-bundle paths come before bare system paths
# (we want the same font OpenSCAD would render with).
_LIBERATION_SANS_CANDIDATES: tuple[str, ...] = (
    # macOS — OpenSCAD app bundle (DMG/installer)
    "/Applications/OpenSCAD.app/Contents/Resources/fonts/Liberation-*/ttf/LiberationSans-Regular.ttf",
    # macOS — Homebrew Cellar (Apple Silicon and Intel)
    "/opt/homebrew/Cellar/openscad/*/OpenSCAD.app/Contents/Resources/fonts/Liberation-*/ttf/LiberationSans-Regular.ttf",
    "/usr/local/Cellar/openscad/*/OpenSCAD.app/Contents/Resources/fonts/Liberation-*/ttf/LiberationSans-Regular.ttf",
    # Linux — Flatpak OpenSCAD
    "/var/lib/flatpak/app/org.openscad.OpenSCAD/current/active/files/share/openscad/fonts/Liberation-*/ttf/LiberationSans-Regular.ttf",
    # Linux — Snap OpenSCAD
    "/snap/openscad/current/usr/share/openscad/fonts/Liberation-*/ttf/LiberationSans-Regular.ttf",
    # Linux — common distro paths
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/LiberationSans-Regular.ttf",
    "/usr/local/share/fonts/LiberationSans-Regular.ttf",
    # Homebrew (macOS) — font-liberation cask
    "/opt/homebrew/share/fonts/LiberationSans-Regular.ttf",
    "/usr/local/share/fonts/LiberationSans-Regular.ttf",
    # Windows — OpenSCAD installer
    r"C:\Program Files\OpenSCAD\fonts\Liberation-*\ttf\LiberationSans-Regular.ttf",
    r"C:\Program Files (x86)\OpenSCAD\fonts\Liberation-*\ttf\LiberationSans-Regular.ttf",
    r"C:\Program Files\OpenSCAD\fonts\LiberationSans-Regular.ttf",
    r"C:\Program Files (x86)\OpenSCAD\fonts\LiberationSans-Regular.ttf",
)


def _find_default_liberation_sans() -> str | None:
    """Walk known install locations for Liberation Sans Regular.

    Each candidate is a path or a ``glob`` pattern (used for the
    version-numbered Homebrew Cellar / Liberation-2.x.y bundle layouts).
    Returns the first existing file, or None.
    """
    import glob
    for pattern in _LIBERATION_SANS_CANDIDATES:
        if any(c in pattern for c in "*?["):
            for hit in sorted(glob.glob(pattern), reverse=True):
                if os.path.isfile(hit):
                    return hit
        else:
            if os.path.isfile(pattern):
                return pattern
    return None


def _font_key_for_warnings(font: str | None) -> str:
    """Stable string used as a cache + dedup-warning key."""
    return "<default>" if font is None else font


def _glyph_metric(face: Any, char: str) -> GlyphMetric:
    """Read unitless (per-EM) outline metrics for ``char`` from ``face``.

    Uses ``FT_LOAD_NO_SCALE | FT_LOAD_NO_HINTING`` so metrics come back in
    raw font units; division by ``units_per_EM`` yields the unitless values.
    The outline bbox (bearing/width/height) is the glyph's actual ink extent,
    including round-glyph overshoot — not the nominal cap/x-height lines — so
    the vertical extent reflects which letters are present (no descenders in
    all-caps, no ascenders in lowercase). Callers multiply by ``size ×
    calibration × ascender / EM`` to reach mm matching OpenSCAD's flat text().

    For chars the font lacks (``glyph_index == 0``), freetype loads the
    ``.notdef`` glyph — same behaviour OpenSCAD's ``text()`` would produce
    when rasterising the missing glyph.
    """
    ft = _try_import_freetype()
    flags = ft.FT_LOAD_NO_SCALE | ft.FT_LOAD_NO_HINTING
    face.load_char(char, flags)
    m = face.glyph.metrics
    em = face.units_per_EM
    return GlyphMetric(
        advance_em=m.horiAdvance / em,
        ink_left_em=m.horiBearingX / em,
        ink_right_em=(m.horiBearingX + m.width) / em,
        ink_top_em=m.horiBearingY / em,
        ink_bottom_em=(m.horiBearingY - m.height) / em,
    )


def _warn_once(font_key: str, cause: str, message: str) -> None:
    """Emit a warning at most once per ``(font_key, cause)`` pair."""
    pair = (font_key, cause)
    with _LOCK:
        if pair in _WARNED:
            return
        _WARNED.add(pair)
    _log.warning(message)


# --- Test helpers (private; not part of the public surface) ---


def _reset_state_for_tests() -> None:
    """Clear all module-level caches and warnings. Tests only."""
    global _FREETYPE_AVAILABLE, _FC_MATCH_EXE
    with _LOCK:
        _CACHE.clear()
        _FACE_CACHE.clear()
        _WARNED.clear()
    _FREETYPE_AVAILABLE = None
    _FC_MATCH_EXE = None
