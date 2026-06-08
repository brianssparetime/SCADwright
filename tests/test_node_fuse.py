"""End-to-end tests for ``Node.fuse(host)``.

Covers the full flow: matching, eps application, alignment, error
matrix from the spec. The standalone peer ``boolops.fuse(a, b)``
form is tested separately in ``test_fuse_peer.py``.
"""

from __future__ import annotations

import pytest

from scadwright import Component, anchor, bbox
from scadwright.ast.csg import Union
from scadwright.ast.transforms import Translate
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder, sphere
from scadwright.shapes import Funnel, Tube


# --- Planar contact: Cube on Cube (already positioned) ---


def test_planar_cube_on_cube_returns_union_with_extended_self():
    """Two coincident same-sized cubes: peg's bottom face matches
    plate's top face. fuse_extend bumps peg's size[2]; no alignment
    translate (positions already coincident)."""
    plate = cube([10, 10, 2], center=True)
    peg = cube([10, 10, 5], center=True).up(3.5)
    result = peg.fuse(plate)
    assert isinstance(result, Union)
    # The bbox should reach down to plate's top with eps overlap on peg's bottom.
    bb = bbox(result)
    assert bb.min[2] == pytest.approx(-1.0)  # plate's bottom
    assert bb.max[2] == pytest.approx(6.0)   # peg's top


# --- Curved (concentric cylindrical): Tube inside Tube — the lens-housing pattern ---


def test_concentric_tubes_fuses_via_host_inner_extension():
    """Holder (outer, inner=False) inside Barrel (inner, inner=True).
    Holder is self with no custom fuse_extend; inner=False side tried
    first but ElementHolder-shaped Components fall through (Tube DOES
    have outer fuse_extend, so for this synthetic case it'd extend self).
    Here both are Tubes; the outer wall of holder grows."""
    barrel = Tube(h=50, od=20, id=10)
    holder = Tube(h=8, od=10, id=4).up(20)
    result = holder.fuse(barrel)
    assert isinstance(result, Union)
    # Holder's od grew by 2*eps; barrel unchanged. Verify holder bbox.
    children = result.children
    # The first child is the extended holder (with .up(20)). Verify it's
    # still Translate-wrapped (the placement is preserved).
    assert any(isinstance(c, Translate) for c in children)


# --- prefers_shift_at_anchor honored on planar ---


def test_prefers_shift_at_anchor_routes_to_shift_branch():
    """A FilletRing on a Tube top has prefers_shift_at_anchor=True at
    its bottom anchor — the fuse path should pick the shift branch
    rather than cross-section overlap."""
    from scadwright.shapes import FilletRing
    tube = Tube(h=10, od=10, id=6)
    ring = FilletRing(id=6, od=10, base_angle=60).up(10)
    result = ring.fuse(tube)
    assert isinstance(result, Union)


# --- Errors: zero matches ---


def test_fuse_zero_matches_with_planar_pair_misaligned_raises():
    """Two cubes that don't touch. Zero matches → raise listing the
    declared anchors."""
    a = cube([5, 5, 5])
    b = cube([5, 5, 5]).up(20)
    with pytest.raises(ValidationError, match="no coincident-surface contact"):
        a.fuse(b)


def test_fuse_zero_matches_with_bridge_hint_points_at_attach_bridge():
    """A planar peg positioned against a curved host (cylindrical
    wall) has no fuse match; the error names the bridge alternative.

    The peg is offset to put its ``lside`` face center exactly on the
    tube's outer wall — the proximity gate in
    ``cross_kind_bridge_candidates`` only fires the bridge hint when
    the planar face is actually on the curved surface.
    """
    peg = cube([2, 2, 5], center=True).right(11)  # lside at (10, 0, 0)
    tube = Tube(h=20, od=20, id=10)  # outer wall radius 10, axial 0..20
    with pytest.raises(ValidationError, match="bridge case"):
        peg.fuse(tube)


def test_fuse_zero_matches_no_proximity_suppresses_bridge_hint():
    """Two shapes that don't touch — a cube in the middle of the bore
    with no face on either wall — should not get the bridge hint.
    The proximity gate keeps the diagnostic honest.
    """
    peg = cube([2, 2, 5])  # default position; sits in the bore, no face on a wall
    tube = Tube(h=20, od=20, id=10)
    with pytest.raises(ValidationError) as excinfo:
        peg.fuse(tube)
    assert "bridge case" not in str(excinfo.value)


