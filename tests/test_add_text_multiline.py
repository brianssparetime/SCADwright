"""Tests for multi-line add_text (label containing ``\\n``)."""

import logging
import re

import pytest

from scadwright.emit import emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder
from scadwright.shapes import Funnel, Tube


def _translates(scad: str) -> list[tuple[float, ...]]:
    """Extract all top-level translate vectors from emitted SCAD."""
    out = []
    for m in re.findall(r"translate\(\[([^\]]+)\]\)", scad):
        out.append(tuple(float(p.strip()) for p in m.split(",")))
    return out


# --- Smoke ---


def test_planar_multiline_emits():
    p = cube([60, 30, 5]).add_text(
        label="LINE 1\nLINE 2", relief=0.4, on="top", font_size=4,
    )
    scad = emit_str(p)
    assert '"LINE 1"' in scad
    assert '"LINE 2"' in scad


def test_cylindrical_multiline_emits():
    p = cylinder(h=30, r=10).add_text(
        label="AB\nCD", relief=0.4, on="outer_wall", font_size=4,
    )
    scad = emit_str(p)
    for ch in "ABCD":
        assert f'text("{ch}"' in scad


def test_conical_multiline_emits():
    p = Funnel(h=30, bot_od=20, top_od=10, thk=2).add_text(
        label="LO\nHI", relief=0.3, on="outer_wall", font_size=2,
    )
    scad = emit_str(p)
    for ch in "LOHI":
        assert f'text("{ch}"' in scad


def test_inner_wall_multiline_emits():
    p = Tube(h=30, od=24, thk=2).add_text(
        label="A\nB\nC", relief=0.3, on="inner_wall", font_size=3,
    )
    scad = emit_str(p)
    for ch in "ABC":
        assert f'text("{ch}"' in scad


def test_rim_arc_multiline_emits():
    p = cylinder(h=10, r=15).add_text(
        label="MAX\n5L", relief=0.4, on="top", font_size=2,
    )
    scad = emit_str(p)
    for ch in "MAX5L":
        assert f'text("{ch}"' in scad


# --- Backward compat: single-line behavior unchanged ---


def test_single_line_planar_unchanged():
    """Single-line add_text emits exactly one text() call (no union wrap)."""
    p = cube([40, 20, 5]).add_text(
        label="HI", relief=0.4, on="top", font_size=4,
    )
    scad = emit_str(p)
    # Only one text() call — single-line takes the legacy path.
    assert scad.count('text("HI"') == 1
    # Outer structure: union of cube + linear_extrude(text). No inner union.
    # Strip whitespace and the cube primitive line, then check for nested unions.
    body = scad.split("union() {")[1]
    assert body.count("union()") == 0  # no extra union wrappers


# --- Line ordering (line 0 visually at top) ---


def test_planar_line_0_above_line_1():
    """In the 2D extruded shape, line 0 has larger Y than line 1."""
    p = cube([60, 30, 5]).add_text(
        label="TOP\nBOT", relief=0.4, on="top", font_size=4,
    )
    scad = emit_str(p)
    # The two inner translates are inside the union of text() nodes; their
    # Y components encode the line offsets.
    inner = re.findall(r"translate\(\[0, ([\-0-9.]+), 0\]\)", scad)
    assert len(inner) == 2
    y_top, y_bot = float(inner[0]), float(inner[1])
    assert y_top > y_bot


def test_cylindrical_line_0_at_higher_z():
    """Line 0 sits at a larger axial position than line 1 on a cylinder wall."""
    p = cylinder(h=30, r=10).add_text(
        label="A\nB", relief=0.4, on="outer_wall", font_size=4,
    )
    scad = emit_str(p)
    glyph_translates = [t for t in _translates(scad) if len(t) == 3 and t[0] > 1]
    # Two glyphs (A above B) — A's z > B's z.
    z_values = sorted(t[2] for t in glyph_translates)
    # A higher up the cylinder, B lower.
    assert glyph_translates[0][2] > glyph_translates[1][2]


def test_rim_arc_line_0_at_outer_radius():
    """On a rim, line 0 sits at a larger path radius than line 1."""
    p = cylinder(h=10, r=15).add_text(
        label="A\nB", relief=0.4, on="top", font_size=2,
    )
    scad = emit_str(p)
    glyph_translates = [t for t in _translates(scad) if len(t) == 3 and abs(t[0]) > 1]
    # Two glyphs; the outer (line 0) has |x| greater than the inner (line 1).
    radii = [(t[0] ** 2 + t[1] ** 2) ** 0.5 for t in glyph_translates]
    assert radii[0] > radii[1]


