"""Walker tests: parallel structure walk + per-leaf transform pairing.

The walker descends both variant trees in lockstep, preserving CSG
structure and decoration wrappers, and identifies leaves (Components and
inline primitives) whose transform stacks differ between variants. Those
leaves end up in the MorphPlan as AnimatedLeaf entries.
"""

from __future__ import annotations

import pytest

from scadwright import Component, Param, positive
from scadwright.animation._morph_walker import (
    AnimatedLeaf, MorphPlan, walk,
)
from scadwright.boolops import difference, intersection, union, hull
from scadwright.design import Design, _reset_for_testing, variant
from scadwright.errors import ValidationError
from scadwright.primitives import cube, sphere


class _Box(Component):
    size: float = Param(default=10.0, validators=(positive,))

    def build(self):
        return cube(self.size)


class _Lid(Component):
    size: float = Param(default=12.0, validators=(positive,))

    def build(self):
        return cube([self.size, self.size, 2.0])


@pytest.fixture(autouse=True)
def reset_registry():
    _reset_for_testing()
    yield
    _reset_for_testing()


# ---------------------------------------------------------------------------
# Basic Component pairing
# ---------------------------------------------------------------------------


def test_walker_static_part_produces_no_animation_entry():
    """One Component at identity on both sides → no leaves; tree passes through."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant(default=True)
        def b(self):
            return self.box

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    assert isinstance(plan, MorphPlan)
    assert plan.leaves == ()


def test_walker_pairs_translated_part():
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant(default=True)
        def b(self):
            return self.box.up(5)

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    assert len(plan.leaves) == 1
    leaf = plan.leaves[0]
    assert leaf.leaf is D.box
    assert leaf.display_name == "box"
    assert leaf.M_a.is_identity
    assert leaf.M_b.translation == (0.0, 0.0, 5.0)


def test_walker_two_parts_in_union():
    class D(Design):
        box = _Box()
        lid = _Lid()

        @variant()
        def a(self):
            return union(self.box, self.lid.up(10))

        @variant(default=True)
        def b(self):
            return union(self.box, self.lid.up(20))

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    # box is static (M_a == M_b == identity), so only lid is in leaves.
    assert len(plan.leaves) == 1
    lid_leaf = plan.leaves[0]
    assert lid_leaf.display_name == "lid"
    assert lid_leaf.M_a.translation == (0.0, 0.0, 10.0)
    assert lid_leaf.M_b.translation == (0.0, 0.0, 20.0)


# ---------------------------------------------------------------------------
# Substitution root identification
# ---------------------------------------------------------------------------


def test_walker_substitution_root_at_topmost_spatial_wrapper():
    """`Translate(globally, self.box)` (no CSG) → sub root is the Translate."""
    from scadwright.ast.transforms import Translate
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return Translate(v=(1.0, 2.0, 3.0), child=self.box)

        @variant(default=True)
        def b(self):
            return Translate(v=(5.0, 6.0, 7.0), child=self.box)

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    assert len(plan.leaves) == 1
    leaf = plan.leaves[0]
    # The substitution root is the outer Translate of variant A.
    assert leaf.substitution_root is plan.tree_a


def test_walker_substitution_root_resets_at_csg_node():
    """`Translate(globally, Union(self.box, sphere(10)))` — the outer Translate
    is above a Union, so it's part of the structural skeleton, not the
    substitution root for self.box. self.box's M_a should be identity."""
    from scadwright.ast.transforms import Translate
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return Translate(v=(1.0, 0.0, 0.0), child=union(self.box, sphere(10).up(20)))

        @variant(default=True)
        def b(self):
            return Translate(v=(1.0, 0.0, 0.0), child=union(self.box.up(5), sphere(10).up(20)))

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    # self.box animates from identity to translate(0,0,5) — the outer
    # Translate is preserved structurally and doesn't accumulate.
    box_leaves = [l for l in plan.leaves if l.display_name == "box"]
    assert len(box_leaves) == 1
    assert box_leaves[0].M_a.is_identity
    assert box_leaves[0].M_b.translation == (0.0, 0.0, 5.0)


