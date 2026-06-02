"""Print-bed layout helper: pack parts into rows, lift to bed, fit-check."""

import pytest

from scadwright import bbox, emit_str
from scadwright.composition_helpers import arrange_on_bed
from scadwright.errors import ValidationError
from scadwright.primitives import cube


def test_single_part_positioned_at_front_left_corner():
    bb = bbox(arrange_on_bed(cube(20, center=True)))
    assert bb.min == (0.0, 0.0, 0.0)
    assert bb.max == (20.0, 20.0, 20.0)


def test_two_parts_separated_by_gap():
    """Cursor advances by part X-extent + gap; second part's bbox.min[0]
    sits at first.x_extent + gap."""
    bb = bbox(arrange_on_bed(cube(10), cube(10), gap=5))
    assert bb.min == (0.0, 0.0, 0.0)
    # First cube spans x ∈ [0, 10]; gap=5 puts second at [15, 25]; total X = 25.
    assert bb.max == (25.0, 10.0, 10.0)


def test_zero_gap_packs_tight():
    bb = bbox(arrange_on_bed(cube(10), cube(10), gap=0))
    assert bb.max[0] == 20.0


def test_single_row_when_everything_fits():
    """Parts that fit within the plate width stay in one row — the simple
    layout is unchanged by row-wrapping."""
    bb = bbox(arrange_on_bed(cube(10), cube(10), cube(10), gap=5))
    # Three 10mm cubes + two 5mm gaps = 40mm wide, well under the 256 plate.
    assert bb.max == (40.0, 10.0, 10.0)


def test_part_with_negative_z_extent_lifted_to_bed():
    """A pre-halved or origin-centered part below z=0 gets lifted so its
    bbox.min[2] sits on the bed."""
    bb = bbox(arrange_on_bed(cube(20, center=True)))
    # cube(20, center=True) has z ∈ [-10, 10]; after lift, z ∈ [0, 20].
    assert bb.min[2] == 0.0
    assert bb.max[2] == 20.0


def test_lift_to_bed_disabled_preserves_z():
    bb = bbox(arrange_on_bed(cube(20, center=True), lift_to_bed=False))
    assert bb.min[2] == -10.0
    assert bb.max[2] == 10.0


def test_iterable_argument_flattens_one_level():
    """Match the CSG-arg convention: arrange_on_bed([a, b], c) treats the
    list and the trailing positional arg uniformly."""
    a = arrange_on_bed([cube(10), cube(10)], cube(10), gap=2)
    b = arrange_on_bed(cube(10), cube(10), cube(10), gap=2)
    assert emit_str(a) == emit_str(b)


def test_empty_parts_raises():
    with pytest.raises(ValidationError):
        arrange_on_bed()


# =============================================================================
# Row-wrapping: the 2D layout
# =============================================================================


def test_wraps_to_new_row_when_x_would_exceed_plate():
    """Two parts each wider than half the plate land in separate rows: the
    layout is 2D, not one overflowing line."""
    bb = bbox(
        arrange_on_bed(
            cube([100, 30, 10]), cube([100, 30, 10]),
            plate=(150, 300), gap=5,
        )
    )
    # Single row would be 205mm wide; wrapping keeps width at one part (100)
    # and stacks depth: row1 y ∈ [0, 30], row2 y ∈ [35, 65].
    assert bb.max[0] == 100.0
    assert bb.max[1] == 65.0


def test_wrap_advances_y_by_tallest_in_row():
    """A new row starts past the previous row's deepest part, not past an
    arbitrary part's depth."""
    bb = bbox(
        arrange_on_bed(
            cube([60, 50, 10]), cube([60, 20, 10]), cube([60, 30, 10]),
            plate=(150, 200), gap=5,
        )
    )
    # Row1 = [50-deep, 20-deep] (125mm wide < 150), row depth 50.
    # Row2 = [30-deep], starting at 50 + 5 = 55, so y ∈ [55, 85].
    assert bb.min[1] == 0.0
    assert bb.max[1] == 85.0