# --- valign block positioning ---


def test_valign_center_block_centered():
    """valign='center' (default) centers the 2-line block on the face center."""
    p = cube([60, 30, 5]).add_text(
        label="L1\nL2", relief=0.4, on="top", font_size=4, line_spacing=1.2,
    )
    scad = emit_str(p)
    inner = re.findall(r"translate\(\[0, ([\-0-9.]+), 0\]\)", scad)
    y_top, y_bot = float(inner[0]), float(inner[1])
    # Lines should be symmetric around y=0.
    assert y_top == pytest.approx(-y_bot, abs=1e-6)


def test_valign_top_puts_line_0_near_top():
    """valign='top' places top of block at face anchor (y=0 in the 2D frame)."""
    p = cube([60, 30, 5]).add_text(
        label="L1\nL2", relief=0.4, on="top", font_size=4, valign="top",
    )
    scad = emit_str(p)
    inner = re.findall(r"translate\(\[0, ([\-0-9.]+), 0\]\)", scad)
    y_top = float(inner[0])
    # base_y_top = -font_size/2 = -2 → line 0 at y=-2.
    assert y_top == pytest.approx(-2.0, abs=1e-6)


def test_valign_bottom_puts_line_n_near_bottom():
    p = cube([60, 30, 5]).add_text(
        label="L1\nL2", relief=0.4, on="top", font_size=4, valign="bottom",
    )
    scad = emit_str(p)
    inner = re.findall(r"translate\(\[0, ([\-0-9.]+), 0\]\)", scad)
    y_bot = float(inner[1])
    # base_y_top = block_h - font_size/2 = 8.8 - 2 = 6.8
    # line 1 at 6.8 - 1.2*4 = 2.0 (font_size/2 above face anchor).
    assert y_bot == pytest.approx(2.0, abs=1e-6)


# --- line_spacing controls ---


def test_line_spacing_smaller_brings_lines_closer():
    a = emit_str(cube([60, 30, 5]).add_text(
        label="A\nB", relief=0.4, on="top", font_size=4, line_spacing=1.0,
    ))
    b = emit_str(cube([60, 30, 5]).add_text(
        label="A\nB", relief=0.4, on="top", font_size=4, line_spacing=2.0,
    ))
    a_ys = [float(y) for y in re.findall(r"translate\(\[0, ([\-0-9.]+), 0\]\)", a)]
    b_ys = [float(y) for y in re.findall(r"translate\(\[0, ([\-0-9.]+), 0\]\)", b)]
    a_gap = abs(a_ys[0] - a_ys[1])
    b_gap = abs(b_ys[0] - b_ys[1])
    assert b_gap > a_gap


def test_line_spacing_zero_rejected():
    with pytest.raises(ValidationError, match="line_spacing"):
        emit_str(cube([20, 20, 5]).add_text(
            label="A\nB", relief=0.4, on="top", font_size=4, line_spacing=0,
        ))


def test_line_spacing_negative_rejected():
    with pytest.raises(ValidationError, match="line_spacing"):
        emit_str(cube([20, 20, 5]).add_text(
            label="A\nB", relief=0.4, on="top", font_size=4, line_spacing=-1,
        ))


# --- Empty lines ---


def test_empty_line_keeps_spacing_slot():
    """A blank line (consecutive \\n) preserves spacing but emits nothing."""
    a = emit_str(cube([60, 60, 5]).add_text(
        label="A\nB", relief=0.4, on="top", font_size=4,
    ))
    b = emit_str(cube([60, 60, 5]).add_text(
        label="A\n\nB", relief=0.4, on="top", font_size=4,
    ))
    # In version `a`, lines A and B are at y=±2.4. In version `b`, the
    # empty middle line takes a slot, so A and B move further apart.
    a_ys = sorted(float(y) for y in re.findall(r"translate\(\[0, ([\-0-9.]+), 0\]\)", a))
    b_ys = sorted(float(y) for y in re.findall(r"translate\(\[0, ([\-0-9.]+), 0\]\)", b))
    assert (b_ys[1] - b_ys[0]) > (a_ys[1] - a_ys[0])
    # Both still have only two text() calls (empty line emits nothing).
    assert b.count('text("A"') == 1
    assert b.count('text("B"') == 1


