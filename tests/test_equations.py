"""Tests for equation-solved Components (banner feature).

See design_docs/MajorReview1.md — this replaces the classmethod/setup
pattern for parametric Components with interdependent variables.
"""

import sys

import pytest

from scadwright import Component, Param
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# --- Basic single-equation solving ---


class _Box3(Component):
    h = Param(float, positive=True)
    id = Param(float, positive=True)
    od = Param(float, positive=True)
    thk = Param(float, positive=True)
    equations = ["od == id + 2*thk"]

    def build(self):
        return cube(self.h)


def test_solve_each_direction():
    assert _Box3(h=1, id=8, thk=1).od == pytest.approx(10.0)
    assert _Box3(h=1, od=10, thk=1).id == pytest.approx(8.0)
    assert _Box3(h=1, id=8, od=10).thk == pytest.approx(1.0)


def test_under_specified_error_message_lists_combinations():
    with pytest.raises(ValidationError) as exc:
        _Box3(h=1, id=8)
    msg = str(exc.value)
    assert "cannot solve" in msg
    # One of the sufficient sets should be enumerated.
    assert any(combo in msg for combo in ("id, thk", "id, od", "od, thk"))


def test_over_specified_consistent_ok():
    b = _Box3(h=1, id=8, od=10, thk=1)
    assert b.thk == pytest.approx(1.0)


def test_over_specified_inconsistent_raises():
    with pytest.raises(ValidationError, match="equation violated"):
        _Box3(h=1, id=8, od=10, thk=2)


def test_near_tolerance_over_specification_accepted():
    # 1e-11 slop is within the tolerance; should not raise.
    _Box3(h=1, id=8, od=10.0 + 1e-11, thk=1)


def test_gross_mismatch_rejected():
    with pytest.raises(ValidationError, match="equation violated"):
        _Box3(h=1, id=8, od=10 + 1e-3, thk=1)


# --- Defaults fill in when insufficient ---


class _WithDefault(Component):
    h = Param(float, positive=True)
    id = Param(float, positive=True)
    od = Param(float, positive=True)
    thk = Param(float, positive=True, default=1.0)
    equations = ["od == id + 2*thk"]

    def build(self):
        return cube(self.h)


def test_default_fills_in_when_missing():
    b = _WithDefault(h=1, id=8)
    assert b.thk == 1.0 and b.od == pytest.approx(10.0)


def test_default_yields_to_solver_when_sufficient():
    # User gave {id, od}, so thk can be solved (to 2). Default of 1.0 must be ignored.
    b = _WithDefault(h=1, id=8, od=12)
    assert b.thk == pytest.approx(2.0)


def test_default_still_insufficient_raises():
    # Only h given; default fills thk, but both id and od still unknown.
    with pytest.raises(ValidationError, match="cannot solve"):
        _WithDefault(h=1)


# --- Multi-equation (Funnel-like) ---


class _TwoEq(Component):
    a = Param(float, positive=True)
    b = Param(float, positive=True)
    c = Param(float, positive=True)
    d = Param(float, positive=True)
    thk = Param(float, positive=True)
    equations = [
        "a == b + 2*thk",
        "c == d + 2*thk",
    ]

    def build(self):
        return cube(1)


def test_two_eq_solves_independently():
    x = _TwoEq(thk=1, b=5, d=3)
    assert x.a == pytest.approx(7.0)
    assert x.c == pytest.approx(5.0)


def test_two_eq_mixed_forms():
    x = _TwoEq(thk=1, a=7, d=3)
    assert x.b == pytest.approx(5.0)
    assert x.c == pytest.approx(5.0)


# --- Frozen after construction ---


def test_frozen_after_construction():
    b = _Box3(h=1, id=8, od=10)
    with pytest.raises(ValidationError, match="frozen"):
        b.id = 5


def test_frozen_only_blocks_params_not_cache_attrs():
    b = _Box3(h=1, id=8, od=10)
    b._bbox_cache = None  # allowed
    b._built_tree = None  # allowed


# --- Class-definition-time validation ---


def test_equation_auto_creates_undeclared_params():
    """Variables in equations that aren't explicitly declared get
    auto-created as Param(float)."""
    class _AutoParam(Component):
        a = Param(float)
        equations = ["a == b"]
        def build(self): return cube(1)

    # b should be auto-created as a Param(float).
    assert "b" in _AutoParam.__params__
    obj = _AutoParam(a=5)
    assert obj.b == 5.0


def test_equation_auto_created_params_are_solvable():
    """Auto-created params from equations can be solved like any other."""
    class _AutoSolve(Component):
        equations = ["od == id + 2*thk"]
        def build(self): return cube(1)

    obj = _AutoSolve(id=10, thk=2)
    assert obj.od == 14.0


def test_unparseable_equation_raises_at_class_def():
    with pytest.raises(ValidationError, match="cannot parse"):
        class _Broken(Component):
            a = Param(float)
            equations = ["a ==== 5"]
            def build(self): return cube(1)


def test_missing_operator_raises_at_class_def():
    with pytest.raises(ValidationError, match="not a boolean predicate"):
        class _NoEq(Component):
            a = Param(float)
            equations = ["a + 5"]
            def build(self): return cube(1)


# --- Constants and nonlinear ---


class _Quadratic(Component):
    area = Param(float, positive=True)
    r = Param(float, positive=True)
    equations = ["area == pi * r**2"]

    def build(self):
        return cube(1)


def test_pi_constant_not_treated_as_param():
    import math
    q = _Quadratic(area=math.pi * 25)
    assert q.r == pytest.approx(5.0)


def test_quadratic_filters_negative_root_via_validator():
    # area = pi*r^2 has r = ±sqrt(area/pi); positive=True keeps only the positive root.
    import math
    q = _Quadratic(area=math.pi * 9)
    assert q.r == pytest.approx(3.0)


# --- Sympy missing ---


def test_sympy_missing_raises_helpful_import_error(monkeypatch):
    # Simulate sympy not installed by blocking future imports.
    import scadwright.component.equations as eq_mod

    def _blocker():
        raise ImportError("no sympy")

    monkeypatch.setattr(eq_mod, "_require_sympy", _blocker)

    with pytest.raises(ImportError, match="no sympy"):
        class _ShouldFail(Component):
            a = Param(float)
            equations = ["a == 5"]
            def build(self): return cube(1)
