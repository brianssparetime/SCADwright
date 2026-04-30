"""Tests for equations-list predicates.

A predicate is any boolean-valued expression in the equations list that
isn't classified as a solver equality, constraint, or cross-constraint. It
evaluates at instance-construction time; a falsy result raises
ValidationError. The enrichment layer adds per-value context for two common
shapes: top-level Compare and ``all(... for e in seq)``.
"""

from __future__ import annotations

from collections import namedtuple

import pytest

from scadwright import Component, Param
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# =============================================================================
# Classification boundary (what becomes a predicate vs. a solver/constraint)
# =============================================================================


def test_algebraic_equality_stays_solver_not_predicate():
    # Pure algebra on both sides → solver equation, not predicate.
    class C(Component):
        equations = ["od = id + 2*thk", "id, od, thk > 0"]
        def build(self): return cube(1)

    c = C(id=8, thk=1)
    assert c.od == 10.0


def test_algebraic_constraint_stays_constraint_not_predicate():
    # `a > 0` with Param LHS and numeric RHS hits the per-Param validator
    # fast path — gives field-aware error messages.
    class C(Component):
        equations = ["a > 0"]
        def build(self): return cube(1)

    with pytest.raises(ValidationError, match="must be positive"):
        C(a=-5)


def test_len_comparison_becomes_predicate():
    class C(Component):
        size = Param(tuple)
        equations = ["len(size) = 3"]
        def build(self): return cube(1)

    C(size=(1, 2, 3))  # passes
    with pytest.raises(ValidationError) as exc_info:
        C(size=(1, 2))
    msg = str(exc_info.value)
    assert "len(size) = 3" in msg


def test_attribute_comparison_becomes_predicate():
    # `spec.length` is an Attribute, so sympify can't reach it → predicate.
    Spec = namedtuple("Spec", "length")

    class C(Component):
        spec = Param(Spec)
        equations = ["depth > 0", "depth < spec.length"]
        def build(self): return cube(1)

    C(spec=Spec(length=50.0), depth=40.0)  # passes
    with pytest.raises(ValidationError) as exc_info:
        C(spec=Spec(length=50.0), depth=60.0)
    msg = str(exc_info.value)
    assert "depth < spec.length" in msg


# =============================================================================
# Common predicate shapes
# =============================================================================


def test_membership_predicate():
    class C(Component):
        series = Param(str)
        equations = ["series in ('AA', 'AAA', 'C', 'D')"]
        def build(self): return cube(1)

    C(series="AA")
    with pytest.raises(ValidationError, match="series in"):
        C(series="9V")


def test_xor_predicate():
    # "exactly one of r or rs must be given"
    class C(Component):
        r = Param(float, default=None)
        rs = Param(tuple, default=None)
        equations = ["(r is None) != (rs is None)"]
        def build(self): return cube(1)

    C(r=3.0)
    C(rs=(1.0, 2.0, 3.0, 4.0))
    with pytest.raises(ValidationError):
        C()  # neither
    with pytest.raises(ValidationError):
        C(r=3.0, rs=(1.0, 2.0, 3.0, 4.0))  # both


def test_boolop_predicate():
    class C(Component):
        equations = ["a, b > 0", "a < 10 and b < 10"]
        def build(self): return cube(1)

    C(a=5, b=5)
    with pytest.raises(ValidationError, match="a < 10 and b < 10"):
        C(a=15, b=5)


def test_not_predicate():
    class C(Component):
        equations = ["x > 0", "not (x > 100)"]
        def build(self): return cube(1)

    C(x=50)
    with pytest.raises(ValidationError):
        C(x=200)


# =============================================================================
# all(...) with generator expression
# =============================================================================


Elem = namedtuple("Elem", "dia ok")


def test_all_passing():
    class C(Component):
        elements = Param(tuple)
        equations = ["all(e.ok for e in elements)"]
        def build(self): return cube(1)

    C(elements=(Elem(10.0, True), Elem(20.0, True)))


def test_all_failing_enriched_with_index():
    class C(Component):
        elements = Param(tuple)
        equations = ["all(e.ok for e in elements)"]
        def build(self): return cube(1)

    with pytest.raises(ValidationError) as exc_info:
        C(elements=(Elem(10.0, True), Elem(20.0, False), Elem(30.0, True)))
    msg = str(exc_info.value)
    assert "all(e.ok for e in elements)" in msg
    assert "index 1" in msg


