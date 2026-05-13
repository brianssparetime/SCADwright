"""Tests for the text_dir / rotate_glyphs / flip kwargs on add_text.

These cover all 8 combinations of (text_dir, rotate_glyphs, flip) on a
cylindrical wall, the conical and meridional wall cases, and the
validation rejections (planar + axial, multi-line + axial, kwarg type
checks).

The geometric oracle: each glyph's MultMatrix matrix maps glyph-local
(+X, +Y, +Z) to (g_right, g_up, extrude_dir) in world. Tests assert the
matrix columns equal the expected world-frame directions for the combo.
"""

import math

import pytest

from scadwright._custom_transforms.base import get_transform
from scadwright.ast.csg import Difference, Union
from scadwright.ast.custom import Custom
from scadwright.ast.transforms import MultMatrix, Translate
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder
from scadwright.shapes import Barrel, Tube


def _expand(custom_node):
    """Run add_text's inline expand() to get the actual geometry tree."""
    t = get_transform("add_text")
    return t.expand(custom_node.child, **custom_node.kwargs_dict())


def _glyph_matrices(node):
    """Walk an add_text result and return the MultMatrix matrices for each
    placed glyph, in placement order. Each glyph is a Translate→MultMatrix
    chain wrapping the extruded text.
    """
    if isinstance(node, Custom):
        node = _expand(node)
    if isinstance(node, (Union, Difference)):
        # First child is host; rest are glyphs.
        glyphs = node.children[1:]
    else:
        glyphs = [node]
    out = []
    for g in glyphs:
        # Glyph: Translate → MultMatrix → linear_extrude(...) → text(...)
        cur = g
        while isinstance(cur, Translate):
            cur = cur.child
        if isinstance(cur, MultMatrix):
            out.append(cur.matrix)
    return out


def _column(matrix, col):
    """Return column ``col`` (0/1/2) of a Matrix as a 3-tuple."""
    rows = matrix.elements
    return (rows[0][col], rows[1][col], rows[2][col])


def _glyph_positions(node):
    """Return the world position of each glyph (the Translate's v vector)."""
    if isinstance(node, Custom):
        node = _expand(node)
    if isinstance(node, (Union, Difference)):
        glyphs = node.children[1:]
    else:
        glyphs = [node]
    out = []
    for g in glyphs:
        if isinstance(g, Translate):
            out.append(g.v)
    return out


# --- The 8 combinations on a vertical cylinder ---
#
# Cylinder along +Z, outer_wall anchor at angle=0 (+X meridian). For a
# single character at angle=0, at_z=0:
#   tangent (e1) = +Y
#   axis    (e2) = +Z
#   radial  (out) = +X (outward from cylinder material).


HUB_KW = dict(h=40, r=10)
TXT_KW = dict(label="X", relief=0.5, font_size=4, on="outer_wall")


def _orient_columns(hub, **kwargs):
    """Render add_text on hub with the given kwargs and return the single
    glyph's (g_right, g_up, extrude_dir) columns from its MultMatrix."""
    result = hub.add_text(**TXT_KW, **kwargs)
    matrices = _glyph_matrices(result)
    assert len(matrices) == 1, "expected exactly one glyph for label='X'"
    m = matrices[0]
    return _column(m, 0), _column(m, 1), _column(m, 2)


def test_circumferential_default():
    """text_dir=circumferential, rg=False, flip=False (default).
    g_right = +tangent (+Y), g_up = +axis (+Z), out = +radial (+X)."""
    hub = cylinder(**HUB_KW)
    g_right, g_up, out = _orient_columns(hub)
    assert g_right == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)
    assert g_up == pytest.approx((0.0, 0.0, 1.0), abs=1e-9)
    assert out == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)


def test_circumferential_flip():
    """text_dir=circumferential, rg=False, flip=True.
    g_right = -tangent, g_up = -axis. Letters rotated 180°."""
    hub = cylinder(**HUB_KW)
    g_right, g_up, out = _orient_columns(hub, flip=True)
    assert g_right == pytest.approx((0.0, -1.0, 0.0), abs=1e-9)
    assert g_up == pytest.approx((0.0, 0.0, -1.0), abs=1e-9)
    assert out == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)