def test_part_centered_within_its_row_depth_band():
    """A shallow part sharing a row with a deeper one is centered across the
    row's depth, not flush to the row's front edge."""
    layout = arrange_on_bed(
        cube([20, 40, 10]), cube([20, 10, 10]),
        plate=(200, 200), gap=5,
    )
    deep, shallow = layout.children  # argument order preserved (no sort)
    # Deep part sets the 40mm band and touches the row front.
    assert bbox(deep).min[1] == 0.0
    assert bbox(deep).max[1] == 40.0
    # Shallow 10mm part centered in the 40mm band: (40 - 10) / 2 = 15.
    assert bbox(shallow).min[1] == 15.0
    assert bbox(shallow).max[1] == 25.0


# =============================================================================
# Fit-check
# =============================================================================


def test_assert_fit_raises_when_part_wider_than_plate():
    """A single part wider than the plate overflows X and can't be wrapped
    away."""
    with pytest.raises(ValidationError, match="overflow X"):
        arrange_on_bed(cube([300, 50, 10]), plate=(200, 200))


def test_assert_fit_raises_when_wrapped_rows_exceed_depth():
    """Parts that wrap into rows whose stacked depth crosses the plate
    overflow Y."""
    with pytest.raises(ValidationError, match="exceeds plate"):
        arrange_on_bed(
            cube([90, 100, 10]), cube([90, 100, 10]), cube([90, 100, 10]),
            plate=(200, 200), gap=5,
        )


def test_assert_fit_raises_when_y_exceeds_plate():
    with pytest.raises(ValidationError, match="exceeds plate"):
        arrange_on_bed(cube(50), gap=5, plate=(100, 30))


def test_assert_fit_disabled_lets_overflow_through():
    # A part wider than the plate; with assert_fit=False, no raise.
    bb = bbox(
        arrange_on_bed(cube([300, 50, 10]), plate=(200, 200), assert_fit=False)
    )
    assert bb.max[0] > 200  # confirm we actually overflow


def test_assert_fit_message_includes_overflow_magnitude():
    """When the layout overflows, the error names the concrete overflow
    so a user can see how much they're over by."""
    with pytest.raises(ValidationError) as exc:
        arrange_on_bed(cube(150), gap=0, plate=(100, 200))
    assert "overflow X=50" in str(exc.value)


def test_assert_fit_message_names_row_count():
    """The error reports how many rows the layout used, so the user can
    reason about the wrapped footprint."""
    with pytest.raises(ValidationError, match="across 3 rows"):
        arrange_on_bed(
            cube([90, 100, 10]), cube([90, 100, 10]),
            cube([90, 100, 10]), cube([90, 100, 10]),
            cube([90, 100, 10]),
            plate=(200, 200), gap=5,
        )


# =============================================================================
# sort
# =============================================================================


def test_sort_depth_packs_tighter_than_argument_order():
    """Alternating deep/shallow parts waste a row each in argument order;
    sort="depth" groups deep rows then shallow rows and fits."""
    parts = [
        cube([60, 50, 10]), cube([60, 10, 10]),
        cube([60, 50, 10]), cube([60, 10, 10]),
    ]
    # Argument order: two rows of [deep, shallow], each 50 deep → 105mm > 100.
    with pytest.raises(ValidationError, match="exceeds plate"):
        arrange_on_bed(*parts, plate=(150, 100), gap=5)
    # sort="depth": row of [50, 50] then row of [10, 10] → 50 + 5 + 10 = 65.
    bb = bbox(arrange_on_bed(*parts, plate=(150, 100), gap=5, sort="depth"))
    assert bb.max[1] == 65.0


def test_sort_depth_is_stable_for_equal_depths():
    """Parts of equal depth keep argument order under sort="depth", so the
    layout stays predictable."""
    layout = arrange_on_bed(
        cube([10, 30, 5]), cube([20, 30, 5]),  # equal depth, distinct width
        plate=(200, 200), gap=5, sort="depth",
    )
    first, second = layout.children
    assert bbox(first).max[0] - bbox(first).min[0] == 10.0   # argument-first
    assert bbox(second).max[0] - bbox(second).min[0] == 20.0


def test_invalid_sort_raises():
    with pytest.raises(ValidationError, match="sort"):
        arrange_on_bed(cube(10), sort="width")


# =============================================================================
# Degenerate footprint
# =============================================================================


def test_degenerate_footprint_raises():
    """A part whose extent can't be known from its tree (`surface()`) has a
    zero footprint. Laying it out would place a zero-size point at the
    origin and report a false fit, so it raises instead."""
    from scadwright.primitives import surface

    with pytest.raises(ValidationError, match="no bed footprint"):
        arrange_on_bed(surface("heightmap.png"))


