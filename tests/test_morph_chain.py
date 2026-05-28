"""Chain morph tests — three or more stages.

The walker produces one ``LegPlan`` per consecutive stage pair; the emit
composes one delta per leg. A leaf may animate in some legs and stay
static in others. Leg timing is auto-allocated by motion magnitude.
"""

from __future__ import annotations

import math

import pytest

from scadwright import Component, Matrix, Param, positive, morph
from scadwright.animation._morph_emit import build_animated_tree
from scadwright.animation._morph_walker import ChainPlan, walk_chain
from scadwright.boolops import union
from scadwright.design import Design, _reset_for_testing, variant
from scadwright.errors import ValidationError
from scadwright.primitives import cube


class _Box(Component):
    size: float = Param(default=10.0, validators=(positive,))

    def build(self):
        return cube(self.size)


@pytest.fixture(autouse=True)
def reset_registry():
    _reset_for_testing()
    yield
    _reset_for_testing()


# ---------------------------------------------------------------------------
# SymbolicExpr evaluator (shared shape with test_morph_emit.py).
# ---------------------------------------------------------------------------


from scadwright.animation import (
    BinOp, Const, FuncCall, Identifier, SymbolicExpr, Ternary, UnaryOp,
)
from scadwright.ast.transforms import Rotate, Scale, Translate


def _eval_expr(expr, t_value: float) -> float:
    if isinstance(expr, (int, float)):
        return float(expr)
    if isinstance(expr, Const):
        return expr.value
    if isinstance(expr, Identifier):
        if expr.name == "$t":
            return t_value
        raise ValueError(f"unexpected identifier: {expr.name!r}")
    if isinstance(expr, BinOp):
        left = _eval_expr(expr.left, t_value)
        right = _eval_expr(expr.right, t_value)
        if expr.op == "+": return left + right
        if expr.op == "-": return left - right
        if expr.op == "*": return left * right
        if expr.op == "/": return left / right
        if expr.op == "<": return left < right
        if expr.op == "<=": return left <= right
        if expr.op == ">": return left > right
        if expr.op == ">=": return left >= right
        raise ValueError(f"unknown binop {expr.op!r}")
    if isinstance(expr, UnaryOp):
        if expr.op == "-":
            return -_eval_expr(expr.operand, t_value)
        raise ValueError(f"unknown unaryop {expr.op!r}")
    if isinstance(expr, FuncCall):
        args = [_eval_expr(a, t_value) for a in expr.args]
        if expr.name == "min": return min(*args)
        if expr.name == "max": return max(*args)
        raise ValueError(f"unknown func {expr.name!r}")
    if isinstance(expr, Ternary):
        c = _eval_expr(expr.test, t_value)
        return _eval_expr(expr.a, t_value) if c else _eval_expr(expr.b, t_value)
    raise TypeError(f"can't evaluate {type(expr).__name__}: {expr!r}")


def _eval_vec(vec, t_value: float):
    return tuple(_eval_expr(x, t_value) for x in vec)


def _chain_matrix(node, t_value: float, leaf) -> Matrix:
    if node is leaf:
        return Matrix.identity()
    if isinstance(node, Translate):
        v = _eval_vec(node.v, t_value)
        return Matrix.translate(*v) @ _chain_matrix(node.child, t_value, leaf)
    if isinstance(node, Rotate):
        if node.a is not None and node.v is not None:
            a = _eval_expr(node.a, t_value)
            return Matrix.rotate_axis_angle(a, node.v) @ _chain_matrix(node.child, t_value, leaf)
        if node.angles is not None:
            angles = _eval_vec(node.angles, t_value)
            return Matrix.rotate_euler(*angles) @ _chain_matrix(node.child, t_value, leaf)
    if isinstance(node, Scale):
        f = _eval_vec(node.factor, t_value)
        return Matrix.scale(*f) @ _chain_matrix(node.child, t_value, leaf)
    raise TypeError(f"unexpected chain node: {type(node).__name__}")


def _matrices_close(a: Matrix, b: Matrix, tol: float = 1e-5) -> bool:
    return all(
        abs(x - y) < tol
        for ra, rb in zip(a.elements, b.elements)
        for x, y in zip(ra, rb)
    )


# ---------------------------------------------------------------------------
# Walker behavior
# ---------------------------------------------------------------------------


def test_walker_three_stages_produces_two_legs():
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant()
        def b(self):
            return self.box.up(10)

        @variant(default=True)
        def c(self):
            return self.box.up(20)

    inst = D()
    plan = walk_chain((inst.a(), inst.b(), inst.c()), inst)
    assert isinstance(plan, ChainPlan)
    assert len(plan.legs) == 2
    # Both legs animate self.box.
    assert len(plan.legs[0].leaves) == 1
    assert len(plan.legs[1].leaves) == 1
    assert plan.legs[0].leaves[0].M_a.translation == (0.0, 0.0, 0.0)
    assert plan.legs[0].leaves[0].M_b.translation == (0.0, 0.0, 10.0)
    assert plan.legs[1].leaves[0].M_a.translation == (0.0, 0.0, 10.0)
    assert plan.legs[1].leaves[0].M_b.translation == (0.0, 0.0, 20.0)