def test_circumferential_rotate_glyphs():
    """text_dir=circumferential, rg=True, flip=False.

    On a circumferential line, rotate_glyphs gets an extra 180° rotation
    compared to the axial+rg case so that ``flip`` reverses only the wrap
    direction (not the letter orientation). Result: g_right = +axis,
    g_up = -tangent. Letters lying on their backs with tops pointing
    against the wrap direction (the natural curved-label convention)."""
    hub = cylinder(**HUB_KW)
    g_right, g_up, out = _orient_columns(hub, rotate_glyphs=True)
    assert g_right == pytest.approx((0.0, 0.0, 1.0), abs=1e-9)
    assert g_up == pytest.approx((0.0, -1.0, 0.0), abs=1e-9)
    assert out == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)


def test_circumferential_rotate_glyphs_flip():
    """text_dir=circumferential, rg=True, flip=True.

    Same letter orientation as the no-flip variant; only the wrap direction
    reverses. g_right = -axis, g_up = +tangent."""
    hub = cylinder(**HUB_KW)
    g_right, g_up, out = _orient_columns(hub, rotate_glyphs=True, flip=True)
    assert g_right == pytest.approx((0.0, 0.0, -1.0), abs=1e-9)
    assert g_up == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)
    assert out == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)


def test_axial_default():
    """text_dir=axial, rg=False, flip=False.
    g_right = +tangent, g_up = +axis. Same orientation as default,
    BUT line goes axially (per-char advance is along -axis, not tangent)."""
    hub = cylinder(**HUB_KW)
    g_right, g_up, out = _orient_columns(hub, text_dir="axial")
    assert g_right == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)
    assert g_up == pytest.approx((0.0, 0.0, 1.0), abs=1e-9)
    assert out == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)


def test_axial_rotate_glyphs():
    """text_dir=axial, rg=True, flip=False.
    g_right = -axis, g_up = +tangent. THE primary missing case — letters
    rotated 90° CCW so a line running axially reads naturally if you
    tilt your head."""
    hub = cylinder(**HUB_KW)
    g_right, g_up, out = _orient_columns(hub, text_dir="axial", rotate_glyphs=True)
    assert g_right == pytest.approx((0.0, 0.0, -1.0), abs=1e-9)
    assert g_up == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)
    assert out == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)


def test_axial_flip():
    """text_dir=axial, rg=False, flip=True. Letters upside-down,
    line direction reversed (bottom-to-top instead of top-to-bottom)."""
    hub = cylinder(**HUB_KW)
    g_right, g_up, out = _orient_columns(hub, text_dir="axial", flip=True)
    assert g_right == pytest.approx((0.0, -1.0, 0.0), abs=1e-9)
    assert g_up == pytest.approx((0.0, 0.0, -1.0), abs=1e-9)


def test_axial_rotate_glyphs_flip():
    """text_dir=axial, rg=True, flip=True. Letters rotated 90° CW;
    line bottom-to-top."""
    hub = cylinder(**HUB_KW)
    g_right, g_up, out = _orient_columns(hub, text_dir="axial", rotate_glyphs=True, flip=True)
    assert g_right == pytest.approx((0.0, 0.0, 1.0), abs=1e-9)
    assert g_up == pytest.approx((0.0, -1.0, 0.0), abs=1e-9)


# --- Per-character placement: axial advances along axis, circumferential around it ---


def test_axial_chars_advance_along_axis():
    """For a multi-char label, axial mode places successive chars at
    decreasing z (default flip=False = top-to-bottom). All chars share
    the same x/y (no circumferential motion)."""
    hub = cylinder(h=40, r=10)
    result = hub.add_text(
        label="ABC", relief=0.3, font_size=4, on="outer_wall",
        text_dir="axial",
    )
    positions = _glyph_positions(result)
    assert len(positions) == 3
    # Char 0 (A) at the top, char 2 (C) at the bottom.
    assert positions[0][2] > positions[1][2] > positions[2][2]
    # All chars at the same x and y (single meridian = +X).
    for p in positions:
        assert p[0] == pytest.approx(positions[0][0], abs=1e-9)
        assert p[1] == pytest.approx(positions[0][1], abs=1e-9)


