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
        missing = [m for m in msgs if "scadwright[curved-text]" in m]
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
        # Sanity-check a specific value against Liberation Sans 2.00.1.
        # The default calibration (1.5 × ascender / EM) makes our advances
        # match OpenSCAD's flat text() rendering: at size=4, OpenSCAD
        # measured i.advance = 1.205 mm (verified against STL bbox of
        # ``text("ii") - text("i")``). If the font ever changes, the
        # numbers update with it.
        adv = get_advances(
            ("i",), font=bundled_font_path, size=4.0, spacing=1.0,
        )
        assert adv[0] == pytest.approx(1.205, abs=0.01)

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
        assert any("resolve fonts by absolute path" in m for m in msgs), msgs

    def test_font_name_warns_once_per_font(self, caplog):
        with caplog.at_level(logging.WARNING, logger="scadwright.add_text.metrics"):
            get_advances(("A",), font="Bogus Family", size=4.0, spacing=1.0)
            get_advances(("B",), font="Bogus Family", size=4.0, spacing=1.0)
            get_advances(("C",), font="Other Family", size=4.0, spacing=1.0)
            get_advances(("D",), font="Other Family", size=4.0, spacing=1.0)
        msgs = [r.getMessage() for r in caplog.records]
        name_warnings = [m for m in msgs if "resolve fonts by absolute path" in m]
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
    """``valign`` resolution at the dispatch level.

    Default is ``"center"`` everywhere (planar and curved). On curved walls
    and rim arcs per-glyph emit is always ``halign="left"`` /
    ``valign="baseline"``, so the user's ``valign`` only governs *block*
    placement on multi-line labels; on single-line it has no effect (the
    line stacks at offset 0). All four valign values are accepted on every
    host kind.
    """

    def test_curved_per_glyph_emit_is_left_baseline(self):
        # Regardless of user's valign, per-glyph emit on curved hosts uses
        # halign="left" + valign="baseline" — both OpenSCAD defaults, elided
        # in the emitter. The user's valign at most governs block placement
        # for multi-line; per-glyph emit is fixed.
        for vk in (None, "center", "top", "bottom", "baseline"):
            kwargs = {"valign": vk} if vk is not None else {}
            scad = _emit(
                cylinder(h=20, r=10).add_text(
                    label="X", relief=0.4, on="outer_wall", font_size=4,
                    **kwargs,
                )
            )
            assert 'valign="center"' not in scad, (vk, scad)
            assert 'halign="center"' not in scad, (vk, scad)
            assert 'text("X", size=4)' in scad, (vk, scad)

    def test_curved_explicit_valign_center_accepted(self):
        # No rejection — block-level center is sensible for multi-line and
        # the per-glyph emit is forced baseline anyway.
        scad = _emit(
            cylinder(h=20, r=10).add_text(
                label="X", relief=0.4, on="outer_wall", font_size=4,
                valign="center",
            )
        )
        assert 'text("X"' in scad

    def test_conical_explicit_valign_center_accepted(self):
        scad = _emit(
            cylinder(h=20, r1=10, r2=4).add_text(
                label="X", relief=0.4, on="outer_wall", font_size=4,
                valign="center",
            )
        )
        assert 'text("X"' in scad

    def test_inner_wall_explicit_valign_center_accepted(self):
        scad = _emit(
            Tube(h=30, od=24, thk=2).add_text(
                label="X", relief=0.4, on="inner_wall", font_size=4,
                valign="center",
            )
        )
        assert 'text("X"' in scad

    def test_rim_arc_explicit_valign_center_accepted(self):
        scad = _emit(
            cylinder(h=10, r=15).add_text(
                label="X", relief=0.4, on="top", font_size=4,
                valign="center",
            )
        )
        assert 'text("X"' in scad

    def test_planar_default_is_center(self):
        # A flat planar face emits one whole-line text() with valign="center".
        scad = _emit(
            cube([20, 20, 4], center="xy").add_text(
                label="X", relief=0.4, on="top", font_size=4,
            )
        )
        assert 'valign="center"' in scad

    def test_planar_explicit_valign_top_overrides_default(self):
        scad = _emit(
            cube([20, 20, 4], center="xy").add_text(
                label="X", relief=0.4, on="top", font_size=4,
                valign="top",
            )
        )
        assert 'valign="top"' in scad

    def test_rim_arc_flat_curvature_default_center(self):
        # text_curvature="flat" on a rim takes the planar (whole-line) path,
        # which forwards valign into the single text() call.
        scad = _emit(
            cylinder(h=10, r=15).add_text(
                label="X", relief=0.4, on="top", font_size=4,
                text_curvature="flat",
            )
        )
        assert 'valign="center"' in scad

    def test_curved_multiline_center_centers_block(self):
        # valign="center" on a multi-line curved label centers the block
        # axially around at_z=0 — line 0 above, line 1 below by equal amounts.
        scad = _emit(
            cylinder(h=40, r=10).add_text(
                label="A\nB", relief=0.4, on="outer_wall", font_size=4,
                valign="center",
            )
        )
        positions = _glyph_translates_3d(scad)
        # Two glyphs (one per line). Their z-coords should be symmetric
        # around the cylinder's mid-wall (z=20) since the cylinder bottom
        # is at z=0 by default.
        assert len(positions) == 2
        zs = sorted(p[2] for p in positions)
        center = (zs[0] + zs[1]) / 2.0
        assert center == pytest.approx(20.0, abs=0.05)


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
        # 2D pre-centering: heuristic mode → advance=0.6*4=2.4, half=1.2 in x;
        # font_size=4, half=2 in y. Centers each glyph on its placement origin.
        assert "translate([-1.2, -2, 0])" in scad

    def test_per_glyph_emit_on_rim_arc(self):
        scad = _emit(
            cylinder(h=10, r=15).add_text(
                label="AB", relief=0.4, on="top", font_size=4,
            )
        )
        assert 'halign="center"' not in scad
        assert 'valign="center"' not in scad
        assert "translate([-1.2, -2, 0])" in scad