def test_declared_bbox_makes_zero_footprint_part_placeable():
    """`with_bbox_from` gives the part a real footprint, so it lays out."""
    from scadwright.primitives import surface

    sized = surface("heightmap.png").with_bbox_from(cube([40, 30, 10]))
    bb = bbox(arrange_on_bed(sized))
    assert bb.max[0] == 40.0
    assert bb.max[1] == 30.0


# =============================================================================
# Misc invariants
# =============================================================================


def test_negative_gap_raises():
    with pytest.raises(ValidationError, match="non-negative"):
        arrange_on_bed(cube(10), gap=-1)


def test_zero_plate_dimension_raises():
    with pytest.raises(ValidationError, match="positive"):
        arrange_on_bed(cube(10), plate=(0, 200))
    with pytest.raises(ValidationError, match="positive"):
        arrange_on_bed(cube(10), plate=(200, -5))


def test_arrange_returns_union_node():
    """The result is a SCAD union, so it composes with the rest of the
    framework's CSG operators."""
    out = emit_str(arrange_on_bed(cube(10), cube(10)))
    assert "union()" in out


def test_arrange_with_halved_part_uses_kept_region_bbox():
    """Layout composes with the bbox-clipping behavior of halve(). A halved
    part contributes its kept region's footprint, not the original
    (pre-halve) AABB."""
    full = cube(20, center=True)              # bbox: 20×20×20
    halved = cube(20, center=True).halve([1, 0, 0])  # bbox: 10×20×20 (kept +x half)
    bb = bbox(arrange_on_bed(full, halved, gap=5))
    # full takes x ∈ [0, 20]; gap=5; halved takes x ∈ [25, 35] (10 wide, not 20).
    assert bb.max[0] == 35.0


def test_source_location_points_at_user_call_site():
    """Construction errors carry the user's call site, not framework
    internals — same convention as the rest of the helpers."""
    import inspect
    line = inspect.currentframe().f_lineno
    try:
        arrange_on_bed(cube(150), plate=(100, 100))  # this line: line + 2
    except ValidationError as exc:
        assert exc.source_location is not None
        assert exc.source_location.file.endswith("test_arrange_on_bed.py")
        assert exc.source_location.line == line + 2
    else:
        pytest.fail("expected ValidationError")


# =============================================================================
# tight_bbox-based lift: Component-with-Difference cases
# =============================================================================


def test_component_with_difference_no_override_raises_named():
    """A Component whose build tree contains Difference and doesn't
    override ``tight_bbox`` raises with the Component class name in
    the message — the layout needs the tight bbox to place parts
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
        arrange_on_bed(TruncCone())


def test_component_with_difference_override_lays_out_correctly():
    """When the author overrides ``tight_bbox``, the layout uses it.
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

    bb = bbox(arrange_on_bed(TruncCone()))
    # Lift uses the declared min[2] = 0, so the part sits on the bed
    # without floating. The KEY assertion is that we didn't raise.
    assert bb.min == (0, 0, 0)


def test_arrange_on_bed_error_lists_workarounds():
    """The error message names the three workarounds so the user
    isn't left guessing how to fix the layout."""
    from scadwright import Component
    from scadwright.boolops import difference

    class Bad(Component):
        def build(self):
            return difference(cube(20), cube(10).translate([5, 5, 15]))

    with pytest.raises(ValidationError) as exc:
        arrange_on_bed(Bad())
    msg = str(exc.value)
    assert "tight_bbox" in msg
    assert "halve" in msg
    assert "lift_to_bed=False" in msg


def test_halved_part_uses_intersection_path_no_override_needed():
    """Halve uses Intersection internally, which TightBBoxVisitor
    handles natively. No override needed for halved geometry."""
    halved = cube(20, center=True).halve([1, 0, 0])
    bb = bbox(arrange_on_bed(halved))
    # Halve keeps +x: x ∈ [0, 10]. After lift (z from -10 to 10) and
    # X-shift to 0: x ∈ [0, 10], z ∈ [0, 20].
    assert bb.min == (0, 0, 0)
    assert bb.max[0] == 10
    assert bb.max[2] == 20
