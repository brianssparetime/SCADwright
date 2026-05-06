"""Tight bbox via AST analysis.

``tight_bbox(node)`` walks the AST honestly: transforms compose,
Union/Hull unite, Intersection clips, Component delegates to its
overridable ``tight_bbox`` method. Difference is the only operator
that can't be tightened — it raises ``NotImplementedError`` with
workaround guidance.

Distinct from ``bbox(node)``, which is always conservative-fast.
"""

from __future__ import annotations

import pytest

from scadwright import BBox, Component, bbox, tight_bbox
from scadwright.boolops import difference, intersection, union
from scadwright.primitives import cube, cylinder, sphere


# =============================================================================
# Primitives — same as bbox
# =============================================================================


def test_tight_bbox_cube():
    bb = tight_bbox(cube([10, 20, 30]))
    assert bb.min == (0, 0, 0)
    assert bb.max == (10, 20, 30)


def test_tight_bbox_sphere():
    bb = tight_bbox(sphere(r=5))
    assert bb.min == (-5, -5, -5)
    assert bb.max == (5, 5, 5)


# =============================================================================
# Transforms — compose through the matrix
# =============================================================================


def test_tight_bbox_translate():
    bb = tight_bbox(cube(10).translate([5, 0, 0]))
    assert bb.min == (5, 0, 0)
    assert bb.max == (15, 10, 10)


def test_tight_bbox_rotate_axis_aligned():
    # 90° around Z swaps X and Y extents.
    bb = tight_bbox(cube([10, 20, 30]).rotate(90, [0, 0, 1]))
    # cube extends to [10,20,30] from origin; after 90Z it's [(-20,0), (0,10), (0,30)].
    assert bb.min[0] == pytest.approx(-20)
    assert bb.max[0] == pytest.approx(0)
    assert bb.min[1] == pytest.approx(0)
    assert bb.max[1] == pytest.approx(10)


# =============================================================================
# CSG — Union and Intersection tighten correctly
# =============================================================================


def test_tight_bbox_union():
    # cube(10) bbox: [0,10]³.
    # sphere(r=2) translated +20x: [18,22]×[-2,2]×[-2,2].
    # Union: [0,22]×[-2,10]×[-2,10].
    bb = tight_bbox(union(cube(10), sphere(r=2).translate([20, 0, 0])))
    assert bb.min == (0, -2, -2)
    assert bb.max == (22, 10, 10)


def test_tight_bbox_intersection_clips():
    """Intersection clips children's bboxes — the framework's existing
    BBoxVisitor logic that ``halve()`` relies on for tight bboxes."""
    bb = tight_bbox(intersection(
        cube([20, 20, 20]),
        cube([10, 30, 30]).translate([5, -5, -5]),
    ))
    # First cube: [0,20]³. Second cube translated: [5,15]×[-5,25]×[-5,25].
    # Intersection: [5,15]×[0,20]×[0,20].
    assert bb.min == (5, 0, 0)
    assert bb.max == (15, 20, 20)


def test_tight_bbox_halve_uses_intersection_path():
    """``halve()`` emits Intersection, which is tightened by the visitor.
    No Component override needed for halved geometry."""
    bb = tight_bbox(cube(20, center=True).halve([1, 0, 0]))
    # Centered cube: [-10,10]³. Keep +x: [0,10]×[-10,10]×[-10,10].
    assert bb.min[0] == 0
    assert bb.max[0] == 10


# =============================================================================
# Difference — raises with workaround guidance
# =============================================================================


def test_tight_bbox_difference_raises():
    """The single operator that AST analysis can't tighten."""
    part = difference(cube(20), cube(10).translate([5, 5, 5]))
    with pytest.raises(NotImplementedError, match="cannot tighten Difference"):
        tight_bbox(part)


def test_tight_bbox_difference_error_names_workarounds():
    part = difference(cube(20), cube(10))
    with pytest.raises(NotImplementedError) as exc:
        tight_bbox(part)
    msg = str(exc.value)
    assert "halve" in msg
    assert "Component.tight_bbox" in msg
    assert "bbox()" in msg


# =============================================================================
# Component — delegates to .tight_bbox()
# =============================================================================


def test_tight_bbox_component_default_walks_built_tree():
    """Default ``Component.tight_bbox`` walks the built tree using
    the same visitor — no override needed when the build tree
    consists of operators that AST analysis can tighten."""

    class Box(Component):
        def build(self):
            return cube([10, 20, 30])

    bb = tight_bbox(Box())
    assert bb.min == (0, 0, 0)
    assert bb.max == (10, 20, 30)


def test_tight_bbox_component_with_difference_raises_naming_class():
    """A Component whose build tree uses Difference and doesn't
    override ``tight_bbox`` raises with the class name in the
    message — the user knows exactly where to add the override."""

    class Chopper(Component):
        def build(self):
            return difference(cube(20), cube(10).translate([5, 5, 15]))

    with pytest.raises(NotImplementedError, match="Chopper.tight_bbox"):
        tight_bbox(Chopper())


def test_tight_bbox_component_override_returns_declared_extents():
    """The author declares the true bbox; the visitor uses it."""

    class TruncCone(Component):
        def build(self):
            # Some Difference-using shape — the build can be anything;
            # the override declares the truth.
            return difference(
                cylinder(r1=10, r2=5, h=10),
                cube([20, 20, 5]).translate([-10, -10, 8]),
            )

        def tight_bbox(self):
            # Author declares: the true height is 8 after the chop.
            return BBox(min=(-10, -10, 0), max=(10, 10, 8))

    bb = tight_bbox(TruncCone())
    assert bb.min == (-10, -10, 0)
    assert bb.max == (10, 10, 8)


def test_tight_bbox_component_override_with_drilled_hole():
    """A Component whose Difference is a drill-through that doesn't
    change outer extents: override returns the conservative bbox to
    assert it's actually tight."""

    class DrilledBox(Component):
        def build(self):
            return difference(
                cube([20, 20, 5]),
                cylinder(r=2, h=10).translate([10, 10, -1]),
            )

        def tight_bbox(self):
            # Drill doesn't reach the outer surface in X/Y, and
            # extends through Z — the box's conservative bbox IS
            # tight for the outer extents.
            return bbox(self)

    bb = tight_bbox(DrilledBox())
    assert bb.min == (0, 0, 0)
    assert bb.max == (20, 20, 5)


def test_tight_bbox_component_through_outer_transform():
    """Outer transform composes with the Component's local tight bbox."""

    class Box(Component):
        def build(self):
            return cube([10, 20, 30])

    bb = tight_bbox(Box().translate([100, 0, 0]))
    assert bb.min == (100, 0, 0)
    assert bb.max == (110, 20, 30)


# =============================================================================
# Cache — repeated calls don't rewalk
# =============================================================================


def test_tight_bbox_caches_on_component_instance():
    class Box(Component):
        def build(self):
            return cube(10)

    c = Box()
    _ = tight_bbox(c)
    assert getattr(c, "_tight_bbox_cache", None) is not None


# =============================================================================
# CHILDREN placeholder — same as bbox, raises
# =============================================================================


def test_tight_bbox_on_children_marker_raises():
    from scadwright.ast.custom import CHILDREN
    from scadwright.errors import ValidationError

    with pytest.raises(ValidationError, match="CHILDREN placeholder"):
        tight_bbox(CHILDREN)