def test_heuristic_uniform_pre_translate():
    """In heuristic mode (no freetype marker → autouse fixture disables it)
    every glyph gets the same -advance/2 pre-translate in x."""
    scad = _emit(
        cylinder(h=20, r=10).add_text(
            label="iW", relief=0.4, on="outer_wall", font_size=4,
        )
    )
    import re
    # Format is `translate([-X, -Y, 0])` where -Y = -font_size/2.
    translates = re.findall(r"translate\(\[(-?\d+\.\d+), -?\d+\.?\d*, 0\]\)", scad)
    xs = {float(t) for t in translates if float(t) < 0}
    # Heuristic: every glyph gets the same x of -0.6 * size / 2 = -1.2 at size=4.
    assert xs == {-1.2}, (
        f"expected uniform -1.2 x pre-translate, got {translates}"
    )


# --- Cumulative-offset math, end-to-end ---


import math
import re


def _glyph_translates_3d(scad):
    """Extract the per-glyph outer Translate ``(x, y, z)`` triples from emitted
    SCAD. Each per-glyph block starts with ``translate([x, y, z]) { multmatrix(...)``;
    we anchor on that pattern so we don't pick up the inner 2D pre-translate."""
    pat = re.compile(
        r"translate\(\[(-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?)\]\)"
        r"\s*\{\s*multmatrix",
    )
    return [(float(x), float(y), float(z)) for x, y, z in pat.findall(scad)]