def test_axial_flip_reverses_char_order():
    """flip=True on axial mode places char 0 at the BOTTOM (line goes
    bottom-to-top)."""
    hub = cylinder(h=40, r=10)
    result = hub.add_text(
        label="ABC", relief=0.3, font_size=4, on="outer_wall",
        text_dir="axial", flip=True,
    )
    positions = _glyph_positions(result)
    assert positions[0][2] < positions[1][2] < positions[2][2]


def test_circumferential_chars_advance_around_axis():
    """Default circumferential mode places chars at successive thetas.
    All chars share the same z."""
    hub = cylinder(h=40, r=10)
    result = hub.add_text(
        label="ABC", relief=0.3, font_size=4, on="outer_wall",
    )
    positions = _glyph_positions(result)
    assert len(positions) == 3
    # All chars at the same z (mid-wall by default).
    for p in positions:
        assert p[2] == pytest.approx(positions[0][2], abs=1e-9)


# --- Validation ---


def test_axial_on_planar_raises():
    """text_dir='axial' requires a curved wall; planar surfaces have no
    axis to follow."""
    from scadwright.emit import emit_str
    plate = cube([20, 20, 2])
    with pytest.raises(ValidationError, match="text_dir='axial' requires"):
        emit_str(plate.add_text(
            label="X", relief=0.5, font_size=4, on="top",
            text_dir="axial",
        ))


def test_axial_multiline_stacks_circumferentially():
    """Axial-mode multi-line: each line runs along the axis at its own
    meridian. Lines stack around the cylinder rather than along it.
    Two lines at angle=0 (default) → line 0 at one theta, line 1 at
    a different theta but same axial range."""
    hub = cylinder(h=40, r=10)
    result = hub.add_text(
        label="AB\nCD", relief=0.3, font_size=4, on="outer_wall",
        text_dir="axial",
    )
    positions = _glyph_positions(result)
    assert len(positions) == 4
    # All 4 chars share the cylinder's mid-wall axial center as line center.
    # Within each line: 2 chars with different at_z (axial line).
    # Between lines: same at_z range, but different theta (circumferential).
    # Group by line: chars 0,1 are line 0; chars 2,3 are line 1.
    line0 = positions[:2]
    line1 = positions[2:]
    # Each line spans different z values (axial layout within a line).
    assert line0[0][2] != pytest.approx(line0[1][2])
    assert line1[0][2] != pytest.approx(line1[1][2])
    # Lines at different meridians: different (x, y) but overlapping z range.
    line0_first_xy = (line0[0][0], line0[0][1])
    line1_first_xy = (line1[0][0], line1[0][1])
    assert line0_first_xy != pytest.approx(line1_first_xy, abs=1e-3)


def test_invalid_text_dir_raises():
    from scadwright.emit import emit_str
    hub = cylinder(h=20, r=5)
    with pytest.raises(ValidationError, match="text_dir must"):
        emit_str(hub.add_text(
            label="X", relief=0.3, font_size=4, on="outer_wall",
            text_dir="diagonal",
        ))


def test_rotate_glyphs_must_be_bool():
    from scadwright.emit import emit_str
    hub = cylinder(h=20, r=5)
    with pytest.raises(ValidationError, match="rotate_glyphs must"):
        emit_str(hub.add_text(
            label="X", relief=0.3, font_size=4, on="outer_wall",
            rotate_glyphs="yes",
        ))


def test_flip_must_be_bool():
    from scadwright.emit import emit_str
    hub = cylinder(h=20, r=5)
    with pytest.raises(ValidationError, match="flip must"):
        emit_str(hub.add_text(
            label="X", relief=0.3, font_size=4, on="outer_wall",
            flip=1,
        ))


# --- Conical wall: text_dir="axial" works with text_orient ---


def test_axial_on_cone():
    """Axial-line text on a cone: glyph's per-glyph radius varies with
    at_z. Multi-char label has glyphs at successive z values; their x
    coordinates differ because of the cone's taper."""
    cone = cylinder(h=40, r1=10, r2=4)
    result = cone.add_text(
        label="AB", relief=0.3, font_size=4, on="outer_wall",
        text_dir="axial", at_z=-10,  # away from cone tip
    )
    positions = _glyph_positions(result)
    assert len(positions) == 2
    # Different z for each char.
    assert positions[0][2] != pytest.approx(positions[1][2])
    # Different radial position too: cone tapers, so x differs.
    assert positions[0][0] != pytest.approx(positions[1][0], abs=1e-3)


