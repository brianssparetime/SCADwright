"""Tests for through()'s world-axis auto-detect heuristic.

The auto-detector picks the cut axis by counting how many of the cutter's
faces are flush with the parent's on each axis. The axis with the most
flush faces wins. A tie at the maximum count raises — the user has to
disambiguate with axis=.

The local-axis path (rotated cutters) is covered in test_through_rotated.py.
"""

import pytest

from scadwright import emit_str
from scadwright.boolops import difference
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder


def test_auto_detect_drill_through_plate_picks_z():
    """Canonical case: cylinder narrower than plate, same height. z has
    2 flush faces (top and bottom), x and y have 0. Picks z."""
    plate = cube([20, 20, 3])
    drill = cylinder(h=3, r=1.5).translate([10, 10, 0])
    scad = emit_str(difference(plate, drill.through(plate)))
    # The z-extension produces translate([0, 0, -eps]) and scale([1, 1, ...]).
    assert "translate([0, 0, -" in scad
    assert "scale([1, 1, " in scad


def test_auto_detect_filletmask_pattern_picks_edge_axis():
    """A cylinder centered at a corner with radius equal to the block's
    lateral half-extent — the FilletMask pattern. The cylinder is wider
    than the block in x and y by design (tangent to the outer faces),
    but its z extent matches the block exactly. z has 2 flush faces;
    x and y have 1 each. The detector picks z, not the spans-most x."""
    block = cube([2, 2, 3])
    cutter = cylinder(h=3, r=2).translate([2, 2, 0])
    scad = emit_str(difference(block, cutter.through(block)))
    # Should extend along z (the edge axis), NOT x or y. The scale wrap
    # ends up on the z component: scale([1, 1, k]) for some k > 1.
    # The buggy old heuristic would emit scale([k, 1, 1]).
    assert "scale([1, 1, " in scad
    assert "scale([1." not in scad.replace("scale([1, 1, ", "")


def test_auto_detect_tied_raises_with_actionable_message():
    """A cutter whose bbox exactly matches the parent's in two axes —
    no unique 'most-flush' axis. Raises and tells the user to pass
    axis= and mentions the tangency case."""
    parent = cube([10, 10, 10])
    # Same size in x and y, slightly smaller in z. Two axes tie at 2.
    overlap = cube([10, 10, 5]).up(2)
    with pytest.raises(ValidationError) as exc:
        difference(parent, overlap.through(parent))
    msg = str(exc.value)
    assert "flush" in msg
    assert "more than one axis" in msg
    assert "axis='x'" in msg and "axis='y'" in msg and "axis='z'" in msg
    # The error should also hint at the "intentional tangency" case so a
    # user who hit the fillet-shaped trap knows what to do.
    assert "tangent" in msg


def test_auto_detect_partial_penetration_picks_the_flush_axis():
    """A cutter flush on only one side (counterbore-style: bottom is
    flush, top extends above). One axis with 1 flush face; others 0.
    Picks the flush axis."""
    plate = cube([20, 20, 3])
    # Cutter same x,y as plate's drill region, taller than the plate
    # (top extends above, bottom is flush with plate bottom).
    cutter = cylinder(h=5, r=1.5).translate([10, 10, 0])
    scad = emit_str(difference(plate, cutter.through(plate)))
    # The min-z face is flush; the cutter gets extended at -z only.
    # Result: translate([0, 0, -eps]) but no top extension (max not flush).
    assert "translate([0, 0, -" in scad


def test_intrinsic_axis_routes_tilted_cylinder_to_local_path():
    """A tilted cylinder cutter (off-axis rotation) calling .through()
    without an explicit axis= flows through the local-axis path via the
    cylinder's intrinsic cut direction (local-z). The output should
    contain a leaf-level translate(-eps in z) rather than raising."""
    plate = cube([20, 20, 2])
    drill = (
        cylinder(h=2, r=2)
        .rotate([0, 30, 0])  # non-axis-permuting → can't go world-axis
        .translate([10, 10, 0])
    )
    result = drill.through(plate)
    scad = emit_str(result)
    # Local-axis dispatch wraps the leaf in a translate/scale inside
    # the rotate chain; emitted SCAD keeps the original rotate.
    assert "rotate" in scad
    # And the bbox grew along the cylinder's local-z direction.
    from scadwright.bbox import bbox as _bbox
    assert _bbox(result).size != _bbox(drill).size


def test_intrinsic_axis_doesnt_fire_on_unrotated_cutter():
    """An axis-aligned cylinder cutter still goes through the
    world-axis path — the intrinsic-axis dispatch is reserved for
    rotated cutters where bbox detection can't find coincidence."""
    plate = cube([20, 20, 3])
    drill = cylinder(h=3, r=1.5).translate([10, 10, 0])
    result = drill.through(plate)
    scad = emit_str(result)
    # World-axis path emits a top-level translate/scale on the WHOLE
    # cutter (including its placement translate), not at the leaf.
    # Sanity: there's a scale wrap somewhere.
    assert "scale(" in scad


def test_auto_detect_cutter_inside_parent_is_noop_no_raise():
    """When no face is flush (cutter sits fully inside the parent), the
    fallback rule picks an axis but nothing gets extended — the cutter
    passes through unchanged. Doesn't raise."""
    parent = cube([20, 20, 20])
    cutter = cylinder(h=4, r=1).translate([10, 10, 5])  # fully inside
    # Should not raise.
    result = cutter.through(parent)
    # The result is the cutter unchanged (no Scale/Translate wrap added,
    # since no face was flush to extend).
    assert result is cutter
