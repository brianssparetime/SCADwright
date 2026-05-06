"""Print-bed layout helper: lay parts left-to-right, lift to bed, fit-check."""

import pytest

from scadwright import bbox, emit_str
from scadwright.composition_helpers import pack_on_bed
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder, sphere


def test_single_part_positioned_at_front_left_corner():
    bb = bbox(pack_on_bed(cube(20, center=True)))
    assert bb.min == (0.0, 0.0, 0.0)
    assert bb.max == (20.0, 20.0, 20.0)


def test_two_parts_separated_by_gap():
    """Cursor advances by part X-extent + gap; second part's bbox.min[0]
    sits at first.x_extent + gap."""
    bb = bbox(pack_on_bed(cube(10), cube(10), gap=5))
    assert bb.min == (0.0, 0.0, 0.0)
    # First cube spans x ∈ [0, 10]; gap=5 puts second at [15, 25]; total X = 25.
    assert bb.max == (25.0, 10.0, 10.0)


def test_zero_gap_packs_tight():
    bb = bbox(pack_on_bed(cube(10), cube(10), gap=0))
    assert bb.max[0] == 20.0


def test_part_with_negative_z_extent_lifted_to_bed():
    """A pre-halved or origin-centered part below z=0 gets lifted so its
    bbox.min[2] sits on the bed."""
    bb = bbox(pack_on_bed(cube(20, center=True)))
    # cube(20, center=True) has z ∈ [-10, 10]; after lift, z ∈ [0, 20].
    assert bb.min[2] == 0.0
    assert bb.max[2] == 20.0


def test_lift_to_bed_disabled_preserves_z():
    bb = bbox(pack_on_bed(cube(20, center=True), lift_to_bed=False))
    assert bb.min[2] == -10.0
    assert bb.max[2] == 10.0


def test_iterable_argument_flattens_one_level():
    """Match the CSG-arg convention: pack_on_bed([a, b], c) treats the
    list and the trailing positional arg uniformly."""
    a = pack_on_bed([cube(10), cube(10)], cube(10), gap=2)
    b = pack_on_bed(cube(10), cube(10), cube(10), gap=2)
    assert emit_str(a) == emit_str(b)


def test_empty_parts_raises():
    with pytest.raises(ValidationError):
        pack_on_bed()


def test_assert_fit_raises_when_x_exceeds_plate():
    with pytest.raises(ValidationError, match="exceeds plate"):
        pack_on_bed(cube(100), cube(100), cube(100), gap=5, plate=(200, 200))


def test_assert_fit_raises_when_y_exceeds_plate():
    with pytest.raises(ValidationError, match="exceeds plate"):
        pack_on_bed(cube(50), gap=5, plate=(100, 30))


def test_assert_fit_disabled_lets_overflow_through():
    # Same parts as the X-overflow test; with assert_fit=False, no raise.
    bb = bbox(
        pack_on_bed(cube(100), cube(100), cube(100),
                    gap=5, plate=(200, 200), assert_fit=False)
    )
    assert bb.max[0] > 200  # confirm we actually overflow


def test_negative_gap_raises():
    with pytest.raises(ValidationError, match="non-negative"):
        pack_on_bed(cube(10), gap=-1)


def test_zero_plate_dimension_raises():
    with pytest.raises(ValidationError, match="positive"):
        pack_on_bed(cube(10), plate=(0, 200))
    with pytest.raises(ValidationError, match="positive"):
        pack_on_bed(cube(10), plate=(200, -5))


def test_pack_returns_union_node():
    """The result is a SCAD union, so it composes with the rest of the
    framework's CSG operators."""
    out = emit_str(pack_on_bed(cube(10), cube(10)))
    assert "union()" in out


def test_pack_with_halved_part_uses_kept_region_bbox():
    """Pack composes with the bbox-clipping behavior of halve(). A halved
    part contributes its kept region's footprint to the layout, not the
    original (pre-halve) AABB."""
    full = cube(20, center=True)              # bbox: 20×20×20
    halved = cube(20, center=True).halve([1, 0, 0])  # bbox: 10×20×20 (kept +x half)
    bb = bbox(pack_on_bed(full, halved, gap=5))
    # full takes x ∈ [0, 20]; gap=5; halved takes x ∈ [25, 35] (10 wide, not 20).
    assert bb.max[0] == 35.0


