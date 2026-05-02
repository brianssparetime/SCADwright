"""Equation-DSL stress: resolver code-path coverage.

Phase 2 of design_docs/MajorReview4_tests.md. Each test targets a
specific branch of the iterative resolver so a regression in that branch
fires here, even when the user-facing surface still sort of works.

Groups (from the doc):
- D: trig + multi-root + feasibility filter
- E: min/max/abs in solver position
- H: system-solve + feasibility
- J: solver postponement / multi-pass
- K: class-define-time validation interactions
- L: cross-Component publishing under stress

Failure here usually points at one of:
- ``IterativeResolver._sympy_solve_one`` (single-eq sympy + filter)
- ``IterativeResolver._system_solve`` (system sympy + filter)
- ``IterativeResolver._filter_by_feasibility`` (single-target propagate)
- ``IterativeResolver._filter_systems_by_feasibility`` (dict-of-targets propagate)
- ``IterativeResolver._preresolve_overrides`` (override pre-resolve before iteration)
- ``IterativeResolver._try_resolve_equation`` (forward-eval, postponement)
- ``parse_equations_unified``'s class-def-time checks
"""

from __future__ import annotations

import math
from collections import namedtuple

import pytest

from scadwright import Component, Param
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# =============================================================================
# Group D — trig + multi-root + feasibility filter
# =============================================================================


def test_D1_asin_two_roots_disambiguated_by_per_param_bound():
    """`theta = asin(d / r)` returns θ ∈ [-90, 90]; sympy hands back
    one solution but verify it lands in the validated range.
    """
    class C(Component):
        equations = [
            "r > 0",
            "d > 0",
            "theta > 0",
            "theta < 90",
            "d = r * sin(theta)",
        ]

        def build(self):
            return cube(1)

    c = C(r=10, d=5)
    assert 0 < c.theta < 90
    assert c.theta == pytest.approx(30.0, abs=1e-3)


def test_D2_double_angle_disambiguated_by_cross_constraint():
    """`max_d = 2 * groove_depth * sin(half_angle)` and
    `angle = 2 * half_angle` with `angle < 180` rules out the second
    branch of the asin solve. Targets ``_filter_by_feasibility`` which
    propagates the candidate forward through the equation system.
    """
    class C(Component):
        equations = [
            "max_d, groove_depth, angle, half_angle > 0",
            "angle < 180",
            "max_d = 2 * groove_depth * sin(half_angle)",
            "angle = 2 * half_angle",
        ]

        def build(self):
            return cube(1)

    p = C(max_d=35, groove_depth=22)
    assert p.half_angle == pytest.approx(52.6982, rel=1e-3)
    assert p.angle == pytest.approx(105.396, rel=1e-3)
    assert p.angle < 180


def test_D3_quadratic_positivity_filter_picks_root():
    """`area = pi * r**2` has roots ±sqrt(area/pi); positivity validator
    on `r` filters down to one. Targets _filter_by_validators."""
    class C(Component):
        area = Param(float, positive=True)
        r = Param(float, positive=True)
        equations = ["area = pi * r**2"]

        def build(self):
            return cube(1)

    c = C(area=math.pi * 9)
    assert c.r == pytest.approx(3.0)


def test_D4_quadratic_with_no_satisfying_root_raises():
    """Both ±sqrt branches fail the validator → 'no candidate' error.
    Pin the error path of _filter_by_feasibility / validators."""
    class C(Component):
        equations = [
            "r > 100",
            "area = pi * r**2",
        ]

        def build(self):
            return cube(1)

    # area = 1 → r = ±1/sqrt(pi) ≈ ±0.564, neither > 100.
    with pytest.raises(ValidationError):
        C(area=1.0)


def test_D5_coupled_two_equation_trig_system():
    """Two equations binding theta and a length via sin/cos. Solving
    both as a system through ``_system_solve``."""
    class C(Component):
        equations = [
            "theta > 0",
            "theta < 90",
            "x > 0",
            "y > 0",
            "r > 0",
            "x = r * cos(theta)",
            "y = r * sin(theta)",
        ]

        def build(self):
            return cube(1)

    # Given x and r → theta = acos(x/r) → y follows.
    c = C(r=10, x=10 * math.cos(math.radians(30)))
    assert c.theta == pytest.approx(30.0, abs=1e-3)
    assert c.y == pytest.approx(10 * math.sin(math.radians(30)), abs=1e-3)