def test_fuse_zero_matches_curved_near_miss_reports_inner_flag():
    """A holder and a section with matching radii but both inner=False.
    The section is offset in z so the axial extents don't overlap
    (preventing same_side_wall_candidates from firing). The error
    should name the curved near-miss with the specific rule that
    failed."""
    from scadwright.component.anchors import anchor as _anchor

    class Section(Component):
        equations = "h, od, thk > 0"
        outer_wall = _anchor(
            at="(od / 2), 0, h / 2",
            normal=(1.0, 0.0, 0.0),
            kind="cylindrical",
            surface_params={
                "axis": (0.0, 0.0, 1.0),
                "radius": "od / 2",
                "length": "h",
            },
        )
        def build(self):
            return Tube(h=self.h, od=self.od, id=self.od - 2 * self.thk)

    class Holder(Component):
        equations = "h, od, thk > 0"
        outer_wall = _anchor(
            at="(od / 2), 0, h / 2",
            normal=(1.0, 0.0, 0.0),
            kind="cylindrical",
            surface_params={
                "axis": (0.0, 0.0, 1.0),
                "radius": "od / 2",
                "length": "h",
            },
        )
        def build(self):
            return Tube(h=self.h, od=self.od, id=self.od - 2 * self.thk)

    section = Section(h=20, od=20, thk=2)
    holder = Holder(h=5, od=20, thk=1).up(30)
    with pytest.raises(ValidationError) as excinfo:
        holder.fuse(section)
    msg = str(excinfo.value)
    assert "Curved near-miss" in msg
    assert "inner=" in msg


def test_fuse_zero_matches_planar_near_miss_suggests_attach_fuse():
    """An off-center peg sitting on a plate: the planes coincide, but
    the named face-center positions don't match. The zero-match error
    should flag the near-miss and suggest ``attach(host, fuse=True)``.
    """
    plate = cube([20, 20, 2], center=True)
    peg = cube([5, 5, 8], center=True).right(5).up(5)  # bottom at z=1 = plate top
    with pytest.raises(ValidationError) as excinfo:
        peg.fuse(plate)
    msg = str(excinfo.value)
    assert "Near-miss" in msg
    assert "attach(host, fuse=True)" in msg


# --- Scale-style wrapper hint in the no-lever error ---


def test_fuse_scale_wrapped_curved_contact_error_names_wrapper():
    """When self is wrapped in Scale (or Resize / MultMatrix), the
    curved-overlap dispatcher can't recurse fuse_extend. The error
    message should name the wrapper and point at rebuilding."""
    from scadwright.ast.transforms import Scale
    holder = Tube(h=8, od=10, id=4).up(20)
    barrel = Tube(h=50, od=20, id=10)
    # Wrap holder in Scale; the underlying Tube lever becomes
    # unreachable through the Scale wrapper.
    scaled_holder = Scale(factor=(1.0, 1.0, 1.0), child=holder)
    # Concentric match still finds host and self anchors; host (Tube)
    # has a lever, so this would actually succeed via the host. Build
    # a case where both sides need recursion: also wrap barrel in
    # Scale so neither side has a reachable lever.
    scaled_barrel = Scale(factor=(1.0, 1.0, 1.0), child=barrel)
    with pytest.raises(ValidationError, match="wrapped in Scale"):
        scaled_holder.fuse(scaled_barrel)


# --- Errors: matched contact but no extension lever ---