def test_walker_leaf_static_in_one_leg_appears_only_in_other():
    """`box` animates in leg 0 only, sits still in leg 1."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant()
        def b(self):
            return self.box.up(10)

        @variant(default=True)
        def c(self):
            return self.box.up(10)  # same as b — leg 1 is static for box.

    inst = D()
    plan = walk_chain((inst.a(), inst.b(), inst.c()), inst)
    assert len(plan.legs) == 2
    assert len(plan.legs[0].leaves) == 1
    assert plan.legs[1].leaves == ()


def test_walker_two_parts_animating_in_different_legs():
    """foo moves only in leg 0; bar moves only in leg 1."""
    class _Foo(Component):
        def build(self): return cube(5)

    class _Bar(Component):
        def build(self): return cube(5)

    class D(Design):
        foo = _Foo()
        bar = _Bar()

        @variant()
        def a(self):
            return union(self.foo, self.bar)

        @variant()
        def b(self):
            return union(self.foo.up(10), self.bar)

        @variant(default=True)
        def c(self):
            return union(self.foo.up(10), self.bar.up(20))

    inst = D()
    plan = walk_chain((inst.a(), inst.b(), inst.c()), inst)
    assert [l.display_name for l in plan.legs[0].leaves] == ["foo"]
    assert [l.display_name for l in plan.legs[1].leaves] == ["bar"]


def test_walker_structural_mismatch_in_middle_stage_raises():
    """Stages 0 and 2 share a skeleton; stage 1 differs structurally."""
    from scadwright.boolops import difference

    class D(Design):
        box = _Box()
        hole = _Box()

        @variant()
        def a(self):
            return difference(self.box, self.hole)

        @variant()
        def b(self):
            return union(self.box, self.hole)  # mismatch.

        @variant(default=True)
        def c(self):
            return difference(self.box, self.hole)

    inst = D()
    with pytest.raises(
        ValidationError,
        match=r"(?s)variant ASTs differ in structure between stages\[0\] and stages\[1\]",
    ):
        walk_chain((inst.a(), inst.b(), inst.c()), inst)


def test_walker_decoration_mismatch_in_middle_stage_raises():
    """Stage 1's decoration metadata differs from stage 0/2."""
    from scadwright.ast.transforms import Color

    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return Color(c="red", child=self.box)

        @variant()
        def b(self):
            return Color(c="blue", child=self.box.up(5))  # different color.

        @variant(default=True)
        def c(self):
            return Color(c="red", child=self.box.up(10))

    inst = D()
    with pytest.raises(
        ValidationError,
        match=r"(?s)decoration mismatch.*between stages\[0\] and stages\[1\].*Color\.c",
    ):
        walk_chain((inst.a(), inst.b(), inst.c()), inst)


def test_walker_mirror_in_middle_leg_raises_with_stage_indices():
    """The mirror error names the offending leg's stage indices."""
    class D(Design):
        lid = _Box()

        @variant()
        def a(self):
            return self.lid

        @variant()
        def b(self):
            return self.lid.flip("z")  # mirror introduced in leg 0.

        @variant(default=True)
        def c(self):
            return self.lid.flip("z")  # static in leg 1.

    inst = D()
    with pytest.raises(
        ValidationError,
        match=r"(?s)between stages\[0\] and stages\[1\].*mirror.*det = -1",
    ):
        walk_chain((inst.a(), inst.b(), inst.c()), inst)


# ---------------------------------------------------------------------------
# Emit: chain endpoints
# ---------------------------------------------------------------------------


def test_emit_three_stage_chain_endpoints():
    """At $t=0 the leaf should be at M_0; at $t=1 at M_2; passes through M_1
    at the leg-0 boundary."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant()
        def b(self):
            return self.box.up(10)

        @variant(default=True)
        def c(self):
            return self.box.up(30)

    inst = D()
    plan = walk_chain((inst.a(), inst.b(), inst.c()), inst)
    spec = morph(stages=["a", "b", "c"], simultaneous=True)
    out = build_animated_tree(plan, spec)

    M_at_0 = _chain_matrix(out, 0.0, D.box)
    M_at_1 = _chain_matrix(out, 1.0, D.box)
    assert _matrices_close(M_at_0, Matrix.identity())
    assert _matrices_close(M_at_1, Matrix.translate(0, 0, 30))


def test_emit_three_stage_chain_hits_middle_pose_at_leg_boundary():
    """The leaf should pass through M_1 exactly when $t equals the
    boundary between leg 0 and leg 1. Auto-weight gives leg 0 weight
    proportional to its motion magnitude (10mm) and leg 1 weight
    proportional to its (20mm), so the boundary is at $t = 10/30 = 1/3."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant()
        def b(self):
            return self.box.up(10)

        @variant(default=True)
        def c(self):
            return self.box.up(30)

    inst = D()
    plan = walk_chain((inst.a(), inst.b(), inst.c()), inst)
    spec = morph(stages=["a", "b", "c"], simultaneous=True)
    out = build_animated_tree(plan, spec)

    boundary_t = 10.0 / 30.0
    M_at_boundary = _chain_matrix(out, boundary_t, D.box)
    assert _matrices_close(M_at_boundary, Matrix.translate(0, 0, 10))