class TestCumulativeOffsetMath:
    """End-to-end checks that cumulative per-glyph offsets land glyphs at the
    expected 3D positions on a cylinder (heuristic mode → known per-glyph advance)."""

    def test_circumferential_three_chars_centered_on_meridian(self):
        # "ABC" on a cylinder(h=20, r=10), default meridian +x, halign=center.
        # Heuristic advance = 0.6 * 4 = 2.4mm per char; total = 7.2mm.
        # Glyph centers in mm: [-2.4, 0, +2.4]; theta_off = mm/radius = ±0.24, 0.
        # raised relief=0.4 → d = r - eps = 10 - 0.01 = 9.99.
        # axis_origin = (0, 0, 10). So 3D positions are
        # (9.99 cos θ, 9.99 sin θ, 10) for θ in {-0.24, 0, +0.24}.
        scad = _emit(
            cylinder(h=20, r=10).add_text(
                label="ABC", relief=0.4, on="outer_wall", font_size=4,
            )
        )
        positions = _glyph_translates_3d(scad)
        assert len(positions) == 3, positions
        positions.sort(key=lambda p: p[1])  # sort by y (the meridian-tangent axis)
        x_a, x_b, x_c = (9.99 * math.cos(0.24), 9.99, 9.99 * math.cos(0.24))
        y_a, y_b, y_c = (-9.99 * math.sin(0.24), 0.0, +9.99 * math.sin(0.24))
        assert positions[0] == pytest.approx((x_a, y_a, 10.0), abs=0.005)
        assert positions[1] == pytest.approx((x_b, y_b, 10.0), abs=0.005)
        assert positions[2] == pytest.approx((x_c, y_c, 10.0), abs=0.005)

    def test_axial_three_chars_centered_on_mid_wall(self):
        # text_dir="axial" → glyphs stack along z, all at the same theta.
        # Heuristic axial step = 0.6 * 4 = 2.4mm. Centers at [-2.4, 0, +2.4]
        # (in axial mm); sign = -1.0 for default flip=False (top-to-bottom).
        # So char 0 sits at z = 2.4 + axis_origin.z (top), char 2 at z = -2.4 + ...
        scad = _emit(
            cylinder(h=20, r=10).add_text(
                label="ABC", relief=0.4, on="outer_wall", font_size=4,
                text_dir="axial",
            )
        )
        positions = _glyph_translates_3d(scad)
        assert len(positions) == 3, positions
        # All three glyphs at the +x meridian (x ≈ 9.99, y ≈ 0).
        for p in positions:
            assert p[0] == pytest.approx(9.99, abs=0.005), p
            assert p[1] == pytest.approx(0.0, abs=0.005), p
        # z ordering: char 0 at top (z=12.4), char 1 at z=10, char 2 at z=7.6.
        zs = sorted(p[2] for p in positions)
        assert zs == pytest.approx([7.6, 10.0, 12.4], abs=0.005)


@pytest.mark.freetype
class TestAxialModeUsesProportionalAdvances:
    """text_dir="axial" with real font metrics: per-glyph axial spacing is
    proportional, not uniform."""

    def test_iWi_axial_offsets_reflect_real_advances(self, bundled_font_path):
        # "iWi" on a cylinder with axial layout. Liberation Sans 2.00.1
        # advances at size=4 with default calibration: i ≈ 1.21mm, W ≈ 5.13mm
        # (matches OpenSCAD's flat text() rendering). Centers (halign=center)
        # are [-(W/2 + i/2), 0, +(W/2 + i/2)] = [-3.17, 0, +3.17] in axial
        # mm, times sign=-1 → z offsets [+3.17, 0, -3.17] from line centre
        # (z=10). Step between adjacent glyphs is (i + W) / 2 ≈ 3.17mm.
        scad = _emit(
            cylinder(h=20, r=10).add_text(
                label="iWi", relief=0.4, on="outer_wall", font_size=4,
                text_dir="axial", font=bundled_font_path,
            )
        )
        positions = _glyph_translates_3d(scad)
        assert len(positions) == 3
        zs = sorted(p[2] for p in positions)
        step_lo = zs[1] - zs[0]
        step_hi = zs[2] - zs[1]
        assert step_lo == pytest.approx(step_hi, abs=0.01), (
            f"i-W-i is symmetric, expected equal steps, got {zs}"
        )
        assert step_lo == pytest.approx(3.167, abs=0.05), (
            f"expected step ≈ 3.17mm (advance midpoint of i+W), got {step_lo}"
        )