def test_fuse_matched_curved_but_no_extender_raises():
    """A custom Component with a cylindrical anchor against another
    custom Component with a matching cylindrical anchor: matching
    succeeds but neither side overrides fuse_extend → dispatch
    raises naming both classes."""
    from scadwright.anchor import Anchor

    class HostCyl(Component):
        equations = "r, h > 0"
        inner_wall = anchor(
            at="r, 0, h/2",
            normal=(-1, 0, 0),
            kind="cylindrical",
            surface_params={
                "axis": (0.0, 0.0, 1.0),
                "radius": "r",
                "length": "h",
                "inner": True,
            },
        )

        def build(self):
            return cube([self.r * 2, self.r * 2, self.h])

    class HolderCyl(Component):
        equations = "r, h > 0"
        outer_wall = anchor(
            at="r, 0, h/2",
            normal=(1, 0, 0),
            kind="cylindrical",
            surface_params={
                "axis": (0.0, 0.0, 1.0),
                "radius": "r",
                "length": "h",
            },
        )

        def build(self):
            return cube([self.r * 2, self.r * 2, self.h])

    host = HostCyl(r=5, h=20)
    holder = HolderCyl(r=5, h=10).up(5)
    with pytest.raises(ValidationError, match="neither side has a fuse_extend"):
        holder.fuse(host)


# --- Errors: multiple matches ---


def test_fuse_multiple_matches_raises_with_candidates():
    """Two genuinely distinct coincident surfaces (different planes) between
    self and host. The pairwise form extends one side, so it can't fuse both
    and raises for disambiguation."""
    a = (
        cube([10, 10, 10])
        .with_anchor("p_top", at=(5, 5, 10), normal=(0, 0, 1))
        .with_anchor("p_side", at=(10, 5, 5), normal=(1, 0, 0))
    )
    b = (
        cube([10, 10, 10])
        .with_anchor("p_top", at=(5, 5, 10), normal=(0, 0, -1))
        .with_anchor("p_side", at=(10, 5, 5), normal=(-1, 0, 0))
    )
    with pytest.raises(ValidationError, match="multiple coincident-surface contacts"):
        a.fuse(b)


def test_fuse_redundant_same_surface_anchor_does_not_raise():
    """A second anchor on the same wall as outer_wall describes one surface,
    not two contacts, so it fuses rather than raising as an ambiguity."""
    barrel = Tube(h=20, od=20, id=10)
    holder = (
        Tube(h=8, od=10, id=4)
        .up(10)
        .with_anchor(
            "alt_outer",
            at=(5, 0, 13), normal=(1, 0, 0),
            kind="cylindrical",
            axis=(0, 0, 1), radius=5.0, length=2.0, inner=False,
        )
    )
    assert isinstance(holder.fuse(barrel), Union)


# --- Errors: explicit override with incompatible kinds ---


def test_fuse_explicit_kinds_mismatch_raises():
    """on= names a planar anchor; from_anchor= names a cylindrical one.
    Match-pair returns None → raise."""
    peg = cube([2, 2, 5])
    tube = Tube(h=20, od=20, id=10)
    with pytest.raises(ValidationError, match="do not describe a coincident surface"):
        peg.fuse(tube, on="outer_wall", from_anchor="bottom")


def test_fuse_explicit_kinds_mismatch_planar_self_curved_host_suggests_bridge():
    """When self anchor is planar and host is curved, the diagnostic
    names this as a bridge case and suggests attach(bridge=True)."""
    peg = cube([2, 2, 5])
    tube = Tube(h=20, od=20, id=10)
    with pytest.raises(ValidationError) as excinfo:
        peg.fuse(tube, on="outer_wall", from_anchor="bottom")
    msg = str(excinfo.value)
    assert "bridge case" in msg
    assert "bridge=True" in msg


def test_fuse_explicit_axial_extent_mismatch_names_spans():
    """Holder above the barrel's axial range: axes coincide, radii
    match, inner flags compat, but axial extents don't overlap. The
    diagnostic should call out the axial-extent failure and show the
    two spans."""
    holder = Tube(h=8, od=10, id=4).up(100)
    barrel = Tube(h=50, od=20, id=10)
    with pytest.raises(ValidationError) as excinfo:
        holder.fuse(barrel, on="inner_wall", from_anchor="outer_wall")
    msg = str(excinfo.value)
    assert "axial extents don't overlap" in msg


def test_fuse_explicit_planar_near_miss_suggests_attach_fuse():
    """Explicit form: planes coincide but positions differ.
    Diagnostic should suggest attach(host, fuse=True)."""
    plate = cube([20, 20, 2], center=True)
    peg = cube([5, 5, 8], center=True).right(5).up(5)
    with pytest.raises(ValidationError) as excinfo:
        peg.fuse(plate, on="top", from_anchor="bottom")
    msg = str(excinfo.value)
    assert "planar positions don't coincide" in msg
    assert "attach(host, fuse=True)" in msg


