"""Tests for ``Anchor._validate_geometry`` — per-kind self-consistency
checks that fire at user-input boundaries (Component class-scope
``anchor()``, ``Component._set_anchor(...)``, ``Node.with_anchor(...)``).

Coverage matches the principle: catch what we can cheaply and reliably
(cylindrical/conical/spherical declarations); document the gap for what
we can't (meridional, anchor-on-actual-build-output).
"""

import pytest

from scadwright import Component, Param, anchor
from scadwright.anchor import Anchor
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder


# --- Cylindrical: normal ⊥ axis, positive dimensions ---


def test_cylindrical_valid_passes():
    a = Anchor(
        position=(5, 0, 10),
        normal=(1, 0, 0),
        kind="cylindrical",
        axis=(0, 0, 1),
        radius=5,
        length=20,
    )
    a._validate_geometry()  # no raise


def test_cylindrical_normal_not_perpendicular_raises():
    a = Anchor(
        position=(5, 0, 10),
        normal=(0, 0, 1),  # parallel to axis — wrong
        kind="cylindrical",
        axis=(0, 0, 1),
        radius=5,
        length=20,
    )
    with pytest.raises(ValidationError, match="not perpendicular to axis"):
        a._validate_geometry()


def test_cylindrical_normal_not_unit_raises():
    a = Anchor(
        position=(5, 0, 10),
        normal=(2, 0, 0),  # length 2, not unit
        kind="cylindrical",
        axis=(0, 0, 1),
        radius=5,
        length=20,
    )
    with pytest.raises(ValidationError, match="not a unit vector"):
        a._validate_geometry()


def test_cylindrical_axis_not_unit_raises():
    a = Anchor(
        position=(5, 0, 10),
        normal=(1, 0, 0),
        kind="cylindrical",
        axis=(0, 0, 2),  # length 2
        radius=5,
        length=20,
    )
    with pytest.raises(ValidationError, match="axis.*not a unit vector"):
        a._validate_geometry()


def test_cylindrical_zero_radius_raises():
    a = Anchor(
        position=(0, 0, 10),
        normal=(1, 0, 0),
        kind="cylindrical",
        axis=(0, 0, 1),
        radius=0,
        length=20,
    )
    with pytest.raises(ValidationError, match="radius must be positive"):
        a._validate_geometry()


def test_cylindrical_zero_length_raises():
    a = Anchor(
        position=(5, 0, 0),
        normal=(1, 0, 0),
        kind="cylindrical",
        axis=(0, 0, 1),
        radius=5,
        length=0,
    )
    with pytest.raises(ValidationError, match="length must be positive"):
        a._validate_geometry()


# --- Conical: same normal-perpendicular-to-axis, plus r1/r2/length ---


def test_conical_valid_passes():
    a = Anchor(
        position=(7.5, 0, 10),
        normal=(1, 0, 0),
        kind="conical",
        axis=(0, 0, 1),
        r1=5,
        r2=10,
        length=20,
    )
    a._validate_geometry()


def test_conical_negative_r1_raises():
    a = Anchor(
        position=(7.5, 0, 10),
        normal=(1, 0, 0),
        kind="conical",
        axis=(0, 0, 1),
        r1=-1,
        r2=10,
        length=20,
    )
    with pytest.raises(ValidationError, match="non-negative"):
        a._validate_geometry()


def test_conical_both_radii_zero_raises():
    a = Anchor(
        position=(0, 0, 10),
        normal=(1, 0, 0),
        kind="conical",
        axis=(0, 0, 1),
        r1=0,
        r2=0,
        length=20,
    )
    with pytest.raises(ValidationError, match="degenerate point cone"):
        a._validate_geometry()


def test_conical_normal_not_perpendicular_raises():
    a = Anchor(
        position=(7.5, 0, 10),
        normal=(0, 0, 1),
        kind="conical",
        axis=(0, 0, 1),
        r1=5,
        r2=10,
        length=20,
    )
    with pytest.raises(ValidationError, match="not perpendicular"):
        a._validate_geometry()


# --- Spherical: position-on-surface + normal-radial ---


def test_spherical_valid_passes():
    a = Anchor(
        position=(0, 0, 5),
        normal=(0, 0, 1),
        kind="spherical",
        axis=(0, 0, 1),
        axis_origin=(0, 0, 0),
        meridian_zero=(1, 0, 0),
        radius=5,
    )
    a._validate_geometry()


def test_spherical_position_off_surface_raises():
    a = Anchor(
        position=(0, 0, 7),  # not at distance 5 from origin
        normal=(0, 0, 1),
        kind="spherical",
        axis=(0, 0, 1),
        axis_origin=(0, 0, 0),
        meridian_zero=(1, 0, 0),
        radius=5,
    )
    with pytest.raises(ValidationError, match="must lie on the sphere"):
        a._validate_geometry()


def test_spherical_normal_not_radial_raises():
    a = Anchor(
        position=(0, 0, 5),
        normal=(1, 0, 0),  # not radial — should be (0, 0, 1)
        kind="spherical",
        axis=(0, 0, 1),
        axis_origin=(0, 0, 0),
        meridian_zero=(1, 0, 0),
        radius=5,
    )
    with pytest.raises(ValidationError, match="radial direction"):
        a._validate_geometry()


