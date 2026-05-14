"""Emit chain tests: screw motion, SRT fallback, pure translation,
ordering, alpha expression, substitution.

Verifies that the animated chain produces M_a at $t=0 and M_b at $t=1.
Uses an inline SymbolicExpr evaluator (a small interpreter over the
emit-tree types) to compute concrete matrices at each endpoint without
shelling out to OpenSCAD.
"""

from __future__ import annotations

import math

import pytest

from scadwright import Component, Matrix, Param, positive, morph
from scadwright.animation import (
    BinOp, Const, FuncCall, Identifier, SymbolicExpr, Ternary, UnaryOp,
)
from scadwright.animation._morph_emit import build_animated_tree
from scadwright.animation._morph_walker import walk
from scadwright.ast.csg import Union
from scadwright.ast.transforms import Rotate, Scale, Translate
from scadwright.design import Design, _reset_for_testing, variant
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
# SymbolicExpr evaluator (test-only)
# ---------------------------------------------------------------------------


def _eval_expr(expr, t_value: float) -> float:
    """Evaluate a SymbolicExpr (or float) at $t = t_value."""
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
        if expr.op == "+":
            return left + right
        if expr.op == "-":
            return left - right
        if expr.op == "*":
            return left * right
        if expr.op == "/":
            return left / right
        raise ValueError(f"unknown binop {expr.op!r}")
    if isinstance(expr, UnaryOp):
        operand = _eval_expr(expr.operand, t_value)
        if expr.op == "-":
            return -operand
        raise ValueError(f"unknown unaryop {expr.op!r}")
    if isinstance(expr, FuncCall):
        args = [_eval_expr(a, t_value) for a in expr.args]
        if expr.name == "min":
            return min(*args)
        if expr.name == "max":
            return max(*args)
        raise ValueError(f"unknown function {expr.name!r}")
    if isinstance(expr, Ternary):
        cond = _eval_expr(expr.test, t_value)
        return _eval_expr(expr.a, t_value) if cond else _eval_expr(expr.b, t_value)
    raise TypeError(f"can't evaluate {type(expr).__name__}: {expr!r}")


def _eval_vec(vec, t_value: float) -> tuple[float, float, float]:
    return tuple(_eval_expr(x, t_value) for x in vec)


def _chain_matrix(node, t_value: float, leaf) -> Matrix:
    """Walk the animated chain rooted at ``node`` down to ``leaf``,
    composing the transform matrices encountered. Returns the matrix
    representing the cumulative transform applied to ``leaf`` at the
    given $t."""
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


def _matrices_close(a: Matrix, b: Matrix, tol: float = 1e-6) -> bool:
    return all(
        abs(x - y) < tol
        for ra, rb in zip(a.elements, b.elements)
        for x, y in zip(ra, rb)
    )


# ---------------------------------------------------------------------------
# Static morph (no leaves animate)
# ---------------------------------------------------------------------------


def test_emit_no_animation_returns_tree_a_unchanged():
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
    spec = morph(start="a", end="b")
    out = build_animated_tree(plan, spec)
    assert out is plan.tree_a


# ---------------------------------------------------------------------------
# Pure translation: chain at $t=0 and $t=1 reproduces M_a and M_b
# ---------------------------------------------------------------------------


def test_emit_pure_translation_endpoints():
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant(default=True)
        def b(self):
            return self.box.up(20)

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    spec = morph(start="a", end="b")
    out = build_animated_tree(plan, spec)

    # The animated chain replaces self.box (the substitution root). Find
    # the chain and verify it composes to M_a at $t=0 and M_b at $t=1.
    leaf = D.box
    M_at_0 = _chain_matrix(out, 0.0, leaf)
    M_at_1 = _chain_matrix(out, 1.0, leaf)
    assert _matrices_close(M_at_0, Matrix.identity())
    assert _matrices_close(M_at_1, Matrix.translate(0, 0, 20))