def test_assert_fit_message_includes_overflow_magnitude():
    """When the layout overflows, the error names the concrete overflow
    so a user can see how much they're over by."""
    with pytest.raises(ValidationError) as exc:
        pack_on_bed(cube(150), gap=0, plate=(100, 200))
    assert "overflow X=50" in str(exc.value)


def test_source_location_points_at_user_call_site():
    """Construction errors carry the user's call site, not framework
    internals — same convention as the rest of the helpers."""
    import inspect
    line = inspect.currentframe().f_lineno
    try:
        pack_on_bed(cube(150), plate=(100, 100))  # this line: line + 2
    except ValidationError as exc:
        assert exc.source_location is not None
        assert exc.source_location.file.endswith("test_pack_on_bed.py")
        assert exc.source_location.line == line + 2
    else:
        pytest.fail("expected ValidationError")


# =============================================================================
# tight_bbox-based lift: Component-with-Difference cases
# =============================================================================


def test_component_with_difference_no_override_raises_named():
    """A Component whose build tree contains Difference and doesn't
    override ``tight_bbox`` raises with the Component class name in
    the message — pack_on_bed needs the tight bbox to lay parts out
    correctly, and it tells the user exactly where to fix it."""
    from scadwright import Component
    from scadwright.boolops import difference

    class TruncCone(Component):
        def build(self):
            return difference(
                cube([20, 20, 10]),
                cube([20, 20, 5]).translate([0, 0, 8]),
            )

    with pytest.raises(ValidationError, match="TruncCone"):
        pack_on_bed(TruncCone())


def test_component_with_difference_override_lays_out_correctly():
    """When the author overrides ``tight_bbox``, pack_on_bed uses it.
    The lift puts the declared bottom on the bed."""
    from scadwright import BBox, Component
    from scadwright.boolops import difference

    class TruncCone(Component):
        def build(self):
            return difference(
                cube([20, 20, 10]),
                cube([20, 20, 5]).translate([0, 0, 8]),
            )

        def tight_bbox(self):
            # Author declares: chop reduces height to 8.
            return BBox(min=(0, 0, 0), max=(20, 20, 8))

    bb = bbox(pack_on_bed(TruncCone()))
    # Lift uses the declared min[2] = 0, so the part sits on the bed
    # without floating. Build-tree bbox would have said max[2] = 10
    # (conservative, ignoring the chop), but tight_bbox says 8 — and
    # the lift uses the declared bottom which IS 0, so result max[2]
    # = 8 (declared) since pack_on_bed wraps in Translate by 0.
    # bbox(pack_on_bed) reads the conservative outer bbox, not tight,
    # so it sees the cube's full 10. The KEY assertion is that we
    # didn't raise.
    assert bb.min == (0, 0, 0)


def test_pack_on_bed_error_lists_workarounds():
    """The error message names the three workarounds so the user
    isn't left guessing how to fix the layout."""
    from scadwright import Component
    from scadwright.boolops import difference

    class Bad(Component):
        def build(self):
            return difference(cube(20), cube(10).translate([5, 5, 15]))

    with pytest.raises(ValidationError) as exc:
        pack_on_bed(Bad())
    msg = str(exc.value)
    assert "tight_bbox" in msg
    assert "halve" in msg
    assert "lift_to_bed=False" in msg


def test_halved_part_uses_intersection_path_no_override_needed():
    """Halve uses Intersection internally, which TightBBoxVisitor
    handles natively. No override needed for halved geometry."""
    halved = cube(20, center=True).halve([1, 0, 0])
    bb = bbox(pack_on_bed(halved))
    # Halve keeps +x: x ∈ [0, 10]. After lift (z from -10 to 10) and
    # X-shift to 0: x ∈ [0, 10], z ∈ [0, 20].
    assert bb.min == (0, 0, 0)
    assert bb.max[0] == 10
    assert bb.max[2] == 20
