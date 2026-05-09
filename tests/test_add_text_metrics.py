"""Tests for the per-glyph advance-width helper used by curved-wall add_text.

Two layers are exercised:

- The heuristic-fallback path. Active by default for every test in the
  suite (the ``_disable_freetype`` autouse fixture in ``conftest.py``
  forces ``_try_import_freetype`` to return None). Tests in this layer
  assert the stable ``0.6 * size * spacing`` per-char output, the warning
  contract, and cache behaviour.
- The real freetype-py path. Opt-in via ``@pytest.mark.freetype``; tests
  pass an absolute path to the bundled Liberation Sans Regular so the
  numbers don't depend on the host's font search path. Skipped if
  freetype-py isn't installed.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import pytest

from scadwright._custom_transforms import _textmetrics
from scadwright._custom_transforms._textmetrics import (
    _HEURISTIC_AVG_ADVANCE,
    get_advances,
)


@pytest.fixture(autouse=True)
def _reset_metrics_state():
    """Clear caches and warning state before and after each test in this file."""
    _textmetrics._reset_state_for_tests()
    yield
    _textmetrics._reset_state_for_tests()


# --- Heuristic-fallback layer ---


class TestHeuristicFallback:
    """Behaviour with freetype-py disabled (the default for the suite)."""

    def test_empty_input_returns_empty_list(self):
        assert get_advances((), font=None, size=4.0, spacing=1.0) == []

    def test_uniform_advance_per_char(self):
        adv = get_advances(("i", "W", "M"), font=None, size=4.0, spacing=1.0)
        assert len(adv) == 3
        assert all(a == _HEURISTIC_AVG_ADVANCE * 4.0 for a in adv)

    def test_size_scales_advance(self):
        adv4 = get_advances(("X",), font=None, size=4.0, spacing=1.0)
        adv8 = get_advances(("X",), font=None, size=8.0, spacing=1.0)
        assert adv8[0] == pytest.approx(2 * adv4[0])

    def test_spacing_scales_advance(self):
        base = get_advances(("X",), font=None, size=4.0, spacing=1.0)
        doubled = get_advances(("X",), font=None, size=4.0, spacing=2.0)
        assert doubled[0] == pytest.approx(2 * base[0])

    def test_freetype_missing_warns_once(self, caplog):
        with caplog.at_level(logging.WARNING, logger="scadwright.add_text.metrics"):
            get_advances(("A",), font=None, size=4.0, spacing=1.0)
            get_advances(("B",), font=None, size=4.0, spacing=1.0)
            get_advances(("C", "D"), font=None, size=4.0, spacing=1.0)
        msgs = [r.getMessage() for r in caplog.records]
        missing = [m for m in msgs if "freetype-py is not installed" in m]
        assert len(missing) == 1, f"expected one missing-freetype warning, got {msgs}"


# --- Real-metrics layer ---

# All tests below need freetype-py and the bundled test font. The ``freetype``
# marker opts out of the suite-wide _disable_freetype autouse fixture.
freetype_module = pytest.importorskip("freetype")
pytestmark_freetype = pytest.mark.freetype


@pytest.mark.freetype
class TestRealMetrics:
    """Behaviour with freetype-py enabled and the bundled font."""

    def test_proportional_advances_for_narrow_vs_wide(self, bundled_font_path):
        adv = get_advances(
            ("i", "W"), font=bundled_font_path, size=4.0, spacing=1.0,
        )
        # Liberation Sans: ``i`` is much narrower than ``W``. The exact
        # values come from the font; assert the relationship, not numbers.
        assert adv[0] < adv[1] * 0.5, f"expected i << W, got {adv}"

    def test_advances_match_known_values(self, bundled_font_path):
        # Sanity-check a few specific values against Liberation Sans 2.00.1.
        # These ride on a stable bundled font; if the font ever changes,
        # the numbers update with it.
        adv = get_advances(
            ("i",), font=bundled_font_path, size=4.0, spacing=1.0,
        )
        # 'i' in Liberation Sans 2.00.1 is 455 / 2048 EM × 4 mm ≈ 0.889 mm.
        assert adv[0] == pytest.approx(0.889, abs=0.01)

    def test_size_scales_real_advance(self, bundled_font_path):
        a4 = get_advances(("M",), font=bundled_font_path, size=4.0, spacing=1.0)
        a8 = get_advances(("M",), font=bundled_font_path, size=8.0, spacing=1.0)
        assert a8[0] == pytest.approx(2 * a4[0])

    def test_spacing_scales_real_advance(self, bundled_font_path):
        a1 = get_advances(("M",), font=bundled_font_path, size=4.0, spacing=1.0)
        a2 = get_advances(("M",), font=bundled_font_path, size=4.0, spacing=2.0)
        assert a2[0] == pytest.approx(2 * a1[0])

    def test_face_loaded_once_per_font(self, bundled_font_path, monkeypatch):
        """Repeated calls reuse the cached freetype.Face instead of reopening."""
        load_count = {"n": 0}
        original_face = freetype_module.Face

        def counting_face(path, *a: Any, **kw: Any):
            load_count["n"] += 1
            return original_face(path, *a, **kw)

        monkeypatch.setattr(freetype_module, "Face", counting_face)
        get_advances(("a",), font=bundled_font_path, size=4.0, spacing=1.0)
        get_advances(("b",), font=bundled_font_path, size=4.0, spacing=1.0)
        get_advances(("c", "d"), font=bundled_font_path, size=4.0, spacing=1.0)
        assert load_count["n"] == 1, "Face should load exactly once per font"

    def test_advance_em_cached_across_size_changes(self, bundled_font_path, monkeypatch):
        """Cache key is ``(font, char)`` not ``(font, char, size, spacing)`` —
        switching size/spacing reuses the cached EM-units value."""
        char_loads = {"n": 0}
        original_advance_em = _textmetrics._advance_em

        def counting_advance_em(face: Any, char: str) -> float:
            char_loads["n"] += 1
            return original_advance_em(face, char)

        monkeypatch.setattr(_textmetrics, "_advance_em", counting_advance_em)
        get_advances(("X",), font=bundled_font_path, size=4.0, spacing=1.0)
        get_advances(("X",), font=bundled_font_path, size=8.0, spacing=1.0)
        get_advances(("X",), font=bundled_font_path, size=4.0, spacing=2.0)
        assert char_loads["n"] == 1, "cached EM advance should be reused across sizes"

    def test_lru_evicts_oldest_at_capacity(self, bundled_font_path, monkeypatch):
        """When the cache is full, the oldest entry is evicted."""
        monkeypatch.setattr(_textmetrics, "_CACHE_MAX", 4)
        # Insert 4 entries.
        get_advances(
            ("a", "b", "c", "d"), font=bundled_font_path, size=4.0, spacing=1.0,
        )
        # Touch 'a' so 'b' becomes the LRU candidate.
        get_advances(("a",), font=bundled_font_path, size=4.0, spacing=1.0)
        # Insert a fifth — 'b' should be evicted.
        get_advances(("e",), font=bundled_font_path, size=4.0, spacing=1.0)
        keys = {k[1] for k in _textmetrics._CACHE.keys()}
        assert "b" not in keys
        assert keys == {"a", "c", "d", "e"}

    def test_threadsafe(self, bundled_font_path):
        """Concurrent calls don't raise and produce consistent results."""
        chars = tuple("SCADwright")
        results = []
        errors = []

        def run():
            try:
                results.append(get_advances(
                    chars, font=bundled_font_path, size=4.0, spacing=1.0,
                ))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=run) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors
        assert len(results) == 8
        assert all(r == results[0] for r in results)

    def test_unknown_abs_path_falls_back_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="scadwright.add_text.metrics"):
            adv = get_advances(
                ("A",), font="/nonexistent/path/to/font.ttf",
                size=4.0, spacing=1.0,
            )
        assert adv[0] == _HEURISTIC_AVG_ADVANCE * 4.0
        msgs = [r.getMessage() for r in caplog.records]
        assert any("does not exist" in m for m in msgs), msgs

    def test_font_name_falls_back_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="scadwright.add_text.metrics"):
            adv = get_advances(
                ("A",), font="Bogus Family", size=4.0, spacing=1.0,
            )
        assert adv[0] == _HEURISTIC_AVG_ADVANCE * 4.0
        msgs = [r.getMessage() for r in caplog.records]
        assert any("name-based system font lookup" in m for m in msgs), msgs

    def test_font_name_warns_once_per_font(self, caplog):
        with caplog.at_level(logging.WARNING, logger="scadwright.add_text.metrics"):
            get_advances(("A",), font="Bogus Family", size=4.0, spacing=1.0)
            get_advances(("B",), font="Bogus Family", size=4.0, spacing=1.0)
            get_advances(("C",), font="Other Family", size=4.0, spacing=1.0)
            get_advances(("D",), font="Other Family", size=4.0, spacing=1.0)
        msgs = [r.getMessage() for r in caplog.records]
        name_warnings = [m for m in msgs if "name-based system font lookup" in m]
        assert len(name_warnings) == 2, f"expected one warning per font, got {msgs}"