def test_D6_atan2_solves_angle_from_components():
    """Forward-eval through `atan2`. Pure forward, no sympy needed."""
    class C(Component):
        equations = [
            "dx, dy > 0",
            "angle = atan2(dy, dx)",
        ]

        def build(self):
            return cube(1)

    c = C(dx=1, dy=1)
    assert c.angle == pytest.approx(45.0)


# =============================================================================
# Group E — min/max/abs in solver position
# =============================================================================


def test_E1_forward_eval_through_max_with_floor():
    """`gap = max(a - b, 0.5)` — pure forward eval, both branches."""
    class C(Component):
        equations = [
            "a, b, gap > 0",
            "gap = max(a - b, 0.5)",
        ]

        def build(self):
            return cube(1)

    assert C(a=10, b=2).gap == 8.0       # 10-2=8 > 0.5
    assert C(a=2, b=10).gap == 0.5       # max picks floor


def test_E2_min_with_three_args_forward_eval():
    class C(Component):
        equations = [
            "w, h, r_max > 0",
            "corner_r = min(r_max, w/2, h/2)",
        ]

        def build(self):
            return cube(1)

    assert C(w=10, h=20, r_max=8).corner_r == 5.0   # w/2 wins
    assert C(w=20, h=20, r_max=3).corner_r == 3.0   # r_max wins


def test_E3_abs_forward_eval():
    class C(Component):
        equations = [
            "delta = abs(target - base)",
        ]

        def build(self):
            return cube(1)

    assert C(target=10, base=3).delta == 7.0
    assert C(target=3, base=10).delta == 7.0


def test_E4_floor_in_derivation():
    class C(Component):
        equations = [
            "n_full = floor(length / pitch)",
        ]

        def build(self):
            return cube(1)

    assert C(length=10.5, pitch=2).n_full == 5
    assert C(length=10.0, pitch=2).n_full == 5


def test_E5_ceil_in_derivation():
    class C(Component):
        equations = [
            "n_needed = ceil(length / pitch)",
        ]

        def build(self):
            return cube(1)

    assert C(length=10.1, pitch=2).n_needed == 6
    assert C(length=10.0, pitch=2).n_needed == 5


def test_E6_max_used_in_constraint_check_only():
    """`max(a, b) > threshold` is a predicate, not a derivation."""
    class C(Component):
        equations = [
            "a, b, threshold > 0",
            "max(a, b) > threshold",
        ]

        def build(self):
            return cube(1)

    C(a=5, b=2, threshold=4)             # max=5 > 4
    C(a=2, b=5, threshold=4)             # max=5 > 4
    with pytest.raises(ValidationError):
        C(a=2, b=3, threshold=4)         # max=3 not > 4


# =============================================================================
# Group H — system-solve + feasibility
# =============================================================================


def test_H1_two_by_two_single_solution():
    class C(Component):
        equations = [
            "a + b = c",
            "a - b = d",
        ]

        def build(self):
            return cube(1)

    p = C(c=5, d=1)
    assert p.a == pytest.approx(3.0)
    assert p.b == pytest.approx(2.0)


def test_H2_two_by_two_through_chained_substitution():
    """The iterative loop should resolve this without invoking
    ``_system_solve``: the first equation forward-evals once `a` is
    known via the second equation. Pin the chained-derivation path.
    """
    class C(Component):
        equations = [
            "b = a + 5",
            "a = 7",
        ]

        def build(self):
            return cube(1)

    c = C()
    assert c.a == 7.0
    assert c.b == 12.0


def test_H3_three_by_three_system():
    """3x3 linear system. Stresses ``_system_solve`` over more than
    two equations.
    """
    class C(Component):
        equations = [
            "a + b + c = 6",
            "a - b + c = 2",
            "a + b - c = 0",
        ]

        def build(self):
            return cube(1)

    p = C()
    assert p.a == pytest.approx(1.0)
    assert p.b == pytest.approx(2.0)
    assert p.c == pytest.approx(3.0)