def test_emit_pure_translation_intermediate_is_lerp():
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant(default=True)
        def b(self):
            return self.box.up(20)

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    spec = morph(start="a", end="b", simultaneous=True)
    out = build_animated_tree(plan, spec)
    # At $t=0.5 the eased alpha smoothstep(0.5) = 0.5; translation should be (0, 0, 10).
    M_at_half = _chain_matrix(out, 0.5, D.box)
    assert math.isclose(M_at_half.translation[2], 10.0, abs_tol=1e-6)


# ---------------------------------------------------------------------------
# Screw motion: rotation + translation, endpoints correct
# ---------------------------------------------------------------------------


def test_emit_screw_180_endpoints():
    """The hinge-swing canonical case: 180° rotation about X + translation
    in Y. The chain should reproduce M_a (no rotation) at t=0 and M_b
    (rotated 180° about X, translated) at t=1."""
    from scadwright.ast.transforms import Rotate as RotateAST
    class D(Design):
        lid = _Box()

        @variant()
        def a(self):
            return self.lid

        @variant(default=True)
        def b(self):
            # Equivalent to flip-over-and-translate, but expressed as a
            # rotation so the morph can animate it.
            return self.lid.up(30).rotate([180, 0, 0])

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    spec = morph(start="a", end="b")
    out = build_animated_tree(plan, spec)

    M_at_0 = _chain_matrix(out, 0.0, D.lid)
    M_at_1 = _chain_matrix(out, 1.0, D.lid)
    expected_b = Matrix.rotate_euler(180, 0, 0) @ Matrix.translate(0, 0, 30)
    assert _matrices_close(M_at_0, Matrix.identity())
    assert _matrices_close(M_at_1, expected_b)


def test_emit_screw_90_endpoints():
    from scadwright.ast.transforms import Rotate as RotateAST
    class D(Design):
        part = _Box()

        @variant()
        def a(self):
            return self.part

        @variant(default=True)
        def b(self):
            return self.part.up(20).rotate([90, 0, 0])

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    spec = morph(start="a", end="b")
    out = build_animated_tree(plan, spec)
    M_at_0 = _chain_matrix(out, 0.0, D.part)
    M_at_1 = _chain_matrix(out, 1.0, D.part)
    expected_b = Matrix.rotate_euler(90, 0, 0) @ Matrix.translate(0, 0, 20)
    assert _matrices_close(M_at_0, Matrix.identity())
    assert _matrices_close(M_at_1, expected_b)


def test_emit_screw_180_traces_an_arc_not_a_straight_line():
    """For a 180° morph, the mid-arc point should be off the straight-line
    interpolation between start and end positions. (The straight-line
    midpoint would be at (0, 0, 0); the arc midpoint should be at
    nonzero y, on a circle around the screw axis through P.)"""
    class D(Design):
        lid = _Box()

        @variant()
        def a(self):
            return self.lid

        @variant(default=True)
        def b(self):
            # M_b = translate(0, 0, 30) @ rotate_x(180). Lid ends at z=30,
            # upside down. The straight-line midpoint of (0,0,0)→(0,0,30)
            # is (0, 0, 15). The arc midpoint should be at (0, ±15, 15) —
            # off the straight line by 15 units in y.
            return self.lid.rotate([180, 0, 0]).up(30)

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    spec = morph(start="a", end="b")
    out = build_animated_tree(plan, spec)
    M_at_half = _chain_matrix(out, 0.5, D.lid)
    mid_pos = M_at_half.apply_point((0.0, 0.0, 0.0))
    # The mid-arc must lie off the line connecting the endpoints. Since
    # the rotation is about X, the deviation is in the YZ plane; the line
    # is along z, so |y_mid| should be ~15 (the arc radius).
    assert abs(mid_pos[1]) > 10.0
    # The midpoint z should land near the straight-line midpoint of z's
    # (here, 15) — the arc passes through that z, but at offset in y.
    assert math.isclose(mid_pos[2], 15.0, abs_tol=1e-6)