# --- Dispatch-level valign behaviour ---


from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder
from scadwright.shapes import Tube


def _emit(node):
    """Render to an emitter-debug string for substring assertions."""
    from scadwright.emit.scad import emit_str
    return emit_str(node)


class TestValignDispatch:
    """``valign`` resolution and rejection at the dispatch level."""

    def test_curved_default_is_baseline(self):
        # Default valign on a cylindrical wall should resolve to "baseline".
        # The OpenSCAD ``text()`` default is also baseline, so no halign/valign
        # arg appears at all in the emitted text() call.
        scad = _emit(
            cylinder(h=20, r=10).add_text(
                label="X", relief=0.4, on="outer_wall", font_size=4,
            )
        )
        # No explicit valign in the per-glyph text() call (baseline is the
        # OpenSCAD default and the emitter omits it).
        assert 'valign="center"' not in scad
        assert 'valign="baseline"' not in scad
        # And halign="left" is also the default, so it's omitted too.
        assert 'halign="center"' not in scad
        assert 'text("X", size=4)' in scad

    def test_curved_explicit_valign_center_rejected(self):
        # add_text is a custom transform — validation happens at emit time
        # when the body actually expands, not at call time.
        node = cylinder(h=20, r=10).add_text(
            label="X", relief=0.4, on="outer_wall", font_size=4,
            valign="center",
        )
        with pytest.raises(ValidationError, match="valign='center' is not supported"):
            _emit(node)

    def test_conical_explicit_valign_center_rejected(self):
        node = cylinder(h=20, r1=10, r2=4).add_text(
            label="X", relief=0.4, on="outer_wall", font_size=4,
            valign="center",
        )
        with pytest.raises(ValidationError, match="valign='center' is not supported"):
            _emit(node)

    def test_inner_wall_explicit_valign_center_rejected(self):
        node = Tube(h=30, od=24, thk=2).add_text(
            label="X", relief=0.4, on="inner_wall", font_size=4,
            valign="center",
        )
        with pytest.raises(ValidationError, match="valign='center' is not supported"):
            _emit(node)

    def test_rim_arc_explicit_valign_center_rejected(self):
        # A cylinder top with default text_curvature is a rim arc.
        node = cylinder(h=10, r=15).add_text(
            label="X", relief=0.4, on="top", font_size=4,
            valign="center",
        )
        with pytest.raises(ValidationError, match="valign='center' is not supported"):
            _emit(node)

    def test_planar_default_valign_unchanged_center(self):
        # A flat planar face still defaults to valign="center" because the
        # whole label emits as one text() call, where "center" works.
        scad = _emit(
            cube([20, 20, 4], center="xy").add_text(
                label="X", relief=0.4, on="top", font_size=4,
            )
        )
        # Single-line planar emit forwards the resolved valign into text();
        # OpenSCAD's text() default is "baseline", so "center" appears.
        assert 'valign="center"' in scad

    def test_planar_explicit_valign_center_accepted(self):
        # Planar still allows explicit "center" — validation only fires on curved/rim.
        scad = _emit(
            cube([20, 20, 4], center="xy").add_text(
                label="X", relief=0.4, on="top", font_size=4,
                valign="center",
            )
        )
        assert 'valign="center"' in scad

    def test_rim_arc_flat_curvature_default_center(self):
        # text_curvature="flat" on a rim takes the planar (whole-line) path,
        # so valign default reverts to "center".
        scad = _emit(
            cylinder(h=10, r=15).add_text(
                label="X", relief=0.4, on="top", font_size=4,
                text_curvature="flat",
            )
        )
        assert 'valign="center"' in scad

    def test_rim_arc_flat_curvature_explicit_center_accepted(self):
        # And explicit valign="center" on flat-curvature rim is accepted.
        scad = _emit(
            cylinder(h=10, r=15).add_text(
                label="X", relief=0.4, on="top", font_size=4,
                text_curvature="flat", valign="center",
            )
        )
        assert 'valign="center"' in scad