def test_H4_underdetermined_system_raises_cannot_solve():
    """Two equations in three unknowns. Sympy returns parametric
    solutions; the resolver should report 'cannot solve'."""
    class C(Component):
        equations = [
            "a + b = c",
            "a - b = c - 4",
        ]

        def build(self):
            return cube(1)

    with pytest.raises(ValidationError, match="cannot solve"):
        C()
    # Supplying one variable gives the system enough to solve.
    p = C(c=10)
    # a + b = 10, a - b = 6 → a=8, b=2.
    assert p.a == pytest.approx(8.0)
    assert p.b == pytest.approx(2.0)


def test_H5_forward_eval_then_system_solve():
    """A derivation forward-evals first, then the resolved value
    becomes a known input to a 2x2 sympy system. Pin the ordering."""
    class C(Component):
        equations = [
            "k > 0",
            "scaled = k * 10",
            "a + b = scaled",
            "a - b = 4",
        ]

        def build(self):
            return cube(1)

    c = C(k=2)
    assert c.scaled == 20.0
    assert c.a == pytest.approx(12.0)
    assert c.b == pytest.approx(8.0)


def test_H6_inconsistent_classdef_time_rejection():
    """Two algebraic equations with no solution → class-define-time
    rejection by ``_check_mutual_inconsistency``."""
    with pytest.raises(ValidationError, match="inconsistent"):
        class C(Component):
            equations = [
                "a + b = 1",
                "a + b = 5",
            ]

            def build(self):
                return cube(1)


def test_H7_redundant_equations_underdetermined_not_inconsistent():
    """`a + b = 5; 2*(a + b) = 10` is the same equation twice — should
    NOT be flagged as inconsistent. Underdetermined is fine; insufficient
    runtime input fires only at construction."""
    class C(Component):
        equations = [
            "a + b = 5",
            "2 * (a + b) = 10",
        ]

        def build(self):
            return cube(1)

    # Class def time: no error.
    p = C(a=2)
    assert p.b == 3.0


# =============================================================================
# Group J — solver postponement / multi-pass
# =============================================================================


def test_J1_three_step_chain_declared_in_dependency_order():
    class C(Component):
        equations = [
            "a > 0",
            "b = a * 2",
            "c = b + 1",
        ]

        def build(self):
            return cube(1)

    p = C(a=3)
    assert p.b == 6.0
    assert p.c == 7.0


def test_J2_three_step_chain_declared_in_reverse_order():
    """The iterative loop should not depend on declaration order."""
    class C(Component):
        equations = [
            "c = b + 1",
            "b = a * 2",
            "a > 0",
        ]

        def build(self):
            return cube(1)

    p = C(a=3)
    assert p.b == 6.0
    assert p.c == 7.0


def test_J3_diamond_dependency_resolves():
    """Two derivations both depend on one source; a third depends on
    both. Verify the iterative loop completes in three passes."""
    class C(Component):
        equations = [
            "src > 0",
            "left = src * 2",
            "right = src + 10",
            "out = left + right",
        ]

        def build(self):
            return cube(1)

    p = C(src=5)
    assert p.left == 10.0
    assert p.right == 15.0
    assert p.out == 25.0


def test_J4_solver_one_direction_postpones_then_resolves():
    """`a = 2 * b` — supplying `a` forces sympy to invert. Pin both
    direction's resolution."""
    class C(Component):
        equations = ["a = 2 * b"]

        def build(self):
            return cube(1)

    assert C(b=3).a == 6.0
    assert C(a=8).b == 4.0


def test_J5_insufficient_with_sufficient_subsets_message():
    """Verify the under-spec message lists the sufficient combinations.
    Pins the ``_sufficient_subsets`` enumeration."""
    class C(Component):
        equations = ["od = id + 2*thk"]

        def build(self):
            return cube(1)

    with pytest.raises(ValidationError) as exc:
        C()
    msg = str(exc.value)
    assert "cannot solve" in msg
    assert "need one of" in msg
    # At least one of the three sufficient pairs is enumerated.
    assert any(
        combo in msg
        for combo in ("id, thk", "od, thk", "id, od", "thk, id", "thk, od", "od, id")
    )