def test_all_empty_lines_rejected():
    with pytest.raises(ValidationError, match="non-empty line"):
        emit_str(cube([20, 20, 5]).add_text(
            label="\n\n", relief=0.4, on="top", font_size=4,
        ))


# --- direction conflict ---


def test_ttb_with_newline_rejected():
    with pytest.raises(ValidationError, match="single-line only"):
        emit_str(cube([20, 20, 5]).add_text(
            label="A\nB", relief=0.4, on="top", font_size=4, direction="ttb",
        ))


def test_btt_with_newline_rejected():
    with pytest.raises(ValidationError, match="single-line only"):
        emit_str(cube([20, 20, 5]).add_text(
            label="A\nB", relief=0.4, on="top", font_size=4, direction="btt",
        ))


# --- Conical per-line radius ---


def test_funnel_outer_lines_have_different_local_radii():
    """Cone narrowing-up: top line has smaller radius than bottom line.
    The glyph translates' (x, y) magnitudes encode the radius at each line."""
    p = Funnel(h=30, bot_od=30, top_od=10, thk=2).add_text(
        label="HI\nLO", relief=0.3, on="outer_wall", font_size=2,
    )
    scad = emit_str(p)
    glyph_translates = [t for t in _translates(scad) if len(t) == 3 and abs(t[0]) > 1]
    # Pull out the (x) component (since meridian="+x" places at world +X).
    # Top line ("HI") at higher z, smaller cone radius. Bottom line at larger.
    z_to_x = {round(t[2], 2): t[0] for t in glyph_translates}
    z_top, z_bot = max(z_to_x), min(z_to_x)
    assert z_to_x[z_top] < z_to_x[z_bot]


# --- Cone-tip per-line ---


def test_funnel_line_past_tip_rejected():
    """A line at_z that puts local_radius past the cone tip is an error
    citing the offending line."""
    # Funnel narrowing to a tiny top: bot_od=20, top_od=2 → r1=8 inner-mid=5.
    # Wait, simpler: use Funnel where the top is very narrow and an at_z
    # plus line offset pushes a line past the tip.
    f = Funnel(h=30, bot_od=20, top_od=2, thk=0.5)
    # Inner: r1=9.5, r2=0.5, mid_radius=5. Slope = (0.5 - 9.5)/30 = -0.3.
    # at_z=15 → mid + 15*-0.3 = 0.5 (just at the tip).
    # With 2 lines at line_spacing=1.2, font_size=4: line offsets ±2.4.
    # Top line at_z = 15 + 2.4 = 17.4 → radius = 5 - 17.4*0.3 = -0.22 (past tip).
    with pytest.raises(ValidationError, match="cone tip"):
        emit_str(f.add_text(
            label="A\nB", relief=0.3, on="inner_wall", font_size=4,
            at_z=15, line_spacing=1.2,
        ))


# --- Rim per-line radius ---


def test_rim_line_non_positive_radius_rejected():
    """If the inner line of a multi-line rim arc would have non-positive
    path radius, raise."""
    # Small rim (r=5), large font_size and line_spacing → inner line
    # radius could go below 0.
    with pytest.raises(ValidationError, match="non-positive"):
        emit_str(cylinder(h=10, r=5).add_text(
            label="A\nB", relief=0.3, on="top", font_size=8, line_spacing=2.0,
        ))


# --- Overflow per-block ---


def test_multiline_block_overflow_warns(caplog):
    """Block height (n lines * spacing) exceeding face height triggers warning."""
    with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
        # Plate is 30x4 (only 4mm tall); font_size=8, 2 lines → block ~17.6mm.
        emit_str(cube([30, 4, 5]).add_text(
            label="A\nB", relief=0.3, on="top", font_size=8,
        ))
    assert any("overflows face" in r.message for r in caplog.records)


# --- Pathway B ---


def test_multiline_chains_through_decoration():
    p = (
        cube([60, 30, 5])
        .add_text(label="LINE 1\nLINE 2", relief=0.4, on="top", font_size=4)
        .add_text(label="SIDE", relief=0.3, on="rside", font_size=3)
    )
    scad = emit_str(p)
    assert '"LINE 1"' in scad
    assert '"LINE 2"' in scad
    assert '"SIDE"' in scad
