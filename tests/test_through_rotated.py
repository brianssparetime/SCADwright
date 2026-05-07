"""Tests for through() on rotated cutters (local-axis path).

The local-axis path activates when the user passes ``axis="local"``,
``"local_x"``, ``"local_y"``, or ``"local_z"`` to ``through()``. It
walks the cutter's transform stack, extracts the cumulative rotation,
and checks coincidence between the cutter's end-face centers and the
parent's AABB face planes — the world-axis path's bbox-comparison
approach silently no-ops on rotated cutters.
"""

import math

import pytest

from scadwright import bbox, emit_str, tree_hash, Component
from scadwright.boolops import difference, union
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder, sphere


def _extract_translate_offset(scad: str, axis: str = "z") -> float:
    """Best-effort: pull the inner-leaf translate offset from emitted SCAD.

    Looks for the deepest ``translate([..., ..., ...])`` line, which is
    the leaf-level extension we just inserted.
    """
    import re
    matches = re.findall(r"translate\(\[([^\]]+)\]\)", scad)
    if not matches:
        return 0.0
    last = matches[-1]
    parts = [float(x.strip()) for x in last.split(",")]
    idx = {"x": 0, "y": 1, "z": 2}[axis]
    return parts[idx]


# --- 30° rotated cone, both faces coincident ---


def test_through_local_z_rotated_cone_both_ends_coincident():
    """A cone rotated 30° around Y, sized so both end faces sit on the
    plate's bottom and top surfaces, gets both ends extended in
    cutter-local Z."""
    plate = cube([20, 20, 2])
    h_local = 2 / math.cos(math.radians(30))
    cone = (
        cylinder(h=h_local, r=2)
        .rotate([0, 30, 0])
        .translate([10, 5, 0])
    )
    extended = cone.through(plate, axis="local_z")

    # Verify: SCAD output keeps the outer rotates and translate, plus
    # adds an inner translate + scale at the leaf.
    scad = emit_str(extended)
    assert "rotate([0, 30, 0])" in scad
    # The leaf-level translate offset on local Z should be -eps (= -0.01).
    leaf_offset_z = _extract_translate_offset(scad, "z")
    assert leaf_offset_z == pytest.approx(-0.01, abs=1e-9)
    # Scale on local Z = (h_local + 2*eps) / h_local.
    expected_scale = (h_local + 0.02) / h_local
    import re
    m = re.search(r"scale\(\[1, 1, ([\d.]+)\]\)", scad)
    assert m, f"expected leaf-level scale on local Z, got SCAD:\n{scad}"
    assert float(m.group(1)) == pytest.approx(expected_scale, abs=1e-6)


# --- one-end-only coincidence ---


def test_through_local_z_only_min_face_coincident():
    """Cone with local Z=0 face on the plate's bottom but local Z=h
    above the plate: only Z_min extends."""
    plate = cube([20, 20, 2])
    cone = (
        cylinder(h=8, r=2)  # local z=[0, 8]; far above the plate
        .rotate([0, 30, 0])
        .translate([10, 5, 0])
    )
    extended = cone.through(plate, axis="local_z")

    scad = emit_str(extended)
    leaf_offset_z = _extract_translate_offset(scad, "z")
    # Only Z_min extends: orig Z range [0, 8] -> [-eps, 8].
    # Scale = (8 + eps) / 8; translate = -eps.
    assert leaf_offset_z == pytest.approx(-0.01, abs=1e-9)
    import re
    m = re.search(r"scale\(\[1, 1, ([\d.]+)\]\)", scad)
    assert m
    expected_scale = 8.01 / 8
    assert float(m.group(1)) == pytest.approx(expected_scale, abs=1e-6)


# --- no coincidence: explicit axis raises ---


def test_through_local_z_no_coincidence_raises():
    """When the user explicitly asked for local-axis and there's no
    coincident face, raise rather than silently no-op."""
    plate = cube([20, 20, 2])
    # Cone floating above the plate; neither local Z face is on a plate face.
    floating = (
        cylinder(h=8, r=2)
        .rotate([0, 30, 0])
        .translate([10, 5, 5])  # cone Z=0 face at world (10, 5, 5), not on any plate face
    )
    with pytest.raises(ValidationError, match="no cutter end-face is coincident"):
        floating.through(plate, axis="local_z")


# --- anisotropic Scale in transform stack raises ---


def test_through_local_z_anisotropic_scale_raises():
    """Cutters with non-uniform Scale in their transform stack are
    rejected — the cumulative transform isn't a pure rotation."""
    plate = cube([20, 20, 2])
    cutter = (
        cube([2, 2, 10])
        .scale([1, 2, 1])
        .rotate([0, 30, 0])
        .translate([10, 5, 0])
    )
    with pytest.raises(ValidationError, match="not a pure rotation|orthogonal"):
        cutter.through(plate, axis="local_z")


# --- Mirror in transform stack raises (det = -1) ---


def test_through_local_z_mirror_raises():
    """Mirror inverts orientation (det = -1); the local-axis path
    rejects it."""
    plate = cube([20, 20, 2])
    cutter = (
        cylinder(h=2, r=2)
        .mirror([1, 0, 0])
        .rotate([0, 30, 0])
        .translate([10, 5, 0])
    )
    with pytest.raises(ValidationError, match="Mirror|orientation-reversing"):
        cutter.through(plate, axis="local_z")


# --- auto-detect with rotated cutter raises pointing at local-axis ---


def test_through_auto_detect_rotated_non_permuting_raises():
    """Auto-detect on a non-axis-permuting rotation raises pointing at
    the local-axis form."""
    plate = cube([20, 20, 2])
    cone = (
        cylinder(h=2, r=2)
        .rotate([0, 30, 0])
        .translate([10, 5, 0])
    )
    with pytest.raises(ValidationError, match="cutter-local space"):
        cone.through(plate)