def test_all_failing_compare_shows_left_right():
    class C(Component):
        elements = Param(tuple)
        throat_dia = Param(float, positive=True)
        equations = ["all(e.dia <= throat_dia for e in elements)"]
        def build(self): return cube(1)

    with pytest.raises(ValidationError) as exc_info:
        C(
            elements=(Elem(10.0, True), Elem(50.0, True)),
            throat_dia=30.0,
        )
    msg = str(exc_info.value)
    assert "index 1" in msg
    assert "left=50.0" in msg
    assert "right=30.0" in msg


def test_all_respects_filter():
    # Only constricted elements are checked.
    Elem2 = namedtuple("Elem2", "dia constricted")
    class C(Component):
        elements = Param(tuple)
        throat = Param(float, positive=True)
        equations = ["all(e.dia <= throat for e in elements if e.constricted)"]
        def build(self): return cube(1)

    # Second element violates but is unconstricted → passes.
    C(
        elements=(Elem2(5.0, True), Elem2(50.0, False)),
        throat=10.0,
    )
    # Second element violates AND is constricted → fails.
    with pytest.raises(ValidationError, match="index 1"):
        C(
            elements=(Elem2(5.0, True), Elem2(50.0, True)),
            throat=10.0,
        )


# =============================================================================
# Namespace restriction (same as derivations)
# =============================================================================


def test_predicate_calls_unknown_function_caught_early():
    # `my_validator` is neither curated nor a Param — class-def-time error.
    # The call is wrapped in a predicate shape (`BoolOp`) so classify_equation
    # gets past the "not a boolean predicate" check and into call-name
    # validation, where `my_validator` is flagged.
    with pytest.raises(ValidationError, match="unknown function"):
        class C(Component):
            equations = ["a > 0", "my_validator(a) and a > 0"]
            def build(self): return cube(1)


def test_predicate_undefined_name_wrapped_at_runtime():
    # A bare name that isn't a curated builtin, Param, or derivation:
    # `sometimes_true` → NameError at eval → ValidationError.
    # (Class-def rejects for bare expressions, so wrap in a shape that passes:
    # `sometimes_true or True`.)
    class C(Component):
        a = Param(float)
        equations = ["sometimes_true or a > 0"]
        def build(self): return cube(1)

    with pytest.raises(ValidationError) as exc_info:
        C(a=5)
    msg = str(exc_info.value)
    assert "sometimes_true" in msg


# =============================================================================
# Rejection at class-definition time
# =============================================================================


def test_bare_name_rejected():
    with pytest.raises(ValidationError, match="not a boolean rule"):
        class C(Component):
            a = Param(float)
            equations = ["a"]
            def build(self): return cube(1)


def test_bare_arithmetic_rejected():
    with pytest.raises(ValidationError, match="not a boolean rule"):
        class C(Component):
            equations = ["a + b"]
            def build(self): return cube(1)


# =============================================================================
# Predicate can reference earlier derivation
# =============================================================================


def test_predicate_references_derivation():
    class C(Component):
        n = Param(int, positive=True)
        pitch = Param(float, positive=True)
        equations = [
            "positions = tuple(i * pitch for i in range(n))",
            "all(p >= 0 for p in positions)",
        ]
        def build(self): return cube(1)

    C(n=4, pitch=2.0)


# =============================================================================
# Mixed with other equation kinds
# =============================================================================


def test_mixed_equality_constraint_cross_derivation_predicate():
    Spec = namedtuple("Spec", "d length")

    class C(Component):
        spec = Param(Spec)
        equations = [
            "od = id + 2*thk",          # solver
            "id, od, thk > 0",            # constraint (fast path)
            "id < od",                    # cross-constraint (fast path)
            "depth > 0",
            "depth < spec.length",        # predicate (Attribute RHS)
            "volume = od * depth",        # derivation
        ]
        def build(self): return cube(1)

    c = C(spec=Spec(d=10.0, length=40.0), id=10, thk=2, depth=30.0)
    assert c.od == 14
    assert c.volume == 420.0
