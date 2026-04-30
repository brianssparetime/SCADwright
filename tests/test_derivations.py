"""Tests for equations-list derivations (single `=`, identifier LHS).

Derivations evaluate Python expressions at instance-construction time and
publish the result as an instance attribute. They cover the cases that
equalities can't: namedtuple field access, loop-generated tuples, conditional
scalars, multi-value reductions.
"""

from __future__ import annotations

from collections import namedtuple

import pytest

from scadwright import Component, Param
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# =============================================================================
# Core behavior
# =============================================================================


def test_scalar_derivation_from_param():
    class C(Component):
        equations = ["x > 0", "y = x * 2"]
        def build(self): return cube(1)

    c = C(x=3)
    assert c.y == 6.0


def test_derivation_chain():
    class C(Component):
        equations = [
            "a > 0",
            "b = a + 1",
            "c = b * 10",
        ]
        def build(self): return cube(1)

    c = C(a=2)
    assert c.b == 3
    assert c.c == 30


def test_derivation_with_namedtuple_field():
    Spec = namedtuple("Spec", "d length")

    class C(Component):
        spec = Param(Spec)
        equations = [
            "pad > 0",
            "outer_d = spec.d + 2 * pad",
            "outer_l = spec.length",
        ]
        def build(self): return cube(1)

    c = C(spec=Spec(d=10.0, length=20.0), pad=1.5)
    assert c.outer_d == 13.0
    assert c.outer_l == 20.0


def test_loop_based_derivation():
    class C(Component):
        n = Param(int, positive=True)
        equations = [
            "pitch > 0",
            "positions = tuple(i * pitch for i in range(n))",
        ]
        def build(self): return cube(1)

    c = C(n=4, pitch=5.0)
    assert c.positions == (0.0, 5.0, 10.0, 15.0)


def test_derivation_uses_min_max():
    class C(Component):
        equations = [
            "w > 0", "h > 0", "r_max > 0",
            "corner_r = min(r_max, w/2, h/2)",
        ]
        def build(self): return cube(1)

    c = C(w=10, h=20, r_max=8)
    assert c.corner_r == 5.0  # bounded by w/2


def test_derivation_uses_math_functions():
    from math import sqrt
    class C(Component):
        equations = ["x > 0", "hypot = sqrt(x*x + 9)"]
        def build(self): return cube(1)

    c = C(x=4)
    assert c.hypot == pytest.approx(sqrt(25))


# =============================================================================
# = and == are interchangeable (collapse_eq spec)
# =============================================================================
#
# Per the unified spec, `=` and `==` produce identical Components. Every
# bare-Name target of any equation is a Param the user MAY supply
# (consistency-checked) or omit (filled in by the resolver). There is no
# class-def-time collision between `=` LHS and other declarations of the
# same name; the resolver treats them as one system.


def test_assign_target_overlaps_with_explicit_param():
    # `x = Param(float)` declares the type explicitly; the equation
    # `x = 5` provides a value the resolver fills in if the user omits.
    # User can omit (gets 5), supply 5 (consistency check passes), or
    # supply 7 (consistency check fails).
    class C(Component):
        x = Param(float)
        equations = ["x = 5"]
        def build(self): return cube(1)

    assert C().x == 5.0
    assert C(x=5).x == 5.0
    with pytest.raises(ValidationError):
        C(x=7)


def test_assign_and_equality_targets_with_same_name():
    # Both `a = b + 1` and `a = 5` constrain `a`. Solving as a system:
    # a=5, b=4. Single consistent solution.
    class C(Component):
        equations = ["a = b + 1", "a = 5"]
        def build(self): return cube(1)

    c = C()
    assert c.a == 5.0
    assert c.b == 4.0


def test_two_assigns_same_target_solve_as_system():
    # Two `=` lines targeting `b` form a 2-equation system in (a, b).
    # b = a+1, b = a*2 → a=1, b=2.
    class C(Component):
        equations = ["a > 0", "b = a + 1", "b = a * 2"]
        def build(self): return cube(1)

    c = C()
    assert c.a == pytest.approx(1.0)
    assert c.b == pytest.approx(2.0)


def test_assign_target_can_be_supplied_as_kwarg():
    # The bare-Name target of an `=` line is a Param the user may pin.
    class C(Component):
        equations = ["a = b + 1"]
        def build(self): return cube(1)

    c = C(a=10, b=9)
    assert c.a == 10.0
    assert c.b == 9.0