class TestPerGlyphEmission:
    """Per-glyph emit shape: halign="left", valign="baseline", advance-centered."""

    def test_per_glyph_text_omits_center_args(self):
        # halign="left" and valign="baseline" are OpenSCAD's text() defaults,
        # so the emitter omits both. The 2D translate that pre-centers each
        # glyph is the visible artefact.
        scad = _emit(
            cylinder(h=20, r=10).add_text(
                label="AB", relief=0.4, on="outer_wall", font_size=4,
            )
        )
        assert 'halign="center"' not in scad
        assert 'valign="center"' not in scad
        # Advance midpoint pre-centering: heuristic mode → advance=0.6*4=2.4,
        # half=1.2, applied as a 2D translate before linear_extrude.
        assert "translate([-1.2, 0, 0])" in scad

    def test_per_glyph_emit_on_rim_arc(self):
        scad = _emit(
            cylinder(h=10, r=15).add_text(
                label="AB", relief=0.4, on="top", font_size=4,
            )
        )
        assert 'halign="center"' not in scad
        assert 'valign="center"' not in scad
        assert "translate([-1.2, 0, 0])" in scad


def test_heuristic_uniform_pre_translate():
    """In heuristic mode (no freetype marker → autouse fixture disables it)
    every glyph gets the same -advance/2 pre-translate."""
    scad = _emit(
        cylinder(h=20, r=10).add_text(
            label="iW", relief=0.4, on="outer_wall", font_size=4,
        )
    )
    import re
    translates = re.findall(r"translate\(\[(-?\d+\.\d+), 0, 0\]\)", scad)
    vals = {float(t) for t in translates if float(t) < 0}
    # Heuristic: every glyph gets the same pre-translate of -0.6 * size / 2
    # = -1.2 at size=4.
    assert vals == {-1.2}, (
        f"expected uniform -1.2 pre-translate, got {translates}"
    )


@pytest.mark.freetype
class TestProportionalSpacingIntegration:
    """End-to-end: real font metrics drive non-uniform glyph spacing on curved hosts."""

    def test_narrow_glyph_packs_tighter_than_wide(self, bundled_font_path):
        # Place "iW" on a cylinder; with proportional metrics the i pre-translate
        # is much smaller than the W pre-translate (i is much narrower than W).
        scad = _emit(
            cylinder(h=20, r=10).add_text(
                label="iW", relief=0.4, on="outer_wall", font_size=4,
                font=bundled_font_path,
            )
        )
        # Liberation Sans 2.00.1 advances at size=4: i ~ 0.889mm, W ~ 3.775mm.
        # Pre-translate per glyph is -advance/2 in the 2D frame. Don't assert
        # exact byte values (that would tie the test to a specific float-format
        # of the rendering), but both must be present and distinct.
        import re
        translates = re.findall(r"translate\(\[(-?\d+\.\d+), 0, 0\]\)", scad)
        vals = sorted({float(t) for t in translates if float(t) < 0})
        assert len(vals) >= 2, (
            f"expected distinct per-glyph 2D pre-translates, got {translates}"
        )