def test_J6_supplied_optional_excluded_from_need_one_of():
    """If the caller already supplied a name, the "need one of" set
    shouldn't mention combinations that include it (it's already given).
    """
    class C(Component):
        equations = ["od = id + 2*thk"]

        def build(self):
            return cube(1)

    # Supply id; resolver still needs one of {od, thk}. The enumerated
    # subsets should reflect what's still missing.
    with pytest.raises(ValidationError) as exc:
        C(id=8)
    msg = str(exc.value)
    assert "given" in msg
    assert "id" in msg


def test_J7_consistency_check_fires_when_overspecified():
    """All three values supplied; the equation just consistency-checks."""
    class C(Component):
        equations = ["od = id + 2*thk"]

        def build(self):
            return cube(1)

    # Consistent: passes.
    C(id=8, od=10, thk=1)
    # Inconsistent: fails.
    with pytest.raises(ValidationError, match="equation violated"):
        C(id=8, od=10, thk=2)


# =============================================================================
# Group K — class-define-time validation interactions
# =============================================================================


def test_K1_self_reference_with_optional_target_caught():
    """`?x = x - 1` is self-referential and inconsistent regardless of
    whether `x` is optional. The check should fire at class-def time."""
    with pytest.raises(ValidationError):
        class C(Component):
            equations = ["?x = ?x - 1"]

            def build(self):
                return cube(1)


def test_K2_override_uses_curated_math_name():
    """`?angle = ?angle or pi/4` — pre-resolve evaluates with curated
    namespace, so `pi` resolves correctly."""
    class C(Component):
        equations = ["?angle = ?angle or (pi / 4)"]

        def build(self):
            return cube(1)

    c = C()
    assert c.angle == pytest.approx(math.pi / 4)
    assert C(angle=1.0).angle == 1.0


def test_K3_equation_target_collides_with_curated_pi_rejected():
    """`pi = 3.14` shadows the curated math constant — class-def-time
    rejection. (Tests _register_equations's curated-namespace check.)"""
    with pytest.raises(ValidationError, match="reserved name"):
        class C(Component):
            equations = ["pi = 3.14"]

            def build(self):
                return cube(1)


def test_K4_optional_on_curated_name_rejected():
    """`?range > 0` collides with the `range` builtin in the curated
    namespace."""
    with pytest.raises(ValidationError, match="reserved name"):
        class C(Component):
            equations = ["?range > 0"]

            def build(self):
                return cube(1)


def test_K5_unknown_function_caught_at_classdef_time():
    """Typo in a math function name: `snh` instead of `sin`. The check
    fires at class-define time, not at construction."""
    with pytest.raises(ValidationError, match="unknown function"):
        class C(Component):
            equations = ["x = snh(theta)"]

            def build(self):
                return cube(1)


def test_K6_walrus_rejected():
    with pytest.raises(ValidationError, match="walrus"):
        class C(Component):
            equations = ["(x := y + 1)"]

            def build(self):
                return cube(1)


def test_K7_chained_assignment_rejected():
    with pytest.raises(ValidationError, match="chained assignment"):
        class C(Component):
            equations = ["x = y = 5"]

            def build(self):
                return cube(1)


def test_K8_top_level_equality_outside_if_rejected():
    """`a == 5` outside an `if` is a typo (should be `=`). Class-def
    rejects with a hint."""
    with pytest.raises(ValidationError, match="`==` as a top-level"):
        class C(Component):
            equations = ["a == 5"]

            def build(self):
                return cube(1)


def test_K9_int_typed_target_with_arithmetic_rhs_rejected():
    """A non-float type can't be derived from arbitrary algebra — class-
    def time rejects unless the override pattern applies."""
    with pytest.raises(ValidationError, match="cannot be derived"):
        class C(Component):
            equations = ["count:int = total / size"]

            def build(self):
                return cube(1)