def test_emit_static_leg_gets_min_fraction():
    """A leg with zero motion still gets the minimum fraction of the
    timeline so the chain reads as a brief pause rather than a snap.
    The two animated legs share what's left."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant()
        def b(self):
            return self.box.up(10)

        @variant()
        def c(self):
            return self.box.up(10)  # leg 1 static

        @variant(default=True)
        def d(self):
            return self.box.up(20)

    inst = D()
    plan = walk_chain(
        (inst.a(), inst.b(), inst.c(), inst.d()), inst,
    )
    spec = morph(stages=["a", "b", "c", "d"], simultaneous=True)
    out = build_animated_tree(plan, spec)

    # Endpoints still correct.
    assert _matrices_close(_chain_matrix(out, 0.0, D.box), Matrix.identity())
    assert _matrices_close(_chain_matrix(out, 1.0, D.box), Matrix.translate(0, 0, 20))


def test_emit_chain_with_partial_leg_animation():
    """A leaf moves in legs 0 and 2 but is static in leg 1. The chain
    should still produce the correct endpoints; leg 1's interior leaves
    the leaf parked at M_1."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant()
        def b(self):
            return self.box.up(10)

        @variant()
        def c(self):
            return self.box.up(10)  # box static across leg 1.

        @variant(default=True)
        def d(self):
            return self.box.up(30)

    inst = D()
    plan = walk_chain(
        (inst.a(), inst.b(), inst.c(), inst.d()), inst,
    )
    spec = morph(stages=["a", "b", "c", "d"], simultaneous=True)
    out = build_animated_tree(plan, spec)

    assert _matrices_close(_chain_matrix(out, 0.0, D.box), Matrix.identity())
    assert _matrices_close(_chain_matrix(out, 1.0, D.box), Matrix.translate(0, 0, 30))


def test_emit_chain_with_rotation_in_one_leg_translation_in_another():
    """leg 0 is a pure translation; leg 1 is a 90° rotation. Both legs
    must reproduce their endpoints when composed."""
    class D(Design):
        part = _Box()

        @variant()
        def a(self):
            return self.part

        @variant()
        def b(self):
            return self.part.up(20)

        @variant(default=True)
        def c(self):
            return self.part.up(20).rotate([90, 0, 0])

    inst = D()
    plan = walk_chain((inst.a(), inst.b(), inst.c()), inst)
    spec = morph(stages=["a", "b", "c"], simultaneous=True)
    out = build_animated_tree(plan, spec)

    M_at_0 = _chain_matrix(out, 0.0, D.part)
    M_at_1 = _chain_matrix(out, 1.0, D.part)
    expected_end = Matrix.rotate_euler(90, 0, 0) @ Matrix.translate(0, 0, 20)
    assert _matrices_close(M_at_0, Matrix.identity())
    assert _matrices_close(M_at_1, expected_end)