# --- Meridional wall (Barrel): text_dir="axial" follows the curve ---


def test_axial_on_barrel():
    """Barrel has a meridional outer_wall (curved meridian). Axial-line
    text places glyphs at successive at_z values and the per-glyph
    radius is computed from the arc."""
    barrel = Barrel(h=40, end_r=8, bulge=2)
    result = barrel.add_text(
        label="AB", relief=0.3, font_size=4, on="outer_wall",
        text_dir="axial", at_z=0,
    )
    positions = _glyph_positions(result)
    assert len(positions) == 2
    # Glyphs at different z values.
    assert positions[0][2] != pytest.approx(positions[1][2])


# --- Multi-line axial on curved-axially surfaces ---


def test_axial_multiline_on_cone():
    """Axial multi-line on a cone: each line runs along the cone axis at
    its own meridian. Per-glyph radii vary within each line because of
    the cone's taper."""
    cone = cylinder(h=40, r1=10, r2=4)
    result = cone.add_text(
        label="AB\nCD", relief=0.3, font_size=4, on="outer_wall",
        text_dir="axial",
    )
    positions = _glyph_positions(result)
    assert len(positions) == 4
    # Char 0 (A) and char 2 (C) are line-tops at different meridians.
    a_xy = (positions[0][0], positions[0][1])
    c_xy = (positions[2][0], positions[2][1])
    assert a_xy != pytest.approx(c_xy, abs=1e-3)
    # Within each line, chars are at different at_z, AND different radii
    # (cone tapers).
    assert positions[0][2] != pytest.approx(positions[1][2])


def test_axial_multiline_on_barrel():
    """Axial multi-line on a Barrel (meridional wall). Per-glyph radii
    follow the meridian arc within each line; lines stack
    circumferentially."""
    barrel = Barrel(h=50, end_r=10, bulge=2)
    result = barrel.add_text(
        label="LOT\nNO.", relief=0.3, font_size=4, on="outer_wall",
        text_dir="axial",
    )
    positions = _glyph_positions(result)
    assert len(positions) == 6
    # 3 chars per line, 2 lines.
    line0 = positions[:3]
    line1 = positions[3:]
    # Each line's chars at different z (axial layout).
    line0_zs = [p[2] for p in line0]
    line1_zs = [p[2] for p in line1]
    assert min(line0_zs) != max(line0_zs)
    assert min(line1_zs) != max(line1_zs)
    # Lines at different meridians.
    line0_xy = (line0[0][0], line0[0][1])
    line1_xy = (line1[0][0], line1[0][1])
    assert line0_xy != pytest.approx(line1_xy, abs=1e-3)


# --- text_orient="slant" + text_dir="axial" composition on cones ---


def test_axial_slant_composition_on_cone():
    """text_orient='slant' + text_dir='axial' on a cone: the line follows
    the slant axis (not the cylinder's z axis), and glyph orientation
    matrix uses slant for the 'up' direction."""
    cone = cylinder(h=40, r1=10, r2=4)
    result = cone.add_text(
        label="AB", relief=0.3, font_size=4, on="outer_wall",
        text_dir="axial", text_orient="slant",
    )
    matrices = _glyph_matrices(result)
    assert len(matrices) == 2
    # Each glyph's "up" column (matrix col 1) should have a non-zero
    # outward radial component (slant axis tilts outward on a cone),
    # whereas plain text_orient="axial" would have up_dir = pure +Z.
    for m in matrices:
        up = _column(m, 1)
        assert abs(up[0]) > 1e-6 or abs(up[1]) > 1e-6  # has radial component


# --- flip=True on curved-axially surfaces ---


def test_flip_on_cone():
    """flip=True on a cone: should compose with the cone's slant logic
    without errors."""
    cone = cylinder(h=40, r1=10, r2=4)
    result = cone.add_text(
        label="X", relief=0.3, font_size=4, on="outer_wall",
        flip=True,
    )
    matrices = _glyph_matrices(result)
    assert len(matrices) == 1
    # flip=True negates both the right and up columns.
    g_right = _column(matrices[0], 0)
    g_up = _column(matrices[0], 1)
    # cone outer_wall +X meridian: tangent = +Y, axis-up = +Z.
    # flip flips both.
    assert g_right[1] < 0  # was +Y, now -Y
    assert g_up[2] < 0     # was +Z, now -Z