# ---------------------------------------------------------------------------
# Non-Union CSG with parts: the big change from the original walker.
# ---------------------------------------------------------------------------


def test_walker_part_inside_difference_now_animates():
    """`difference(self.body, self.hole.up(5))` vs `.up(10)` should ANIMATE
    self.hole (the cutter slides between positions) and preserve the
    difference structure."""
    class D(Design):
        body = _Box()
        hole = _Box()

        @variant()
        def a(self):
            return difference(self.body, self.hole.up(5))

        @variant(default=True)
        def b(self):
            return difference(self.body, self.hole.up(10))

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    # body is static; hole animates.
    assert len(plan.leaves) == 1
    hole_leaf = plan.leaves[0]
    assert hole_leaf.display_name == "hole"
    assert hole_leaf.M_a.translation == (0.0, 0.0, 5.0)
    assert hole_leaf.M_b.translation == (0.0, 0.0, 10.0)


def test_walker_part_inside_intersection_animates():
    class D(Design):
        body = _Box()
        cutter = _Box()

        @variant()
        def a(self):
            return intersection(self.body, self.cutter.up(2))

        @variant(default=True)
        def b(self):
            return intersection(self.body, self.cutter.up(5))

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    assert len(plan.leaves) == 1
    assert plan.leaves[0].display_name == "cutter"


def test_walker_difference_with_no_components_is_carried_in_tree_a():
    """A static difference with no Components — both sides identical —
    passes through as part of the structural template. No leaves entry."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return union(self.box, difference(cube(5), sphere(3)).up(20))

        @variant(default=True)
        def b(self):
            return union(self.box.up(10), difference(cube(5), sphere(3)).up(20))

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    box_leaves = [l for l in plan.leaves if l.display_name == "box"]
    assert len(box_leaves) == 1
    # The diff-of-primitives is static; it pairs structurally because the
    # cubes/spheres tree-hash the same on both sides. No leaves entry.
    assert all(l.display_name == "box" for l in plan.leaves)


# ---------------------------------------------------------------------------
# Inline primitives can animate
# ---------------------------------------------------------------------------


def test_walker_inline_primitive_can_animate():
    """`cube(5).up(20)` vs `cube(5).up(30)` — primitive matches by
    tree_hash, transforms differ → animates without lifting to a Component."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return union(self.box, cube(5).up(20))

        @variant(default=True)
        def b(self):
            return union(self.box, cube(5).up(30))

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    primitive_leaves = [l for l in plan.leaves if "inline" in l.display_name]
    assert len(primitive_leaves) == 1
    assert primitive_leaves[0].M_a.translation == (0.0, 0.0, 20.0)
    assert primitive_leaves[0].M_b.translation == (0.0, 0.0, 30.0)


def test_walker_inline_primitive_static_doesnt_animate():
    """Same cube at the same position on both sides — passes through, no
    leaf entry."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return union(self.box, cube(5).up(20))

        @variant(default=True)
        def b(self):
            return union(self.box.up(10), cube(5).up(20))

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    # Only self.box animates; cube is static.
    assert all(l.display_name == "box" for l in plan.leaves)


def test_walker_different_primitive_types_raises():
    """cube vs sphere at the same position → primitive mismatch."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return union(self.box, cube(5).up(20))

        @variant(default=True)
        def b(self):
            return union(self.box, sphere(5).up(20))

    inst = D()
    with pytest.raises(ValidationError, match=r"(?s)inline primitive geometry differs"):
        walk(inst.a(), inst.b(), inst)