def test_fuse_explicit_inner_flag_mismatch_names_rule():
    """Two cylindrical anchors with inner=False on **different**
    surfaces: the inner-flag rule message fires. (Same-surface case
    is covered by
    test_fuse_explicit_same_side_wall_suggests_union below.)
    """
    # Synthetic outer anchor at a different radius from the host tube,
    # so they fail both the inner-flag rule and the radius check.
    a = Tube(h=20, od=10, id=4).with_anchor(
        "synth_outer", at=(7, 0, 10), normal=(1, 0, 0),
        kind="cylindrical",
        axis=(0, 0, 1), radius=7.0, length=20.0, inner=False,
    )
    b = Tube(h=20, od=10, id=4)  # outer_wall at radius 5
    with pytest.raises(ValidationError) as excinfo:
        a.fuse(b, on="outer_wall", from_anchor="synth_outer")
    msg = str(excinfo.value)
    assert "inner=False" in msg
    assert "inner=True (concave/bore side)" in msg


# --- Errors: explicit anchor lookup ---


def test_fuse_unknown_host_anchor_raises():
    a = cube([5, 5, 5])
    b = cube([5, 5, 5])
    with pytest.raises(ValidationError, match="anchor"):
        a.fuse(b, on="bogus_anchor")


def test_fuse_unknown_self_anchor_raises():
    a = cube([5, 5, 5])
    b = cube([5, 5, 5])
    with pytest.raises(ValidationError, match="anchor"):
        a.fuse(b, from_anchor="bogus_anchor")


# --- Explicit overrides: positive paths ---


def test_fuse_with_explicit_on_disambiguates():
    """Two stacked cubes with coincident contact faces, fused via
    explicit on= / from_anchor= naming."""
    b = cube([10, 10, 10], center=True)  # bbox z=-5..5
    a = cube([10, 10, 10], center=True).up(10)  # bbox z=5..15; bottom at z=5 == b.top
    result = a.fuse(b, on="top", from_anchor="bottom")
    assert isinstance(result, Union)


# --- Error prefix from cross-section validation reads "fuse:" not "cross-section fuse:" ---


def test_node_fuse_cone_apex_error_has_fuse_prefix():
    """When cross_section_extend raises (e.g., cone-apex degeneracy),
    the error must read 'fuse:' to match the user's actual call, not
    leak the internal 'cross-section fuse:' prefix."""
    cone = cylinder(h=10, r1=5, r2=0)  # apex at z=10
    plate = cube([10, 10, 2], center=True).up(11)  # bottom face at z=10
    with pytest.raises(ValidationError, match=r"^fuse:.*cone apex"):
        cone.fuse(plate)


# --- disable_eps_fuse() integration ---


def test_fuse_disable_eps_skips_extension():
    """Inside disable_eps_fuse(), no fuse_extend is called; the result
    is union(self, host) with exact contact."""
    from scadwright.api.fuse_mode import disable_eps_fuse
    barrel = Tube(h=50, od=20, id=10)
    holder = Tube(h=8, od=10, id=4).up(20)
    with disable_eps_fuse():
        result = holder.fuse(barrel)
    assert isinstance(result, Union)
    # Holder's od should be unchanged (no extension).
    # The result's children should be just (holder_with_up, barrel).
    assert len(result.children) == 2


def test_fuse_disable_eps_still_raises_on_no_match():
    """Matching still runs under disable_eps_fuse; bad call still raises."""
    from scadwright.api.fuse_mode import disable_eps_fuse
    a = cube([5, 5, 5])
    b = cube([5, 5, 5]).up(20)
    with disable_eps_fuse():
        with pytest.raises(ValidationError, match="no coincident-surface contact"):
            a.fuse(b)


# --- Errors: same-side wall (telescoping / coincident surfaces) ---