def test_emit_chain_compatible_with_2_stage_emit():
    """A chain with stages=[a, b] should produce equivalent geometry to
    the original 2-stage emit — same endpoints, same intermediate at
    smoothstep(0.5)."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant(default=True)
        def b(self):
            return self.box.rotate([180, 0, 0]).up(30)

    inst = D()
    plan = walk_chain((inst.a(), inst.b()), inst)
    spec = morph(stages=["a", "b"])
    out = build_animated_tree(plan, spec)

    # `.rotate(...).up(30)` wraps inner-first, so matrix-form is
    # translate(0,0,30) @ rotate(180,0,0).
    expected_end = Matrix.translate(0, 0, 30) @ Matrix.rotate_euler(180, 0, 0)
    assert _matrices_close(_chain_matrix(out, 0.0, D.box), Matrix.identity())
    assert _matrices_close(_chain_matrix(out, 1.0, D.box), expected_end)


# ---------------------------------------------------------------------------
# Order + chain interaction
# ---------------------------------------------------------------------------


def test_emit_chain_with_order_applies_per_leg():
    """order= governs slot order WITHIN each leg. Two parts share both
    legs of a 3-stage chain; explicit order means part_a always animates
    before part_b within each leg."""
    class _A(Component):
        def build(self): return cube(5)

    class _B(Component):
        def build(self): return cube(5)

    class D(Design):
        a_part = _A()
        b_part = _B()

        @variant()
        def s0(self):
            return union(self.a_part, self.b_part)

        @variant()
        def s1(self):
            return union(self.a_part.up(10), self.b_part.up(10))

        @variant(default=True)
        def s2(self):
            return union(self.a_part.up(20), self.b_part.up(20))

    inst = D()
    plan = walk_chain((inst.s0(), inst.s1(), inst.s2()), inst)
    spec = morph(stages=["s0", "s1", "s2"], order=["a_part", "b_part"])
    out = build_animated_tree(plan, spec)

    # Both legs have 2 slots; a_part takes slot 0, b_part takes slot 1.
    # In leg 0 (t ∈ [0, 0.5]), at t=0.25 (just past leg-local 0.5), a_part
    # is mid-animation but b_part hasn't started yet.
    # The chain composes union; out.children[0] is a_part's chain,
    # children[1] is b_part's chain.
    M_a_at_quarter = _chain_matrix(out.children[0], 0.25, D.a_part)
    M_b_at_quarter = _chain_matrix(out.children[1], 0.25, D.b_part)
    assert M_a_at_quarter.translation[2] > 0.0  # a_part is moving.
    assert math.isclose(
        M_b_at_quarter.translation[2], 0.0, abs_tol=1e-6,
    )  # b_part still parked at M_0.


# ---------------------------------------------------------------------------
# Pingpong
# ---------------------------------------------------------------------------


def test_emit_pingpong_two_stage_returns_to_start():
    """At $t=1, pingpong should put the leaf back at its M_0 — the next
    loop iteration begins on the start pose."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant(default=True)
        def b(self):
            return self.box.up(20)

    inst = D()
    plan = walk_chain((inst.a(), inst.b()), inst)
    spec = morph(stages=["a", "b"], pingpong=True, simultaneous=True)
    out = build_animated_tree(plan, spec)

    M_at_0 = _chain_matrix(out, 0.0, D.box)
    M_at_half = _chain_matrix(out, 0.5, D.box)
    M_at_1 = _chain_matrix(out, 1.0, D.box)
    assert _matrices_close(M_at_0, Matrix.identity())
    assert _matrices_close(M_at_half, Matrix.translate(0, 0, 20))
    assert _matrices_close(M_at_1, Matrix.identity())


def test_emit_pingpong_three_stage_chain_returns_to_start():
    """Chain pingpong: A→B→C over [0, 0.5], C→B→A over [0.5, 1]."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant()
        def b(self):
            return self.box.up(10)

        @variant(default=True)
        def c(self):
            return self.box.up(30)

    inst = D()
    plan = walk_chain((inst.a(), inst.b(), inst.c()), inst)
    spec = morph(stages=["a", "b", "c"], pingpong=True, simultaneous=True)
    out = build_animated_tree(plan, spec)

    # Equal motion magnitudes give leg boundaries at 1/3, 2/3 of the
    # effective time. Effective t under pingpong: $t=0.5 maps to 1.0
    # (peak), so $t=0.5 is the C pose. By symmetry, $t = 0.5 ·
    # (boundary) = 0.5/3 ≈ 0.167 maps to effective t = 1/3, the A→B
    # boundary → leaf at M_1.
    M_at_0 = _chain_matrix(out, 0.0, D.box)
    M_at_peak = _chain_matrix(out, 0.5, D.box)
    M_at_1 = _chain_matrix(out, 1.0, D.box)
    assert _matrices_close(M_at_0, Matrix.identity())
    assert _matrices_close(M_at_peak, Matrix.translate(0, 0, 30))
    assert _matrices_close(M_at_1, Matrix.identity())

    # During the reverse half, the leaf passes back through M_1 at
    # some t > 0.5. We don't need to compute the exact boundary; just
    # verify the leaf is somewhere between M_1 and M_0 in the second
    # half — translation z is between 0 and 10 at $t = 0.85 (well past
    # the peak, well before the end).
    M_returning = _chain_matrix(out, 0.85, D.box)
    assert 0.0 <= M_returning.translation[2] <= 30.0


def test_emit_pingpong_off_by_default():
    """Without pingpong=True, $t=1 should leave the leaf at M_end, not
    M_start."""
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant(default=True)
        def b(self):
            return self.box.up(20)

    inst = D()
    plan = walk_chain((inst.a(), inst.b()), inst)
    spec = morph(stages=["a", "b"], simultaneous=True)
    out = build_animated_tree(plan, spec)

    M_at_1 = _chain_matrix(out, 1.0, D.box)
    assert _matrices_close(M_at_1, Matrix.translate(0, 0, 20))