def test_emit_screw_180_sign_choice_is_deterministic():
    """Running the morph build twice should pick the same arc — no
    nondeterminism in the heuristic."""
    class D(Design):
        lid = _Box()

        @variant()
        def a(self):
            return self.lid

        @variant(default=True)
        def b(self):
            return self.lid.rotate([180, 0, 0]).up(30)

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    spec = morph(start="a", end="b")
    out_1 = build_animated_tree(plan, spec)
    out_2 = build_animated_tree(plan, spec)
    mid_1 = _chain_matrix(out_1, 0.5, D.lid).apply_point((0.0, 0.0, 0.0))
    mid_2 = _chain_matrix(out_2, 0.5, D.lid).apply_point((0.0, 0.0, 0.0))
    for a, b in zip(mid_1, mid_2):
        assert math.isclose(a, b, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# SRT fallback for corkscrew-dominated motions
# ---------------------------------------------------------------------------


def test_emit_srt_fallback_endpoints():
    """A small rotation combined with large parallel-to-axis translation
    triggers the SRT fallback. Check that endpoints still work."""
    from scadwright.ast.transforms import Translate as TranslateAST
    class D(Design):
        part = _Box()

        @variant()
        def a(self):
            return self.part

        @variant(default=True)
        def b(self):
            # Rotate slightly about Z; translate heavily along Z (parallel
            # to the rotation axis). Pitch dominates → SRT fallback.
            return self.part.up(100).rotate([0, 0, 10])

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    spec = morph(start="a", end="b")
    out = build_animated_tree(plan, spec)
    M_at_0 = _chain_matrix(out, 0.0, D.part)
    M_at_1 = _chain_matrix(out, 1.0, D.part)
    expected_b = Matrix.rotate_euler(0, 0, 10) @ Matrix.translate(0, 0, 100)
    assert _matrices_close(M_at_0, Matrix.identity(), tol=1e-5)
    assert _matrices_close(M_at_1, expected_b, tol=1e-5)


# ---------------------------------------------------------------------------
# Alpha expression: smoothstep + clamp behaviour
# ---------------------------------------------------------------------------


def test_emit_simultaneous_alpha_smoothstep_at_half():
    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return self.box

        @variant(default=True)
        def b(self):
            return self.box.up(10)

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    spec = morph(start="a", end="b", simultaneous=True)
    out = build_animated_tree(plan, spec)
    M_at_quarter = _chain_matrix(out, 0.25, D.box)
    # smoothstep(0.25) = 0.0625·(3 − 0.5) = 0.15625; translation should be ~1.5625.
    assert math.isclose(M_at_quarter.translation[2], 10 * 0.15625, abs_tol=1e-6)


def test_emit_one_at_a_time_slot_boundaries():
    """Two parts at different display_names → two slots. Part 0 finishes
    its animation by $t = 0.5; part 1 hasn't started until $t = 0.5."""
    class _Foo(Component):
        def build(self): return cube(5)

    class _Bar(Component):
        def build(self): return cube(5)

    class D(Design):
        foo = _Foo()
        bar = _Bar()

        @variant()
        def a(self):
            from scadwright.boolops import union
            return union(self.foo, self.bar.up(0))

        @variant(default=True)
        def b(self):
            from scadwright.boolops import union
            return union(self.foo.up(10), self.bar.up(10))

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    spec = morph(
        start="a", end="b",
        order=["foo", "bar"],  # foo first, bar second
        simultaneous=False,
    )
    out = build_animated_tree(plan, spec)
    # At $t = 0.5, foo should be at its end position (slot 0 ends at 0.5),
    # bar should be at its start (slot 1 hasn't started).
    M_foo_half = _chain_matrix(out.children[0], 0.5, D.foo)
    M_bar_half = _chain_matrix(out.children[1], 0.5, D.bar)
    assert math.isclose(M_foo_half.translation[2], 10.0, abs_tol=1e-6)
    assert math.isclose(M_bar_half.translation[2], 0.0, abs_tol=1e-6)


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def test_emit_default_order_destination_z_ascending():
    class _Lo(Component):
        def build(self): return cube(5)

    class _Hi(Component):
        def build(self): return cube(5)

    class D(Design):
        hi = _Hi()
        lo = _Lo()

        @variant()
        def a(self):
            from scadwright.boolops import union
            return union(self.hi, self.lo)

        @variant(default=True)
        def b(self):
            from scadwright.boolops import union
            # lo ends up at z=10, hi ends up at z=50; default order is by
            # destination-z ascending so lo is slot 0, hi is slot 1.
            return union(self.hi.up(50), self.lo.up(10))

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    spec = morph(start="a", end="b")
    out = build_animated_tree(plan, spec)
    # At $t = 0.4, lo's slot [0, 0.5] is in its second half (eased), hi
    # hasn't started yet.
    M_lo_at_t = _chain_matrix(out.children[1], 0.4, D.lo)
    M_hi_at_t = _chain_matrix(out.children[0], 0.4, D.hi)
    assert M_lo_at_t.translation[2] > 0.0  # lo is moving
    assert math.isclose(M_hi_at_t.translation[2], 0.0, abs_tol=1e-6)  # hi static


def test_emit_explicit_order_respected():
    class _A(Component):
        def build(self): return cube(5)

    class _B(Component):
        def build(self): return cube(5)

    class D(Design):
        a_part = _A()
        b_part = _B()

        @variant()
        def first(self):
            from scadwright.boolops import union
            return union(self.a_part, self.b_part)

        @variant(default=True)
        def second(self):
            from scadwright.boolops import union
            # If we left it to the default destination-z ordering, b_part
            # (z=5) would go before a_part (z=20). The explicit order=
            # below should override.
            return union(self.a_part.up(20), self.b_part.up(5))

    inst = D()
    plan = walk(inst.first(), inst.second(), inst)
    spec = morph(start="first", end="second", order=["a_part", "b_part"])
    out = build_animated_tree(plan, spec)
    # At $t = 0.4: a_part should already be moving (slot 0 of 2 runs [0, 0.5]).
    M_a_at_t = _chain_matrix(out.children[0], 0.4, D.a_part)
    M_b_at_t = _chain_matrix(out.children[1], 0.4, D.b_part)
    assert M_a_at_t.translation[2] > 0.0
    assert math.isclose(M_b_at_t.translation[2], 0.0, abs_tol=1e-6)


# ---------------------------------------------------------------------------
# Tree substitution preserves structure
# ---------------------------------------------------------------------------


def test_emit_preserves_difference_structure():
    """`difference(self.body, self.hole.up(5))` morph: the output should
    STILL be a Difference, with self.body unchanged and self.hole replaced
    by its animated chain."""
    from scadwright.ast.csg import Difference

    class D(Design):
        body = _Box()
        hole = _Box()

        @variant()
        def a(self):
            from scadwright.boolops import difference
            return difference(self.body, self.hole.up(5))

        @variant(default=True)
        def b(self):
            from scadwright.boolops import difference
            return difference(self.body, self.hole.up(10))

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    spec = morph(start="a", end="b")
    out = build_animated_tree(plan, spec)
    assert isinstance(out, Difference)
    # The first child is self.body (unchanged); the second child is the
    # animated chain.
    assert out.children[0] is D.body
    # At t=0, the animated chain on the cutter side reproduces the
    # original .up(5) position.
    M_hole_at_0 = _chain_matrix(out.children[1], 0.0, D.hole)
    M_hole_at_1 = _chain_matrix(out.children[1], 1.0, D.hole)
    assert _matrices_close(M_hole_at_0, Matrix.translate(0, 0, 5))
    assert _matrices_close(M_hole_at_1, Matrix.translate(0, 0, 10))


def test_emit_preserves_color_decoration():
    from scadwright.ast.transforms import Color

    class D(Design):
        box = _Box()

        @variant()
        def a(self):
            return Color(c="red", child=self.box)

        @variant(default=True)
        def b(self):
            return Color(c="red", child=self.box.up(20))

    inst = D()
    plan = walk(inst.a(), inst.b(), inst)
    spec = morph(start="a", end="b")
    out = build_animated_tree(plan, spec)
    # Color stays at the root.
    assert isinstance(out, Color)
    assert out.c == "red"
    # The child is the animated chain.
    M_at_1 = _chain_matrix(out.child, 1.0, D.box)
    assert _matrices_close(M_at_1, Matrix.translate(0, 0, 20))