def test_spherical_inner_normal_inverted_passes():
    """Inner spherical anchor: normal points inward (toward axis_origin)."""
    a = Anchor(
        position=(0, 0, 5),
        normal=(0, 0, -1),  # inward radial
        kind="spherical",
        axis=(0, 0, 1),
        axis_origin=(0, 0, 0),
        meridian_zero=(1, 0, 0),
        radius=5,
        inner=True,
    )
    a._validate_geometry()


def test_spherical_inner_normal_outward_raises():
    a = Anchor(
        position=(0, 0, 5),
        normal=(0, 0, 1),  # outward; wrong for inner
        kind="spherical",
        axis=(0, 0, 1),
        axis_origin=(0, 0, 0),
        meridian_zero=(1, 0, 0),
        radius=5,
        inner=True,
    )
    with pytest.raises(ValidationError, match="inward.*radial"):
        a._validate_geometry()


def test_spherical_offset_center_passes():
    """Sphere not centered at origin: distance check uses axis_origin."""
    a = Anchor(
        position=(10, 20, 35),  # 5 units +Z from center (10, 20, 30)
        normal=(0, 0, 1),
        kind="spherical",
        axis=(0, 0, 1),
        axis_origin=(10, 20, 30),
        meridian_zero=(1, 0, 0),
        radius=5,
    )
    a._validate_geometry()


# --- Planar: no curved-surface check ---


def test_planar_skips_curved_check():
    """Bare planar anchors don't require any geometric self-consistency."""
    a = Anchor(position=(0, 0, 0), normal=(0, 0, 1))
    a._validate_geometry()


def test_planar_with_rim_radius_passes():
    """Planar cap anchors (cylinder/cone top) carry rim_radius but
    aren't subject to curved-surface validation."""
    a = Anchor(
        position=(0, 0, 10),
        normal=(0, 0, 1),
        kind="planar",
        axis=(0, 0, 1),
        meridian_zero=(1, 0, 0),
        rim_radius=5,
    )
    a._validate_geometry()


# --- Validation fires at user-input boundaries ---


def test_component_class_scope_anchor_validates():
    """A bad cylindrical anchor declared at class scope raises at
    instance construction."""

    class BadCylinderShape(Component):
        equations = "h, r > 0"
        # Normal parallel to axis — wrong.
        wall = anchor(
            at="r, 0, h/2",
            normal=(0, 0, 1),  # wrong: should be radial
            kind="cylindrical",
            surface_params={"axis": (0, 0, 1), "radius": "r", "length": "h"},
        )

        def build(self):
            return cylinder(h=self.h, r=self.r)

    with pytest.raises(ValidationError, match="not perpendicular"):
        BadCylinderShape(h=10, r=5)


def test_component_class_scope_valid_anchor_passes():
    class GoodCylinderShape(Component):
        equations = "h, r > 0"
        wall = anchor(
            at="r, 0, h/2",
            normal=(1, 0, 0),
            kind="cylindrical",
            surface_params={"axis": (0, 0, 1), "radius": "r", "length": "h"},
        )

        def build(self):
            return cylinder(h=self.h, r=self.r)

    GoodCylinderShape(h=10, r=5)  # no raise


def test_component_runtime_set_anchor_validates():
    """Framework-internal Component._set_anchor() runs the same per-kind
    geometric check as the declarative path."""
    class Foo(Component):
        equations = "size > 0"

        def build(self):
            return cube([self.size, self.size, self.size])

    f = Foo(size=10)
    with pytest.raises(ValidationError, match="not perpendicular"):
        f._set_anchor(
            "wall",
            position=(5, 0, 5),
            normal=(0, 0, 1),  # wrong
            kind="cylindrical",
            axis=(0, 0, 1),
            radius=5,
            length=10,
        )


def test_with_anchor_validates():
    """Node.with_anchor also catches geometric errors."""
    c = cube([10, 10, 10])
    with pytest.raises(ValidationError, match="must lie on the sphere"):
        c.with_anchor(
            "bad",
            at=(0, 0, 7),  # not at radius 5 from origin
            normal=(0, 0, 1),
            kind="spherical",
            axis=(0, 0, 1),
            axis_origin=(0, 0, 0),
            meridian_zero=(1, 0, 0),
            radius=5,
        )


def test_with_anchor_valid_passes():
    c = cube([10, 10, 10])
    c.with_anchor(
        "ok",
        at=(0, 0, 5),
        normal=(0, 0, 1),
        kind="spherical",
        axis=(0, 0, 1),
        axis_origin=(0, 0, 0),
        meridian_zero=(1, 0, 0),
        radius=5,
    )


# --- Internal Anchor constructions skip validation ---


def test_transform_anchors_does_not_raise_on_inconsistent_result():
    """transform_anchors after non-uniform scale on a sphere produces
    a 'radius' that doesn't match the position-to-axis_origin distance
    (we approximate radial scale with a single perpendicular). This is
    not a user-facing validation case — the internal Anchor construction
    should not call _validate_geometry, so no false positive raises."""
    from scadwright.anchor import get_node_anchors
    from scadwright.primitives import sphere

    # Non-uniform scale: x*2, y*1, z*1.
    s = sphere(r=5).scale([2, 1, 1])
    # Should not raise — the framework applies the matrix and produces
    # an anchor; the inconsistency is accepted internally.
    anchors = get_node_anchors(s)
    assert "top" in anchors