def test_flip_on_barrel():
    """flip=True on a meridional Barrel wall."""
    barrel = Barrel(h=40, end_r=10, bulge=2)
    result = barrel.add_text(
        label="X", relief=0.3, font_size=4, on="outer_wall",
        flip=True,
    )
    matrices = _glyph_matrices(result)
    assert len(matrices) == 1


# --- Inner wall + axial ---


def test_axial_on_inner_wall():
    """Axial-line text on a Tube's inner wall. The s_outward sign-flip
    handles the inner-wall orientation; axial-line layout should still
    place chars at successive at_z values."""
    tube = Tube(od=30, id=20, h=40)
    result = tube.add_text(
        label="ABC", relief=-0.3, font_size=3, on="inner_wall",
        text_dir="axial",
    )
    positions = _glyph_positions(result)
    assert len(positions) == 3
    # Chars at different z values along the inner wall.
    assert positions[0][2] != pytest.approx(positions[1][2])
    assert positions[1][2] != pytest.approx(positions[2][2])


# --- Overflow warnings ---


def test_axial_overflow_warning(caplog):
    """A label whose total axial extent exceeds the wall length should
    log a warning."""
    import logging
    from scadwright.emit import emit_str
    cyl = cylinder(h=10, r=10)
    long_label = "X" * 30  # 30 chars of axial extent at font_size=4 way > 10mm
    with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
        emit_str(cyl.add_text(
            label=long_label, relief=0.3, font_size=4, on="outer_wall",
            text_dir="axial",
        ))
    assert any("axial extent" in r.message for r in caplog.records)


def test_axial_multiline_circumferential_overflow_warning(caplog):
    """Many lines + axial mode → block wraps past the cylinder."""
    import logging
    from scadwright.emit import emit_str
    cyl = cylinder(h=40, r=2)  # tiny radius
    label = "\n".join(["X"] * 10)  # 10 lines, big spacing
    with caplog.at_level(logging.WARNING, logger="scadwright.add_text"):
        emit_str(cyl.add_text(
            label=label, relief=0.3, font_size=4, on="outer_wall",
            text_dir="axial",
        ))
    assert any("circumferentially" in r.message for r in caplog.records)


# --- Rim anchor rejection ---


def test_text_dir_axial_on_rim_raises():
    from scadwright.emit import emit_str
    cyl = cylinder(h=20, r=10)
    with pytest.raises(ValidationError, match="text_dir='axial' requires"):
        emit_str(cyl.add_text(
            label="X", relief=0.3, font_size=4, on="top",
            text_dir="axial",
        ))


def test_rotate_glyphs_on_rim_raises():
    from scadwright.emit import emit_str
    cyl = cylinder(h=20, r=10)
    with pytest.raises(ValidationError, match="rotate_glyphs=True applies"):
        emit_str(cyl.add_text(
            label="X", relief=0.3, font_size=4, on="top",
            rotate_glyphs=True,
        ))


def test_flip_on_planar_raises():
    from scadwright.emit import emit_str
    plate = cube([20, 20, 2])
    with pytest.raises(ValidationError, match="flip=True applies"):
        emit_str(plate.add_text(
            label="X", relief=0.5, font_size=4, on="top",
            flip=True,
        ))


# --- Backwards compatibility ---


def test_default_kwargs_unchanged():
    """Ensure that adding the new kwargs with their defaults produces
    the same SCAD as not passing them at all (byte-identical for the
    default circumferential, no-rotate, no-flip path)."""
    from scadwright.emit import emit_str
    hub = cylinder(h=40, r=10)
    base = hub.add_text(label="HI", relief=0.3, font_size=4, on="outer_wall")
    explicit = hub.add_text(
        label="HI", relief=0.3, font_size=4, on="outer_wall",
        text_dir="circumferential", rotate_glyphs=False, flip=False,
    )
    assert emit_str(base) == emit_str(explicit)