def test_assign_target_supplied_inconsistent_raises():
    class C(Component):
        equations = ["a = b + 1"]
        def build(self): return cube(1)

    with pytest.raises(ValidationError):
        C(a=10, b=5)


# =============================================================================
# Class-definition-time rejection
# =============================================================================


def test_derivation_syntax_error_caught_early():
    with pytest.raises(ValidationError, match="cannot parse"):
        class C(Component):
            equations = ["pitch = (x + "]
            def build(self): return cube(1)


def test_derivation_calls_unknown_function_caught_early():
    # `foo_helper` isn't a curated builtin, isn't a Param, isn't an earlier
    # derivation. Class-def time error (matches the same UX as equality typos).
    with pytest.raises(ValidationError, match="unknown function"):
        class C(Component):
            equations = ["a > 0", "b = foo_helper(a)"]
            def build(self): return cube(1)


# =============================================================================
# Instance-time evaluation failures
# =============================================================================


def test_undeclared_free_name_in_equation_auto_declares_as_param():
    # Under the unified spec, free names appearing in equations are
    # auto-declared as Params. A typo'd name therefore becomes a
    # required Param; the user gets a runtime "missing required
    # parameter" / "insufficient" error instead of a class-def-time one,
    # which still points at the offending name.
    class C(Component):
        equations = ["a > 0", "b = a + undeclared_name"]
        def build(self): return cube(1)

    with pytest.raises(ValidationError) as exc_info:
        C(a=1)
    msg = str(exc_info.value)
    assert "undeclared_name" in msg


def test_derivation_zero_division_wrapped():
    class C(Component):
        a = Param(float, non_negative=True)
        equations = ["b = 1 / a"]
        def build(self): return cube(1)

    with pytest.raises(ValidationError) as exc_info:
        C(a=0)
    msg = str(exc_info.value)
    assert "equation" in msg
    assert "1 / a" in msg
    assert "ZeroDivisionError" in msg


# =============================================================================
# Namespace restriction
# =============================================================================


def test_derivation_cannot_use_blocked_builtin():
    # `open` is not in the curated namespace; trying to call it produces
    # a class-def time error (unknown function).
    with pytest.raises(ValidationError, match="unknown function"):
        class C(Component):
            equations = ["x = open('/etc/passwd').read()"]
            def build(self): return cube(1)


def test_derivation_cannot_import():
    # `__import__` isn't exposed; the whole `__builtins__` dict is blanked.
    # Users don't write `__import__` directly, but class-def time bare-name
    # check rejects it.
    with pytest.raises(ValidationError, match="unknown function"):
        class C(Component):
            equations = ["x = __import__('os')"]
            def build(self): return cube(1)


# =============================================================================
# Freeze behavior
# =============================================================================


def test_derivation_name_frozen_after_construction():
    class C(Component):
        equations = ["a > 0", "b = a * 2"]
        def build(self): return cube(1)

    c = C(a=3)
    assert c.b == 6
    with pytest.raises(ValidationError, match="frozen"):
        c.b = 999


def test_param_still_frozen_when_only_derivations():
    # A Component with derivations (but no equations) still freezes Params.
    class C(Component):
        x = Param(float)
        equations = ["y = x * 2"]
        def build(self): return cube(1)

    c = C(x=5)
    with pytest.raises(ValidationError, match="frozen"):
        c.x = 10


# =============================================================================
# Usage in build()
# =============================================================================


def test_derivation_visible_in_build():
    class C(Component):
        equations = ["side > 0", "half = side / 2"]
        def build(self):
            assert self.half == self.side / 2
            return cube(self.side)

    c = C(side=10)
    assert c.half == 5.0
    _ = c._get_built_tree()  # ensure build sees derived attr


# =============================================================================
# Mixed with equalities, constraints, cross-constraints
# =============================================================================


def test_derivation_alongside_equation_solver():
    class C(Component):
        equations = [
            "od = id + 2*thk",
            "id, od, thk > 0",
            "wall_mid = (od + id) / 2 / 2",  # mean wall-centerline radius
        ]
        def build(self): return cube(1)

    c = C(id=10, thk=2)
    assert c.od == 14
    assert c.wall_mid == pytest.approx(6.0)


def test_derivation_sees_cross_constraint_params():
    class C(Component):
        equations = [
            "a, b > 0",
            "a < b",
            "ratio = a / b",
        ]
        def build(self): return cube(1)

    c = C(a=3, b=4)
    assert c.ratio == 0.75