def test_walker_different_primitive_parameters_raises():
    """cube(5) vs cube(7) → tree_hash mismatch."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return union(self.box, cube(5).up(20))

        @variant(default=True)
        def b(self):
            return union(self.box, cube(7).up(20))

    inst = D()
    with pytest.raises(ValidationError, match=r"(?s)inline primitive geometry differs"):
        walk(inst.a(), inst.b(), inst)


# ---------------------------------------------------------------------------
# Structural mismatches
# ---------------------------------------------------------------------------


def test_walker_csg_node_type_mismatch_raises():
    """One side uses union, the other difference. The walker should detect
    the structural difference at the first divergent node."""
    class D(Design):
        box = _Box()
        lid = _Lid()

        @variant()
        def a(self):
            return union(self.box, self.lid)

        @variant(default=True)
        def b(self):
            return difference(self.box, self.lid)

    inst = D()
    with pytest.raises(ValidationError, match=r"(?s)variant ASTs differ in structure"):
        walk(inst.a(), inst.b(), inst)


def test_walker_arity_mismatch_raises():
    """Two children in start, three in end → structural mismatch."""
    class D(Design):
        box = _Box()
        lid = _Lid()
        spacer = _Box()

        @variant()
        def a(self):
            return union(self.box, self.lid)

        @variant(default=True)
        def b(self):
            return union(self.box, self.lid, self.spacer)

    inst = D()
    with pytest.raises(ValidationError, match=r"(?s)Union.*2 children.*3"):
        walk(inst.a(), inst.b(), inst)


def test_walker_different_components_at_same_position_raises():
    class D(Design):
        box = _Box()
        lid = _Lid()

        @variant()
        def a(self):
            return self.box

        @variant(default=True)
        def b(self):
            return self.lid

    inst = D()
    with pytest.raises(ValidationError, match=r"(?s)Component leaves differ"):
        walk(inst.a(), inst.b(), inst)


# ---------------------------------------------------------------------------
# Mirror / scale validations
# ---------------------------------------------------------------------------


def test_walker_mirror_difference_raises():
    class D(Design):
        lid = _Lid()

        @variant()
        def a(self):
            return self.lid.flip("z")

        @variant(default=True)
        def b(self):
            return self.lid

    inst = D()
    with pytest.raises(ValidationError, match=r"(?s)mirror.*det = -1.*hinge swing"):
        walk(inst.a(), inst.b(), inst)


def test_walker_uniform_scale_change_ok():
    from scadwright.ast.transforms import Scale
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return Scale(factor=(1.0, 1.0, 1.0), child=self.box)

        @variant(default=True)
        def b(self):
            return Scale(factor=(2.0, 2.0, 2.0), child=self.box)

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    assert len(plan.leaves) == 1


def test_walker_non_uniform_scale_difference_raises():
    from scadwright.ast.transforms import Scale
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant(default=True)
        def b(self):
            return Scale(factor=(2.0, 1.0, 1.0), child=self.box)

    inst = D()
    with pytest.raises(ValidationError, match=r"(?s)non-uniform scale.*differs"):
        walk(inst.a(), inst.b(), inst)


# ---------------------------------------------------------------------------
# Decorations preserved
# ---------------------------------------------------------------------------


def test_walker_color_preserved_and_matches_required():
    """Same Color on both sides → fine. The walker doesn't put the Color in
    leaves; it stays in tree_a for emit to preserve."""
    from scadwright.ast.transforms import Color
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return Color(c="red", child=self.box.up(0))

        @variant(default=True)
        def b(self):
            return Color(c="red", child=self.box.up(5))

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    assert len(plan.leaves) == 1


def test_walker_color_in_one_variant_only_gives_specific_guidance():
    """When a Color wraps the leaf in one variant but not the other, the
    error names the missing-wrapper specifically and tells the user to
    either add it to both or remove it from both — better than the
    generic 'kind differs' message."""
    from scadwright.ast.transforms import Color
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return Color(c="red", child=self.box)

        @variant(default=True)
        def b(self):
            return self.box

    inst = D()
    with pytest.raises(
        ValidationError,
        match=r"(?s)decoration wrapper present in one variant only.*Color",
    ):
        walk(inst.a(), inst.b(), inst)


def test_walker_decoration_asymmetry_names_both_sides():
    """The error names which side has the decoration and which doesn't,
    so users know what to add where."""
    from scadwright.ast.transforms import Color
    class D(Design):
        box = _Box()

        @variant()
        def plain(self):
            return self.box

        @variant(default=True)
        def colored(self):
            return Color(c="blue", child=self.box.up(10))

    inst = D()
    with pytest.raises(
        ValidationError,
        match=r"(?s)end has: Color.*start has: the leaf with no wrapper",
    ):
        walk(inst.plain(), inst.colored(), inst)


def test_walker_different_colors_raises():
    from scadwright.ast.transforms import Color
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return Color(c="red", child=self.box)

        @variant(default=True)
        def b(self):
            return Color(c="blue", child=self.box)

    inst = D()
    with pytest.raises(ValidationError, match=r"(?s)decoration mismatch.*Color\.c"):
        walk(inst.a(), inst.b(), inst)


def test_walker_different_color_alphas_raises():
    """Color alpha field must match across variants — same colour name
    but different transparency is still a mismatch."""
    from scadwright.ast.transforms import Color
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return Color(c="red", child=self.box, alpha=1.0)

        @variant(default=True)
        def b(self):
            return Color(c="red", child=self.box, alpha=0.3)

    inst = D()
    with pytest.raises(ValidationError, match=r"(?s)decoration mismatch.*Color\.alpha"):
        walk(inst.a(), inst.b(), inst)


def test_walker_different_preview_modifier_modes_raises():
    """PreviewModifier(mode='highlight') vs PreviewModifier(mode='background')
    must mismatch — the generic decoration check catches this even though
    PreviewModifier wasn't previously special-cased."""
    from scadwright.ast.transforms import PreviewModifier
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return PreviewModifier(mode="highlight", child=self.box)

        @variant(default=True)
        def b(self):
            return PreviewModifier(mode="background", child=self.box)

    inst = D()
    with pytest.raises(
        ValidationError, match=r"(?s)decoration mismatch.*PreviewModifier\.mode",
    ):
        walk(inst.a(), inst.b(), inst)