def test_fuse_zero_matches_telescoping_tubes_suggests_union():
    """Two same-OD tubes overlapping axially: their outer walls
    describe the same cylindrical surface from the same side. fuse
    rightly rejects (compatible_inner_flags requires one True one
    False); the error should point at plain union()."""
    lower = Tube(h=20, od=20, id=10)
    upper = Tube(h=20, od=20, id=10).up(10)  # axially overlaps lower
    with pytest.raises(ValidationError) as excinfo:
        upper.fuse(lower)
    msg = str(excinfo.value)
    assert "Same surface" in msg
    assert "union(self, host)" in msg
    # The bridge hint should be suppressed when same-side fires.
    assert "bridge case" not in msg


def test_fuse_zero_matches_telescoping_same_id_bores_suggests_union():
    """Two same-ID tubes overlapping axially: their inner walls
    describe the same bore surface from the same side. Same case,
    inner=True flavor."""
    a = Tube(h=20, od=20, id=10)
    b = Tube(h=20, od=20, id=10).up(10)
    with pytest.raises(ValidationError) as excinfo:
        b.fuse(a)
    msg = str(excinfo.value)
    assert "Same surface" in msg
    assert "union(self, host)" in msg


def test_fuse_explicit_same_side_wall_suggests_union():
    """Explicit form: user names two anchors that describe the same
    cylindrical surface from the same side. Diagnostic upgrades from
    the bare 'both inner=False' rule statement to the union()
    suggestion."""
    lower = Tube(h=20, od=20, id=10)
    upper = Tube(h=20, od=20, id=10).up(10)
    with pytest.raises(ValidationError) as excinfo:
        upper.fuse(lower, on="outer_wall", from_anchor="outer_wall")
    msg = str(excinfo.value)
    assert "same cylindrical surface from the same side" in msg
    assert "union(self, host)" in msg


# --- self_only=True: return extended self without host union ---


def test_self_only_concentric_returns_extended_self_no_host():
    """Holder inside barrel with self_only=True. Returns the extended
    holder only; barrel is not in the result."""
    barrel = Tube(h=50, od=20, id=10)
    holder = Tube(h=8, od=10, id=4).up(20)
    result = holder.fuse(barrel, self_only=True)
    assert not isinstance(result, Union)
    bb = bbox(result)
    assert bb.min[2] == pytest.approx(20.0)
    assert bb.max[2] == pytest.approx(28.0)


def test_self_only_planar_returns_extended_self_no_host():
    """Cube on cube with self_only=True. Returns the extended peg
    only; plate is not in the result."""
    plate = cube([10, 10, 2], center=True)
    peg = cube([10, 10, 5], center=True).up(3.5)
    result = peg.fuse(plate, self_only=True)
    assert not isinstance(result, Union)
    bb = bbox(result)
    assert bb.max[2] == pytest.approx(6.0)


def test_self_only_raises_when_lever_on_host():
    """When self has no fuse_extend and the lever is on host, self_only
    raises instead of silently falling back to host extension."""
    from scadwright.component.anchors import anchor as _anchor

    class Holder(Component):
        equations = "h, od > 0"
        outer_wall = _anchor(
            at="od / 2, 0, h / 2",
            normal=(1.0, 0.0, 0.0),
            kind="cylindrical",
            surface_params={
                "axis": (0.0, 0.0, 1.0),
                "radius": "od / 2",
                "length": "h",
            },
        )
        def build(self):
            return cylinder(h=self.h, r=self.od / 2)

    barrel = Tube(h=50, od=20, id=10)
    holder = Holder(h=8, od=10).up(20)
    # Normal fuse() works (falls through to barrel's inner-wall lever).
    normal_result = holder.fuse(barrel)
    assert isinstance(normal_result, Union)
    # self_only raises because Holder (a Component) has no fuse_extend.
    with pytest.raises(ValidationError, match="self_only"):
        holder.fuse(barrel, self_only=True)


def test_self_only_disable_eps_returns_aligned_self():
    """Under disable_eps_fuse(), self_only returns the aligned self
    without extension and without host."""
    from scadwright import disable_eps_fuse
    barrel = Tube(h=50, od=20, id=10)
    holder = Tube(h=8, od=10, id=4).up(20)
    with disable_eps_fuse():
        result = holder.fuse(barrel, self_only=True)
    assert not isinstance(result, Union)
    bb = bbox(result)
    assert bb.min[2] == pytest.approx(20.0)
    assert bb.max[2] == pytest.approx(28.0)