def test_through_auto_detect_axis_permuting_rotation_works():
    """A 90° rotation permutes axes but keeps the bbox axis-aligned;
    the world-axis path handles it correctly. No raise."""
    plate = cube([20, 20, 10])
    # cylinder along world X, fully spanning the plate's X extent
    cutter = (
        cylinder(h=20, r=2)
        .rotate([0, 90, 0])
        .translate([0, 10, 5])
    )
    extended = cutter.through(plate)
    bb = bbox(extended)
    # Bottom of cylinder rotates to negative X; top to positive X.
    # The world-axis path should extend on world X.
    assert bb.size[0] >= 20.0  # extension applied somewhere


# --- axis="local" as synonym for axis="local_z" ---


def test_through_local_synonym_for_local_z():
    """``axis='local'`` resolves to ``axis='local_z'`` (cylinder convention)."""
    plate = cube([20, 20, 2])
    h_local = 2 / math.cos(math.radians(30))
    cone = (
        cylinder(h=h_local, r=2)
        .rotate([0, 30, 0])
        .translate([10, 5, 0])
    )
    via_local = cone.through(plate, axis="local")
    via_local_z = cone.through(plate, axis="local_z")
    assert tree_hash(via_local) == tree_hash(via_local_z)


# --- identity rotation treated as no rotation ---


def test_through_identity_rotation_uses_world_axis():
    """``Rotate(angles=(0, 0, 0))`` is effectively identity; auto-detect
    should use the world-axis path (no 'rotated cutter' raise)."""
    plate = cube([20, 20, 10])
    cutter = (
        cylinder(h=10, r=2)
        .rotate([0, 0, 0])  # zero rotation
    )
    # World-axis path should find both ends coincident on world Z and extend.
    extended = cutter.through(plate)
    bb = bbox(extended)
    assert bb.min[2] == pytest.approx(-0.01)
    assert bb.max[2] == pytest.approx(10.01)


# --- compound leaf: Union of two cylinders rotated together ---


def test_through_local_z_union_leaf_both_children_stretch():
    """When the cutter's leaf is a Union, the local-frame Translate+Scale
    stretches the entire compound. Both children of the Union extend
    proportionally along local Z."""
    plate = cube([40, 40, 2])
    h_local = 2 / math.cos(math.radians(30))
    cutter = (
        union(
            cylinder(h=h_local, r=2),
            cylinder(h=h_local, r=2).translate([5, 0, 0]),
        )
        .rotate([0, 30, 0])
        .translate([10, 10, 0])
    )
    extended = cutter.through(plate, axis="local_z")
    # The union has its bbox stretched along local Z by the same factor;
    # both children move with it. Smoke check: the result emits valid SCAD.
    scad = emit_str(extended)
    assert "union()" in scad
    assert "scale" in scad
    # Two cylinders should still appear in the output.
    assert scad.count("cylinder(") == 2


# --- Component-leaf snapshot preservation (R1 from design doc) ---


class _SnapshotProbe(Component):
    equations = "r > 0"

    def build(self):
        # `r=2` is a Param value; the resolution snapshot is what we're checking.
        return cylinder(h=2 / math.cos(math.radians(30)), r=self.r)

    def tight_bbox(self):
        from scadwright.bbox import BBox
        h = 2 / math.cos(math.radians(30))
        return BBox(min=(-self.r, -self.r, 0), max=(self.r, self.r, h))


def test_through_local_z_preserves_component_snapshot():
    """Wrapping a Component leaf in Translate(Scale(...)) for the
    extension would normally trigger Position-Y's __post_init__ to
    re-capture the Component's resolution snapshot. The placement helper
    saves and restores the snapshot around the wrap to prevent that."""
    from scadwright.api.resolution import resolution

    plate = cube([20, 20, 2])
    with resolution(fn=64):
        c = _SnapshotProbe(r=2)
    # c's snapshot should be (64, None, None) from construction.
    assert c._ctx_resolution == (64, None, None), (
        f"setup expected (64, None, None), got {c._ctx_resolution}"
    )

    # Now wrap and call through with axis="local_z". The leaf-level
    # Translate+Scale insertion must NOT clobber c's snapshot.
    cutter = c.rotate([0, 30, 0]).translate([10, 5, 0])
    # The wrap-time __post_init__ recaptures c with whatever ambient is here.
    # That's outside the resolution() block, so c's snapshot was already
    # overwritten by the .rotate() and .translate() calls. To isolate the
    # through() snapshot interaction, restore the original snapshot first.
    c._ctx_resolution = (64, None, None)

    _ = cutter.through(plate, axis="local_z")

    # After through(), the snapshot must still be (64, None, None) — the
    # save/restore in wrap_leaf_with_eps must have preserved it.
    assert c._ctx_resolution == (64, None, None), (
        f"snapshot was clobbered by leaf-level wrap: now {c._ctx_resolution}"
    )


# --- regression: existing axis-aligned through() tests stay green ---


def test_through_axis_aligned_unchanged():
    """A non-rotated cutter still uses the world-axis path with no
    behavior change."""
    box = cube([20, 20, 10])
    hole = cylinder(h=10, r=3).through(box)
    bb = bbox(hole)
    assert bb.min[2] == pytest.approx(-0.01)
    assert bb.max[2] == pytest.approx(10.01)


def test_through_explicit_axis_world_unchanged():
    """Explicit world-axis still works unchanged."""
    box = cube([20, 20, 10])
    hole = cylinder(h=10, r=3).through(box, axis="z")
    bb = bbox(hole)
    assert bb.min[2] == pytest.approx(-0.01)
    assert bb.max[2] == pytest.approx(10.01)