def test_walker_same_preview_modifier_mode_passes():
    from scadwright.ast.transforms import PreviewModifier
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return PreviewModifier(mode="highlight", child=self.box)

        @variant(default=True)
        def b(self):
            return PreviewModifier(mode="highlight", child=self.box.up(10))

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    assert len(plan.leaves) == 1


def test_walker_different_force_render_convexity_raises():
    """ForceRender wraps a subtree with a different convexity in each
    variant — semantically different render hints."""
    from scadwright.ast.transforms import ForceRender
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return ForceRender(child=self.box, convexity=3)

        @variant(default=True)
        def b(self):
            return ForceRender(child=self.box, convexity=10)

    inst = D()
    with pytest.raises(
        ValidationError, match=r"(?s)decoration mismatch.*ForceRender\.convexity",
    ):
        walk(inst.a(), inst.b(), inst)


def test_walker_different_resize_new_size_raises():
    """Resize is treated as a decoration; mismatching new_size is detected
    by the generic field comparison."""
    from scadwright.ast.transforms import Resize
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return Resize(new_size=(10.0, 10.0, 10.0), child=self.box)

        @variant(default=True)
        def b(self):
            return Resize(new_size=(20.0, 20.0, 20.0), child=self.box)

    inst = D()
    with pytest.raises(
        ValidationError, match=r"(?s)decoration mismatch.*Resize\.new_size",
    ):
        walk(inst.a(), inst.b(), inst)


def test_walker_resize_wrapping_animated_component_raises():
    """Resize wrapping an animated subtree is rejected — its scale factor
    is bbox-dependent and would recompute per frame, producing
    size-jitter as the part rotates / translates."""
    from scadwright.ast.transforms import Resize
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return Resize(new_size=(10.0, 10.0, 10.0), child=self.box)

        @variant(default=True)
        def b(self):
            return Resize(new_size=(10.0, 10.0, 10.0), child=self.box.up(5))

    inst = D()
    with pytest.raises(
        ValidationError, match=r"(?s)animates inside a Resize.*size-jitter",
    ):
        walk(inst.a(), inst.b(), inst)


def test_walker_resize_wrapping_animated_inline_primitive_raises():
    """Inline primitive that animates inside a Resize: same prohibition
    as a Component, with the error tagged for inline geometry."""
    from scadwright.ast.transforms import Resize
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return union(self.box, Resize(new_size=(5.0, 5.0, 5.0), child=cube(3).up(10)))

        @variant(default=True)
        def b(self):
            return union(self.box, Resize(new_size=(5.0, 5.0, 5.0), child=cube(3).up(20)))

    inst = D()
    with pytest.raises(
        ValidationError, match=r"(?s)inline Cube animates inside a Resize",
    ):
        walk(inst.a(), inst.b(), inst)


