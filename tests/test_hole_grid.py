"""Tests for the ``hole_grid`` composition helper."""

import pytest

from scadwright import bbox
from scadwright.boolops import difference
from scadwright.composition_helpers import hole_grid
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder
from scadwright.shapes import clearance_hole


def _count_translates(node, depth=20):
    """Walk the tree and count Translate wrappers — used as a rough
    proxy for how many hole copies got produced."""
    from scadwright.ast.transforms import Translate

    count = 0

    def walk(n, d):
        nonlocal count
        if d == 0:
            return
        if isinstance(n, Translate):
            count += 1
        for attr in ("child", "children"):
            v = getattr(n, attr, None)
            if v is None:
                continue
            if isinstance(v, tuple):
                for c in v:
                    walk(c, d - 1)
            else:
                walk(v, d - 1)

    walk(node, depth)
    return count


def test_hole_grid_default_centered():
    """A 2x2 grid spans (cols-1)*col_spacing × (rows-1)*row_spacing,
    centered on the origin."""
    grid = hole_grid(
        rows=2, cols=2, row_spacing=10, col_spacing=10,
        hole=cylinder(h=2, r=1),
    )
    bb = bbox(grid)
    # 2x2 grid spans 10 in each direction. Each hole has radius 1, so
    # the outer bbox extends ±(5 + 1) = ±6 in x and y.
    assert bb.min[0] == pytest.approx(-6.0, abs=0.1)
    assert bb.max[0] == pytest.approx(6.0, abs=0.1)
    assert bb.min[1] == pytest.approx(-6.0, abs=0.1)
    assert bb.max[1] == pytest.approx(6.0, abs=0.1)


def test_hole_grid_uncentered():
    """center=False puts the bottom-left hole at the origin."""
    grid = hole_grid(
        rows=2, cols=2, row_spacing=10, col_spacing=10,
        hole=cylinder(h=2, r=1),
        center=False,
    )
    bb = bbox(grid)
    # Bottom-left hole's bbox is x in [-1, 1], y in [-1, 1].
    # Top-right hole's bbox is x in [9, 11], y in [9, 11].
    assert bb.min[0] == pytest.approx(-1.0, abs=0.1)
    assert bb.max[0] == pytest.approx(11.0, abs=0.1)


def test_hole_grid_3x4_grid():
    """A 3-row, 4-col grid produces 12 hole copies in total."""
    grid = hole_grid(
        rows=3, cols=4, row_spacing=10, col_spacing=8,
        hole=cylinder(h=2, r=1),
        center=False,
    )
    bb = bbox(grid)
    # cols=4 → x spans (4-1)*8 = 24 (between hole centers); plus ±1 radius.
    assert bb.size[0] == pytest.approx(24 + 2, abs=0.1)
    # rows=3 → y spans (3-1)*10 = 20; plus ±1 radius.
    assert bb.size[1] == pytest.approx(20 + 2, abs=0.1)


def test_hole_grid_composes_with_clearance_hole():
    """hole_grid + clearance_hole + difference produces the standard
    FC-stack drilling pattern."""
    plate = cube([60, 60, 3])
    cutter = hole_grid(
        rows=2, cols=2, row_spacing=30.5, col_spacing=30.5,
        hole=clearance_hole("M3", depth=5),
    )
    result = difference(plate, cutter)
    # Result bbox should match the plate (cutters are subtractive).
    bb = bbox(result)
    assert bb.size[0] == pytest.approx(60.0, abs=0.1)
    assert bb.size[1] == pytest.approx(60.0, abs=0.1)
    assert bb.size[2] == pytest.approx(3.0, abs=0.1)


def test_hole_grid_single_row_or_col():
    """rows=1 or cols=1 produces a 1D strip — the helper degrades to
    a single linear_copy worth of holes."""
    strip = hole_grid(
        rows=1, cols=4, row_spacing=10, col_spacing=8,
        hole=cylinder(h=2, r=1),
        center=False,
    )
    bb = bbox(strip)
    assert bb.size[0] == pytest.approx(24 + 2, abs=0.1)
    assert bb.size[1] == pytest.approx(2.0, abs=0.1)


def test_hole_grid_rejects_zero_rows():
    with pytest.raises(ValidationError, match="rows"):
        hole_grid(
            rows=0, cols=2, row_spacing=10, col_spacing=10,
            hole=cylinder(h=2, r=1),
        )


def test_hole_grid_rejects_negative_spacing():
    with pytest.raises(ValidationError, match="row_spacing"):
        hole_grid(
            rows=2, cols=2, row_spacing=-5, col_spacing=10,
            hole=cylinder(h=2, r=1),
        )


def test_hole_grid_rejects_non_int_rows():
    with pytest.raises(ValidationError, match="rows"):
        hole_grid(
            rows=2.5, cols=2, row_spacing=10, col_spacing=10,
            hole=cylinder(h=2, r=1),
        )