@pytest.mark.freetype
class TestConicalAxialCumulativeRadius:
    """text_dir="axial" on a conical wall: each glyph's local radius is looked
    up via compute_geom_at(at_z + cumulative_advance_so_far), so per-glyph
    radial position varies along the cone."""

    def test_cone_axial_per_glyph_radius_tracks_cumulative_at_z(self, bundled_font_path):
        # Tapered cylinder: r1=10 at bottom, r2=4 at top, h=20. r_mid=7,
        # slope = (4-10)/20 = -0.3. So local radius at at_z is 7 + at_z*-0.3.
        # With "iWi" axial centered (default calibration matches OpenSCAD),
        # char positions at_z = +3.167, 0, -3.167 (sign=-1 default flip=False;
        # char 0 at top, char 2 at bottom). Local radius: top = 7 - 0.95 = 6.05;
        # mid = 7; bottom = 7.95. Each glyph's translate.x ≈ local_radius - eps.
        scad = _emit(
            cylinder(h=20, r1=10, r2=4).add_text(
                label="iWi", relief=0.4, on="outer_wall", font_size=4,
                text_dir="axial", font=bundled_font_path,
            )
        )
        positions = _glyph_translates_3d(scad)
        assert len(positions) == 3
        # Sort by z descending (top first).
        positions.sort(key=lambda p: -p[2])
        top, mid, bot = positions
        # Top char at z ≈ 13.167. Local radius = 7 + 3.167 × -0.3 ≈ 6.05.
        assert top[2] == pytest.approx(13.167, abs=0.05)
        assert top[0] == pytest.approx(6.05 - 0.01, abs=0.05)
        # Mid at z=10, radius=7.
        assert mid[2] == pytest.approx(10.0, abs=0.05)
        assert mid[0] == pytest.approx(7.0 - 0.01, abs=0.05)
        # Bottom at z ≈ 6.833, radius = 7 + (-3.167)*-0.3 ≈ 7.95.
        assert bot[2] == pytest.approx(6.833, abs=0.05)
        assert bot[0] == pytest.approx(7.95 - 0.01, abs=0.05)


@pytest.mark.freetype
class TestRimArcCumulativeOffsets:
    """Rim-arc placement uses cumulative-advance angular offsets so glyph
    centers land at theta = (cum + advance/2 - total/2) / path_radius."""

    def test_rim_arc_iWi_glyph_angles_proportional(self, bundled_font_path):
        # cylinder(h=10, r=15).top — rim arc. Default at_radial = max(15-4, 2) = 11.
        # "iWi" with halign=center. theta(glyph_n) = center_mm[n] / 11.
        # Glyph 3D position on the rim: ≈ (11 cos θ, 11 sin θ, 10 + ε) where
        # the rim normal lifts by ±eps.
        scad = _emit(
            cylinder(h=10, r=15).add_text(
                label="iWi", relief=0.4, on="top", font_size=4,
                font=bundled_font_path,
            )
        )
        positions = _glyph_translates_3d(scad)
        assert len(positions) == 3
        # All on the +z face. For raised relief the extrusion BASE is shifted
        # by -eps (into the host) so the extrusion overlaps cleanly through
        # the rim plane; visible relief extends above z=10.
        for p in positions:
            assert p[2] == pytest.approx(9.99, abs=0.005), p
        # Compute each glyph's theta from atan2(y, x) and verify symmetry +
        # proportional steps. i-W spacing should equal W-i spacing (palindrome).
        thetas = sorted(math.atan2(p[1], p[0]) for p in positions)
        step_lo = thetas[1] - thetas[0]
        step_hi = thetas[2] - thetas[1]
        assert step_lo == pytest.approx(step_hi, abs=1e-4), (
            f"iWi is a palindrome, expected equal angular steps, got {thetas}"
        )
        # Step magnitude: theta_step = (i_advance + W_advance) / 2 / path_radius.
        # Liberation Sans at size=4 with default calibration: i ≈ 1.21mm,
        # W ≈ 5.13mm; step ≈ 3.167/11 ≈ 0.288 rad.
        assert step_lo == pytest.approx(0.288, abs=0.005), (
            f"expected step ≈ 0.288 rad, got {step_lo}"
        )


# --- Overflow check still uses the heuristic ---