def test_walker_resize_wrapping_static_content_is_fine():
    """Resize over geometry that's identical in both variants is purely
    static — the bbox is constant, the scale factor is constant, no
    size-jitter. Should pass through."""
    from scadwright.ast.transforms import Resize
    class D(Design):
        box = _Box()
        decor = _Lid()

        @variant()
        def a(self):
            # box animates; decor is wrapped in Resize but is static.
            return union(self.box, Resize(new_size=(20.0, 20.0, 5.0), child=self.decor))

        @variant(default=True)
        def b(self):
            return union(self.box.up(15), Resize(new_size=(20.0, 20.0, 5.0), child=self.decor))

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    # Only box animates; decor (under Resize) is static, doesn't appear in leaves.
    assert len(plan.leaves) == 1
    assert plan.leaves[0].display_name == "box"


def test_walker_resize_below_a_csg_still_catches_animation():
    """Resize doesn't need to be at the top of the tree; it can sit
    anywhere above an animated leaf and still trigger the error."""
    from scadwright.ast.transforms import Resize
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return union(Resize(new_size=(5.0, 5.0, 5.0), child=self.box))

        @variant(default=True)
        def b(self):
            return union(Resize(new_size=(5.0, 5.0, 5.0), child=self.box.up(8)))

    inst = D()
    with pytest.raises(
        ValidationError, match=r"(?s)animates inside a Resize",
    ):
        walk(inst.a(), inst.b(), inst)


def test_walker_different_projection_cut_raises():
    from scadwright.ast.transforms import Projection
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return Projection(child=self.box, cut=True)

        @variant(default=True)
        def b(self):
            return Projection(child=self.box, cut=False)

    inst = D()
    with pytest.raises(
        ValidationError, match=r"(?s)decoration mismatch.*Projection\.cut",
    ):
        walk(inst.a(), inst.b(), inst)


def test_walker_different_with_anchor_names_raises():
    """WithAnchor carries an anchor_name (str) and an Anchor (frozen
    dataclass) — the generic field comparison detects mismatches in
    either."""
    from scadwright.anchor import Anchor
    from scadwright.ast.transforms import WithAnchor
    a_left = Anchor(position=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0), kind="planar")

    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return WithAnchor(child=self.box, anchor_name="top", anchor=a_left)

        @variant(default=True)
        def b(self):
            return WithAnchor(child=self.box.up(5), anchor_name="bottom", anchor=a_left)

    inst = D()
    with pytest.raises(
        ValidationError, match=r"(?s)decoration mismatch.*WithAnchor\.anchor_name",
    ):
        walk(inst.a(), inst.b(), inst)


# ---------------------------------------------------------------------------
# Multiplicity via position-based pairing
# ---------------------------------------------------------------------------


def test_walker_multiplicity_pairs_by_tree_position():
    """`self.leg` referenced twice in union; pair by position."""
    class D(Design):
        leg = _Box()

        @variant()
        def a(self):
            return union(self.leg.up(0), self.leg.up(10))

        @variant(default=True)
        def b(self):
            return union(self.leg.up(50), self.leg.up(60))

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    assert len(plan.leaves) == 2
    z_pairs = sorted(
        (leaf.M_a.translation[2], leaf.M_b.translation[2])
        for leaf in plan.leaves
    )
    assert z_pairs == [(0.0, 50.0), (10.0, 60.0)]


# ---------------------------------------------------------------------------
# Hull (a structural node we want to support)
# ---------------------------------------------------------------------------


def test_walker_part_inside_hull_animates():
    class D(Design):
        a_part = _Box()
        b_part = _Box()

        @variant()
        def first(self):
            return hull(self.a_part, self.b_part.up(20))

        @variant(default=True)
        def second(self):
            return hull(self.a_part, self.b_part.up(30))

    inst = D()
    plan = walk(inst.first(), inst.second(), inst)
    assert len(plan.leaves) == 1
    assert plan.leaves[0].display_name == "b_part"
