"""Tests for the symmetric-fuse side-selection heuristic.

When ``boolops.fuse(a, b, ...)`` runs the smart cascade and both sides
have a parametric ``fuse_extend`` lever, ``_pick_simpler_extension``
picks one side. The ranking is:

1. Exactness — Cube and true-cylinder caps extend without changing
   geometry elsewhere. Cone caps and linear_extrude end-caps drift the
   slope or profile by ``eps/h``.
2. Within the same exactness tier, prefer the leaf form over a
   Translate-wrapped form (cleaner SCAD output).
"""

import pytest

from scadwright.ast.placement import _extension_is_exact, _pick_simpler_extension
from scadwright.extrusions import linear_extrude
from scadwright.primitives import circle, cube, cylinder


# --- _extension_is_exact classifier ---


def test_cube_extension_is_exact():
    assert _extension_is_exact(cube([10, 10, 10])) is True


def test_true_cylinder_extension_is_exact():
    assert _extension_is_exact(cylinder(h=10, r=5)) is True


def test_cone_cylinder_extension_is_inexact():
    """r1 != r2 — bumping h changes the slope."""
    assert _extension_is_exact(cylinder(h=10, r1=5, r2=8)) is False


def test_linear_extrude_extension_is_inexact():
    assert _extension_is_exact(linear_extrude(circle(r=5), height=10)) is False


def test_extension_is_exact_recurses_through_transforms():
    cube_translated = cube([10, 10, 10]).up(5)
    assert _extension_is_exact(cube_translated) is True

    cube_rotated = cube([10, 10, 10]).rotate([0, 90, 0])
    assert _extension_is_exact(cube_rotated) is True

    cone_translated = cylinder(h=10, r1=5, r2=8).up(5)
    assert _extension_is_exact(cone_translated) is False


# --- _pick_simpler_extension picks by exactness first ---


def test_pick_exact_over_inexact_a():
    """Cube (a) vs cone (b) — cube wins."""
    a, b = cube([10, 10, 10]), cylinder(h=10, r1=5, r2=8)
    extended_a, extended_b = "fake_a", "fake_b"  # treat as non-None tokens
    assert _pick_simpler_extension(a, b, extended_a, extended_b) == "a"


def test_pick_exact_over_inexact_b():
    """Cone (a) vs cube (b) — cube wins (b)."""
    a, b = cylinder(h=10, r1=5, r2=8), cube([10, 10, 10])
    extended_a, extended_b = "fake_a", "fake_b"
    assert _pick_simpler_extension(a, b, extended_a, extended_b) == "b"


def test_pick_exact_over_linear_extrude():
    a, b = cube([10, 10, 10]), linear_extrude(circle(r=5), height=10)
    extended_a, extended_b = "fake_a", "fake_b"
    assert _pick_simpler_extension(a, b, extended_a, extended_b) == "a"


def test_pick_among_two_exact_uses_leaf_tiebreaker():
    """Both exact (cube vs true cylinder) — leaf tiebreaker decides.
    Both extended results are leaves → fall through to default 'a'."""
    from scadwright.ast.primitives import Cube, Cylinder
    a, b = cube([10, 10, 10]), cylinder(h=10, r=5)
    extended_a = Cube(size=(10.01, 10, 10), center=(False, False, False))
    extended_b = Cylinder(h=10.01, r1=5, r2=5, center=False)
    assert _pick_simpler_extension(a, b, extended_a, extended_b) == "a"


def test_pick_leaf_over_wrapped_within_same_tier():
    """Both exact, but extended_a is wrapped in Translate (non-leaf
    SCAD output) and extended_b is a leaf — pick b."""
    from scadwright.ast.primitives import Cylinder
    from scadwright.ast.transforms import Translate
    a, b = cube([10, 10, 10]), cylinder(h=10, r=5)
    extended_a_leaf = "leaf"  # surrogate
    extended_a = Translate(v=(0, 0, -0.005), child=extended_a_leaf, source_location=None)
    extended_b = Cylinder(h=10.01, r1=5, r2=5, center=False)
    assert _pick_simpler_extension(a, b, extended_a, extended_b) == "b"


def test_pick_only_qualified_side():
    a, b = cube([10, 10, 10]), cube([5, 5, 5])
    assert _pick_simpler_extension(a, b, "ext_a", None) == "a"
    assert _pick_simpler_extension(a, b, None, "ext_b") == "b"


def test_pick_neither_qualified():
    a, b = cube([10, 10, 10]), cube([5, 5, 5])
    assert _pick_simpler_extension(a, b, None, None) is None


# --- end-to-end via boolops.fuse — the right side actually gets extended ---


def test_fuse_picks_cube_over_cone_cylinder():
    """fuse(cone, cube) with planar caps — the cube side should be the
    extended one (its math is exact). Verify by checking the emitted
    Translate's child contains the bumped cube primitive, not the cone."""
    from scadwright.boolops import fuse
    from scadwright.ast.primitives import Cube, Cylinder
    from scadwright.ast.transforms import Translate

    cone = cylinder(h=20, r1=5, r2=8)
    plate = cube([20, 20, 4])
    # cone.top is planar; plate.bottom is planar. Both qualify for Tier 1.
    # Explicit bond="overlap" keeps the directed grow + symmetric picker; bare
    # fuse would slab here (the plate isn't contained in the cone's cap disc).
    result = fuse(cone, plate, on="bottom", using_anchor="top", bond="overlap")
    # Result is a Union of (placed_a, b_or_extended_b). With the new
    # ranking, b (cube) is the extended side; a (cone) gets only a
    # Translate to coincide-anchor positions.
    children = list(result.children)
    # The extended side (cube) is non-None in one of the children;
    # navigate to find a Cube whose size differs from (20, 20, 4).
    def find_extended_cube(node, depth=8):
        if depth == 0:
            return None
        if isinstance(node, Cube) and node.size != (20.0, 20.0, 4.0):
            return node
        for attr in ("child", "children"):
            v = getattr(node, attr, None)
            if v is None:
                continue
            if isinstance(v, tuple):
                for c in v:
                    found = find_extended_cube(c, depth - 1)
                    if found is not None:
                        return found
            else:
                found = find_extended_cube(v, depth - 1)
                if found is not None:
                    return found
        return None
    bumped_cube = find_extended_cube(result)
    assert bumped_cube is not None, (
        "Expected a bumped cube in the result tree (extended side); "
        "the new ranking should pick cube over cone."
    )
    # The cube's size on the contact axis (z) should be 4 + eps = 4.01.
    assert bumped_cube.size[2] == pytest.approx(4.01)