@pytest.mark.freetype
class TestOverflowCheckIgnoresMetrics:
    """``_check_overflow_block`` and ``_check_overflow`` are best-effort
    estimators on planar dispatch and don't consult ``get_advances``. Even
    with real metrics active, the warning fires (or doesn't) based on the
    heuristic estimate."""

    def test_iiii_warns_under_heuristic_even_when_real_is_smaller(
        self, bundled_font_path, caplog,
    ):
        # 4 narrow ``i`` glyphs at size=2: heuristic estimate = 4 * 0.6 * 2 = 4.8mm,
        # real Liberation Sans width ≈ 4 * 0.444 = 1.78mm. On a 4mm-wide face,
        # heuristic would warn; real metrics wouldn't. We assert the warning fires
        # — proving the overflow check is heuristic-driven, even though we passed
        # an absolute font path that would otherwise enable proportional spacing
        # for the curved-wall code path (planar uses one whole-line text() call,
        # so this only proves overflow checks aren't reaching for metrics).
        with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
            _emit(
                cube([4, 10, 2], center="xy").add_text(
                    label="iiii", relief=0.3, on="top", font_size=2,
                    font=bundled_font_path,
                )
            )
        msgs = [r.getMessage() for r in caplog.records]
        assert any("overflows face" in m for m in msgs), (
            f"expected heuristic-based overflow warning, got {msgs}"
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
        # Liberation Sans at size=4 with default calibration: i ≈ 1.21mm,
        # W ≈ 5.13mm. Pre-translate per glyph is -advance/2 in the 2D
        # frame. Don't assert exact byte values (that would tie the test to
        # a specific float-format of the rendering); both must be present
        # and distinct.
        import re
        translates = re.findall(r"translate\(\[(-?\d+\.\d+), -?\d+\.?\d*, 0\]\)", scad)
        vals = sorted({float(t) for t in translates if float(t) < 0})
        assert len(vals) >= 2, (
            f"expected distinct per-glyph 2D pre-translates, got {translates}"
        )


@pytest.mark.freetype
class TestAdvanceCalibration:
    """``text_advance_calibration`` context manager scales advance widths."""

    def test_default_matches_openscad(self, bundled_font_path):
        # No calibration override: advances match OpenSCAD's flat layout
        # for Liberation Sans (verified empirically).
        adv = get_advances(
            ("i",), font=bundled_font_path, size=4.0, spacing=1.0,
        )
        assert adv[0] == pytest.approx(1.205, abs=0.01)

    def test_override_below_one_packs_tighter(self, bundled_font_path):
        from scadwright import text_advance_calibration

        with text_advance_calibration(1.0):
            # 1.0 reverts to bare em-relative scaling (no OpenSCAD-matching
            # 1.5 multiplier), giving ~26% tighter advances.
            adv = get_advances(
                ("i",), font=bundled_font_path, size=4.0, spacing=1.0,
            )
        assert adv[0] == pytest.approx(0.804, abs=0.01)

    def test_override_above_default_loosens(self, bundled_font_path):
        from scadwright import text_advance_calibration

        with text_advance_calibration(3.0):
            # 2× the default 1.5 factor → 2× the default advance.
            adv = get_advances(
                ("i",), font=bundled_font_path, size=4.0, spacing=1.0,
            )
        # Default is 1.205; doubling the calibration doubles the advance.
        assert adv[0] == pytest.approx(2.41, abs=0.02)

    def test_override_resets_after_block(self, bundled_font_path):
        from scadwright import text_advance_calibration

        before = get_advances(
            ("i",), font=bundled_font_path, size=4.0, spacing=1.0,
        )
        with text_advance_calibration(1.0):
            pass
        after = get_advances(
            ("i",), font=bundled_font_path, size=4.0, spacing=1.0,
        )
        assert before == after

    def test_override_nests(self, bundled_font_path):
        from scadwright import text_advance_calibration

        outer = []
        inner = []
        with text_advance_calibration(1.0):
            outer.append(get_advances(
                ("i",), font=bundled_font_path, size=4.0, spacing=1.0,
            )[0])
            with text_advance_calibration(3.0):
                inner.append(get_advances(
                    ("i",), font=bundled_font_path, size=4.0, spacing=1.0,
                )[0])
            outer.append(get_advances(
                ("i",), font=bundled_font_path, size=4.0, spacing=1.0,
            )[0])
        assert outer[0] == outer[1]  # restored on exit of inner
        assert inner[0] != outer[0]


def test_text_advance_calibration_rejects_non_positive():
    from scadwright import text_advance_calibration
    with pytest.raises(ValueError, match="positive"):
        with text_advance_calibration(0):
            pass
    with pytest.raises(ValueError, match="positive"):
        with text_advance_calibration(-1.5):
            pass


def test_text_advance_calibration_no_effect_on_heuristic():
    # The calibration is for the freetype path; heuristic stays at 0.6 * size.
    from scadwright import text_advance_calibration

    base = get_advances(("X",), font=None, size=4.0, spacing=1.0)
    with text_advance_calibration(2.0):
        scaled = get_advances(("X",), font=None, size=4.0, spacing=1.0)
    assert base == scaled