def test_K10_override_rhs_uses_target_in_arithmetic_rejected():
    """`?n = ?n + 1` — RHS throws when n is None. Class-def time."""
    with pytest.raises(ValidationError, match="cannot be evaluated when"):
        class C(Component):
            equations = ["?n = ?n + 1"]

            def build(self):
                return cube(1)


def test_K11_inline_tag_collides_with_explicit_param_rejected():
    with pytest.raises(ValidationError, match="both an inline"):
        class C(Component):
            count = Param(int)
            equations = ["count:int > 0"]

            def build(self):
                return cube(1)


def test_K12_disagreeing_inline_tags_rejected():
    with pytest.raises(ValidationError, match="type disagreement"):
        class C(Component):
            equations = [
                "count:int > 0",
                "y = count:str",
            ]

            def build(self):
                return cube(1)


# =============================================================================
# Group L — cross-Component publishing under stress
# =============================================================================


def test_L1_lid_reads_box_attribute():
    class _Box(Component):
        equations = [
            "w > 0",
            "outer_w = w + 4",
        ]

        def build(self):
            return cube(1)

    class _Lid(Component):
        box = Param(_Box)
        equations = ["lid_w = box.outer_w + 1"]

        def build(self):
            return cube(1)

    box = _Box(w=10)
    assert box.outer_w == 14.0
    lid = _Lid(box=box)
    assert lid.lid_w == 15.0


def test_L2_lid_reads_box_tuple_via_comprehension():
    """Box publishes a tuple derivation; Lid consumes it via a
    comprehension. Pins that tuple Params propagate through .attr-read
    in another Component's equations."""
    class _Box(Component):
        equations = [
            "len(size:tuple) = 3",
            "outer = tuple(s + 4 for s in size)",
        ]

        def build(self):
            return cube(1)

    class _Lid(Component):
        box = Param(_Box)
        equations = ["volume = box.outer[0] * box.outer[1] * box.outer[2]"]

        def build(self):
            return cube(1)

    box = _Box(size=(10, 20, 30))
    lid = _Lid(box=box)
    # outer = (14, 24, 34); volume = 11424.
    assert lid.volume == pytest.approx(14 * 24 * 34)


def test_L3_lid_reads_box_optional_after_default_applied():
    """Box has an optional override that fills via override pattern;
    Lid reads the resolved value."""
    class _Box(Component):
        equations = [
            "w > 0",
            "?bonus = ?bonus or 5",
            "outer_w = w + bonus",
        ]

        def build(self):
            return cube(1)

    class _Lid(Component):
        box = Param(_Box)
        equations = ["lid_w = box.outer_w + 1"]

        def build(self):
            return cube(1)

    box = _Box(w=10)        # bonus defaults to 5; outer_w = 15
    lid = _Lid(box=box)
    assert lid.lid_w == 16.0


def test_L4_namedtuple_field_read_in_equation():
    """Pattern from examples/battery-holder.py."""
    Spec = namedtuple("Spec", "d length")

    class _Holder(Component):
        spec = Param(Spec)
        equations = [
            "wall_thk, clearance > 0",
            "pitch = spec.d + 2 * (clearance + wall_thk)",
        ]

        def build(self):
            return cube(1)

    h = _Holder(spec=Spec(d=14.5, length=50.5), wall_thk=1.6, clearance=0.4)
    assert h.pitch == pytest.approx(14.5 + 2 * (0.4 + 1.6))


def test_L5_namedtuple_field_in_predicate():
    """Cross-constraint comparing a Param to a namedtuple field.
    `spec.length` is an Attribute, so the constraint becomes a
    predicate (not a per-Param fast-path)."""
    Spec = namedtuple("Spec", "length")

    class C(Component):
        spec = Param(Spec)
        equations = [
            "depth > 0",
            "depth < spec.length",
        ]

        def build(self):
            return cube(1)

    C(spec=Spec(length=50.0), depth=40.0)
    with pytest.raises(ValidationError, match="depth < spec.length"):
        C(spec=Spec(length=50.0), depth=60.0)
