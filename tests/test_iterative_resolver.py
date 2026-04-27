"""Tests for the iterative resolver (gated by ``_use_iterative_resolver``).

The resolver is the new path for the equations pipeline. It coexists
with the legacy bucketed pipeline; Components opt in via the
``_use_iterative_resolver = True`` class attribute.

These tests exercise the resolver through opt-in Component subclasses.
The legacy path is covered by ``test_equations_baseline.py`` and the
existing ``test_equations.py`` / ``test_derivations.py`` /
``test_predicates.py`` / ``test_cross_constraints.py`` files.
"""

from __future__ import annotations

from collections import namedtuple

import pytest

from scadwright import Component, Param
from scadwright.component.resolver import (
    IterativeResolver,
    parse_equations_unified,
)
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# =============================================================================
# Standalone resolver (no Component)
# =============================================================================


def _make_param(default=None):
    if default is None:
        return Param(float)
    return Param(float, default=default)


def test_standalone_simple_solve():
    eqs, cons, _ = parse_equations_unified(["od == id + 2*thk"])
    params = {"id": _make_param(), "od": _make_param(), "thk": _make_param()}
    r = IterativeResolver(eqs, cons, params, {"id": 8, "thk": 1}, "T")
    out = r.resolve()
    assert out["od"] == pytest.approx(10.0)


def test_standalone_solve_each_direction():
    eqs, cons, _ = parse_equations_unified(["od == id + 2*thk"])
    params = {"id": _make_param(), "od": _make_param(), "thk": _make_param()}

    out = IterativeResolver(eqs, cons, params, {"id": 8, "od": 10}, "T").resolve()
    assert out["thk"] == pytest.approx(1.0)

    out = IterativeResolver(eqs, cons, params, {"od": 10, "thk": 1}, "T").resolve()
    assert out["id"] == pytest.approx(8.0)


def test_standalone_consistency_check_passes():
    eqs, cons, _ = parse_equations_unified(["od == id + 2*thk"])
    params = {"id": _make_param(), "od": _make_param(), "thk": _make_param()}
    out = IterativeResolver(
        eqs, cons, params, {"id": 8, "od": 10, "thk": 1}, "T"
    ).resolve()
    assert out["od"] == pytest.approx(10.0)


def test_standalone_consistency_check_fails():
    eqs, cons, _ = parse_equations_unified(["od == id + 2*thk"])
    params = {"id": _make_param(), "od": _make_param(), "thk": _make_param()}
    with pytest.raises(ValidationError, match="equation violated"):
        IterativeResolver(
            eqs, cons, params, {"id": 8, "od": 10, "thk": 2}, "T"
        ).resolve()


def test_standalone_insufficient():
    eqs, cons, _ = parse_equations_unified(["od == id + 2*thk"])
    params = {"id": _make_param(), "od": _make_param(), "thk": _make_param()}
    with pytest.raises(ValidationError, match="cannot solve"):
        IterativeResolver(eqs, cons, params, {"id": 8}, "T").resolve()


def test_standalone_system_solve():
    # Two equations, two unknowns, neither solvable single-handedly.
    eqs, cons, _ = parse_equations_unified([
        "a + b == 5",
        "a - b == 1",
    ])
    params = {"a": _make_param(), "b": _make_param()}
    out = IterativeResolver(eqs, cons, params, {}, "T").resolve()
    assert out["a"] == pytest.approx(3.0)
    assert out["b"] == pytest.approx(2.0)


def test_standalone_quadratic_with_validator():
    eqs, cons, _ = parse_equations_unified([
        "area == 3.141592653589793 * r**2",
    ])
    params = {
        "area": Param(float),
        "r": Param(float, positive=True),
    }
    out = IterativeResolver(
        eqs, cons, params, {"area": 12.566370614359172}, "T"
    ).resolve()
    assert out["r"] == pytest.approx(2.0)


def test_standalone_forward_eval_with_max():
    eqs, cons, _ = parse_equations_unified([
        "edge = max(a - b, 0.5)",
    ])
    params = {"a": _make_param(), "b": _make_param()}
    out = IterativeResolver(eqs, cons, params, {"a": 3, "b": 1}, "T").resolve()
    assert out["edge"] == pytest.approx(2.0)
    out2 = IterativeResolver(eqs, cons, params, {"a": 1, "b": 3}, "T").resolve()
    assert out2["edge"] == pytest.approx(0.5)


def test_standalone_forward_eval_with_tuple():
    eqs, cons, _ = parse_equations_unified([
        "positions = tuple(i * pitch for i in range(count))",
    ])
    params = {
        "pitch": _make_param(),
        "count": Param(int),
    }
    out = IterativeResolver(
        eqs, cons, params, {"pitch": 5.0, "count": 4}, "T"
    ).resolve()
    assert out["positions"] == (0.0, 5.0, 10.0, 15.0)


def test_standalone_attribute_access():
    Spec = namedtuple("Spec", "d length")
    eqs, cons, _ = parse_equations_unified([
        "pitch = spec.d + 2 * clearance",
    ])
    params = {
        "spec": Param(Spec),
        "clearance": _make_param(),
    }
    out = IterativeResolver(
        eqs, cons, params, {"spec": Spec(d=14.5, length=50.5), "clearance": 1.5},
        "T",
    ).resolve()
    assert out["pitch"] == pytest.approx(17.5)


def test_standalone_constraint_passes():
    eqs, cons, _ = parse_equations_unified([
        "od == id + 2*thk",
        "id < od",
    ])
    params = {"id": _make_param(), "od": _make_param(), "thk": _make_param()}
    out = IterativeResolver(
        eqs, cons, params, {"id": 8, "thk": 1}, "T"
    ).resolve()
    assert out["od"] == pytest.approx(10.0)


def test_standalone_constraint_fails():
    eqs, cons, _ = parse_equations_unified([
        "id < od",
    ])
    params = {"id": _make_param(), "od": _make_param()}
    with pytest.raises(ValidationError, match="constraint violated"):
        IterativeResolver(eqs, cons, params, {"id": 10, "od": 5}, "T").resolve()


def test_standalone_per_param_validator_fires():
    eqs, cons, _ = parse_equations_unified([
        "x == 5 - y",
    ])
    params = {
        "x": Param(float, positive=True),
        "y": _make_param(),
    }
    # y=10 makes x=-5, violating positivity.
    with pytest.raises(ValidationError, match="must be positive"):
        IterativeResolver(eqs, cons, params, {"y": 10}, "T").resolve()


def test_standalone_chained_derivation():
    # b depends on a; c depends on b.
    eqs, cons, _ = parse_equations_unified([
        "b = a * 2",
        "c = b + 1",
    ])
    params = {"a": _make_param()}
    out = IterativeResolver(eqs, cons, params, {"a": 3}, "T").resolve()
    assert out["b"] == pytest.approx(6.0)
    assert out["c"] == pytest.approx(7.0)


def test_standalone_chained_derivation_reverse_order():
    # Same as above but the equations list has the dependent first;
    # iterative loop should still resolve.
    eqs, cons, _ = parse_equations_unified([
        "c = b + 1",
        "b = a * 2",
    ])
    params = {"a": _make_param()}
    out = IterativeResolver(eqs, cons, params, {"a": 3}, "T").resolve()
    assert out["b"] == pytest.approx(6.0)
    assert out["c"] == pytest.approx(7.0)


def test_standalone_optional_skipped_when_none():
    eqs, cons, _ = parse_equations_unified([
        "?fillet > 0",
    ])
    params = {"fillet": Param(float, default=None)}
    out = IterativeResolver(eqs, cons, params, {}, "T").resolve()
    assert out["fillet"] is None


def test_standalone_optional_constraint_fires_when_set():
    eqs, cons, _ = parse_equations_unified([
        "?fillet > 0",
    ])
    params = {"fillet": Param(float, default=None)}
    # `?fillet > 0` becomes a per-Param positive validator; the message
    # uses the validator's own phrasing.
    with pytest.raises(ValidationError, match="must be positive"):
        IterativeResolver(eqs, cons, params, {"fillet": -1}, "T").resolve()


def test_standalone_supplied_none_with_pinned_equation_inconsistent():
    """OQ 6: explicit None + equation pinning a value → inconsistent.

    The `?` sigil can't be used on a derivation LHS, so this test
    declares the optional Param explicitly and uses a derivation that
    pins it to a fixed value.
    """
    eqs, cons, _ = parse_equations_unified(["x = 5"])
    params = {"x": Param(float, default=None)}
    with pytest.raises(ValidationError, match="explicitly supplied as None"):
        IterativeResolver(eqs, cons, params, {"x": None}, "T").resolve()


# =============================================================================
# Component integration via opt-in flag
# =============================================================================


class _NewBox(Component):
    _use_iterative_resolver = True
    h = Param(float, positive=True)
    id = Param(float, positive=True)
    od = Param(float, positive=True)
    thk = Param(float, positive=True)
    equations = ["od == id + 2*thk"]

    def build(self):
        return cube(self.h)


def test_opt_in_solve_each_direction():
    assert _NewBox(h=1, id=8, thk=1).od == pytest.approx(10.0)
    assert _NewBox(h=1, od=10, thk=1).id == pytest.approx(8.0)
    assert _NewBox(h=1, id=8, od=10).thk == pytest.approx(1.0)


def test_opt_in_consistency_check():
    box = _NewBox(h=1, id=8, od=10, thk=1)
    assert box.thk == pytest.approx(1.0)


def test_opt_in_inconsistent_raises():
    with pytest.raises(ValidationError, match="equation violated"):
        _NewBox(h=1, id=8, od=10, thk=2)


def test_opt_in_underspec_message():
    with pytest.raises(ValidationError) as exc:
        _NewBox(h=1, id=8)
    msg = str(exc.value)
    assert "cannot solve" in msg


class _NewBatteryHolder(Component):
    """Pattern from examples/battery-holder.py via the new resolver."""

    _use_iterative_resolver = True
    spec = Param(namedtuple("Spec", "d length"))
    count = Param(int, positive=True)
    equations = [
        "wall_thk, clearance > 0",
        "tray_depth > 0",
        "tray_depth < spec.length",
        "pitch = spec.d + 2 * (clearance + wall_thk)",
        "outer_w = count * pitch + 2 * end_clearance",
        "end_clearance > 0",
    ]

    def build(self):
        return cube(1)


def test_opt_in_with_namedtuple_spec_and_derivations():
    Spec = _NewBatteryHolder.__params__["spec"].type
    s = Spec(d=14.5, length=50.5)
    holder = _NewBatteryHolder(
        spec=s, count=6, wall_thk=1.6, clearance=0.4,
        end_clearance=3.0, tray_depth=40.0,
    )
    expected_pitch = 14.5 + 2 * (0.4 + 1.6)
    assert holder.pitch == pytest.approx(expected_pitch)
    assert holder.outer_w == pytest.approx(6 * expected_pitch + 6.0)


def test_opt_in_predicate_against_namedtuple_field():
    Spec = _NewBatteryHolder.__params__["spec"].type
    s = Spec(d=14.5, length=50.5)
    with pytest.raises(ValidationError, match="constraint violated"):
        _NewBatteryHolder(
            spec=s, count=2, wall_thk=1, clearance=0.4,
            end_clearance=3.0, tray_depth=60.0,  # > spec.length
        )


class _NewChamferedBox(Component):
    """Pattern from shapes/fillets/chamfered_box.py via the new resolver."""

    _use_iterative_resolver = True
    size = Param(tuple)
    equations = [
        "?fillet > 0",
        "?chamfer > 0",
        "len(size) == 3",
        "exactly_one(?fillet, ?chamfer)",
        "edge = ?fillet if ?fillet else ?chamfer",
        "all(s > 2 * edge for s in size)",
    ]

    def build(self):
        return cube(1)


def test_opt_in_optional_with_helper():
    # Either fillet or chamfer; not both.
    a = _NewChamferedBox(size=(20, 15, 10), fillet=2)
    assert a.fillet == 2
    assert a.chamfer is None
    assert a.edge == 2

    b = _NewChamferedBox(size=(20, 15, 10), chamfer=3)
    assert b.fillet is None
    assert b.chamfer == 3
    assert b.edge == 3


def test_opt_in_optional_helper_fail_neither():
    with pytest.raises(ValidationError, match="constraint violated"):
        _NewChamferedBox(size=(20, 15, 10))


def test_opt_in_optional_helper_fail_both():
    with pytest.raises(ValidationError, match="constraint violated"):
        _NewChamferedBox(size=(20, 15, 10), fillet=2, chamfer=3)


def test_opt_in_size_check_with_derived_intermediate():
    # `all(s > 2 * edge for s in size)` checks each side.
    with pytest.raises(ValidationError, match="constraint violated"):
        _NewChamferedBox(size=(4, 4, 4), fillet=3)


# =============================================================================
# Cross-Component publishing via the new resolver
# =============================================================================


class _NewBoxPublisher(Component):
    _use_iterative_resolver = True
    w = Param(float, positive=True)
    equations = [
        "outer_w = w + 4",
    ]

    def build(self):
        return cube(1)


class _NewLid(Component):
    _use_iterative_resolver = True
    box = Param(_NewBoxPublisher)
    equations = [
        "lid_w = box.outer_w + 1",
    ]

    def build(self):
        return cube(1)


def test_opt_in_cross_component_publishing():
    box = _NewBoxPublisher(w=10)
    assert box.outer_w == pytest.approx(14.0)
    lid = _NewLid(box=box)
    assert lid.lid_w == pytest.approx(15.0)


# =============================================================================
# Comma expansion
# =============================================================================


class _NewCommaConstraint(Component):
    _use_iterative_resolver = True
    equations = [
        "h, id, od, thk > 0",
        "od == id + 2*thk",
    ]

    def build(self):
        return cube(1)


def test_opt_in_comma_constraint_expansion():
    box = _NewCommaConstraint(h=1, id=8, thk=1)
    assert box.od == pytest.approx(10.0)


def test_opt_in_comma_constraint_fails_per_name():
    # Comma-expanded `> 0` constraints become per-Param positive
    # validators; the message uses the validator's wording.
    with pytest.raises(ValidationError, match="must be positive"):
        _NewCommaConstraint(h=1, id=-1, thk=1)


# =============================================================================
# Setup() hook still runs
# =============================================================================


class _NewSetupRuns(Component):
    _use_iterative_resolver = True
    a = Param(float, positive=True)
    equations = ["b = a * 2"]

    def setup(self):
        self.from_setup = self.b + 1

    def build(self):
        return cube(1)


def test_opt_in_setup_hook_runs_after_resolver():
    p = _NewSetupRuns(a=3)
    assert p.b == pytest.approx(6.0)
    assert p.from_setup == pytest.approx(7.0)


# =============================================================================
# Spec compliance: equations whose LHS isn't a bare Name
# =============================================================================
# Per the spec (collapse_eq.md, "Feature spec v2"), an equation can have
# any expression on either side. ``=`` requires Python's grammar (LHS
# must be an assignable target), but ``==`` accepts arbitrary shapes.
# The resolver decides at resolve time whether to drive a side or
# consistency-check.


class _NonBareLhs(Component):
    a = Param(float)
    b = Param(float)
    foo = Param(float)
    equations = ["max(a, b) == foo"]

    def build(self):
        return cube(1)


def test_eq_with_non_bare_lhs_resolves_bare_rhs():
    # ``max(a, b) == foo`` with a, b known should solve foo by
    # forward-eval (the bare-Name side gets the result).
    p = _NonBareLhs(a=3, b=7)
    assert p.foo == pytest.approx(7.0)


def test_eq_with_non_bare_lhs_consistency_checks():
    # All three supplied: equation reduces to constant comparison.
    p = _NonBareLhs(a=3, b=7, foo=7)
    assert p.foo == pytest.approx(7.0)
    with pytest.raises(ValidationError):
        _NonBareLhs(a=3, b=7, foo=10)


class _NonInvertableMixed(Component):
    x = Param(float)
    y = Param(tuple)
    c = Param(float)
    equations = ["x * len(y) == c"]

    def build(self):
        return cube(1)


def test_eq_with_non_invertable_factor_rearranges():
    # ``x * len(y) == c`` solves x once y, c are known. ``len(y)`` folds
    # to a scalar after substitution and sympy isolates x.
    p = _NonInvertableMixed(y=(1, 2, 3, 4), c=12)
    assert p.x == pytest.approx(3.0)


class _LenEqConsistency(Component):
    size = Param(tuple)
    equations = ["len(size) == 3"]

    def build(self):
        return cube(1)


def test_len_eq_constant_is_equation_consistency_check():
    # Under the unified spec, ``len(size) == 3`` is an equation that
    # consistency-checks once size is known. Pre-spec it would have
    # been classified as a constraint; behavior is identical for the
    # passing path.
    _LenEqConsistency(size=(1, 2, 3))  # OK
    with pytest.raises(ValidationError):
        _LenEqConsistency(size=(1, 2))


# =============================================================================
# Spec compliance: feasibility filtering across the system-solve path
# =============================================================================


class _MultiBranch(Component):
    # Two solutions for half_angle from the asin: 52.7° and 127.3°. The
    # cross-equation constraint ``angle < 180`` rules out the second
    # via ``angle = 2 * half_angle``, leaving a unique solution.
    equations = [
        "max_d == 2 * groove_depth * sin(half_angle * pi / 180)",
        "angle == 2 * half_angle",
        "max_d, groove_depth, angle, half_angle > 0",
        "angle < 180",
    ]

    def build(self):
        return cube(1)


def test_multi_branch_disambiguated_by_cross_constraint():
    p = _MultiBranch(max_d=35, groove_depth=22)
    assert p.half_angle == pytest.approx(52.6982097, rel=1e-5)
    assert p.angle == pytest.approx(105.396419, rel=1e-5)


# =============================================================================
# Spec compliance: comma-broadcast `==` is the same as comma-broadcast `=`
# =============================================================================


def test_comma_eq_broadcast_is_equation():
    eqs, cons, _ = parse_equations_unified(["x, y == 5"])
    assert len(eqs) == 2
    assert len(cons) == 0


def test_comma_other_op_still_constraint():
    eqs, cons, _ = parse_equations_unified(["x, y > 0"])
    assert len(eqs) == 0
    assert len(cons) == 2


# =============================================================================
# Symmetric parser: any expression on either side of an equation
# =============================================================================
# The framework treats both halves of an equation as expressions in
# scadwright's language. Subscript and Attribute appearances are reads,
# never outputs — the resolver only fills in bare-Name unknowns.


class _LenEq(Component):
    size = Param(tuple)
    equations = ["len(size) = 3"]

    def build(self):
        return cube(1)


def test_len_eq_three_uses_single_equals():
    # ``len(size) = 3`` is a valid equation under the symmetric parser.
    # Identical semantics to ``len(size) == 3``.
    _LenEq(size=(1, 2, 3))
    with pytest.raises(ValidationError):
        _LenEq(size=(1, 2))


class _AttributeRead(Component):
    from collections import namedtuple as _nt
    Spec = _nt("Spec", "foo bar")
    spec = Param(Spec)
    equations = ["spec.foo = 5"]

    def build(self):
        return cube(1)


def test_attribute_in_equation_consistency_check():
    # ``spec.foo = 5`` reads ``spec.foo`` and consistency-checks.
    s = _AttributeRead.Spec(foo=5, bar=99)
    _AttributeRead(spec=s)
    bad = _AttributeRead.Spec(foo=7, bar=99)
    with pytest.raises(ValidationError):
        _AttributeRead(spec=bad)


class _SubscriptRead(Component):
    arr = Param(tuple)
    equations = ["arr[0] = 5"]

    def build(self):
        return cube(1)


def test_subscript_in_equation_consistency_check():
    # ``arr[0] = 5`` reads ``arr[0]`` and consistency-checks. Subscripts
    # never act as outputs; tuple Params are supplied as a whole.
    _SubscriptRead(arr=(5, 99, 99))
    with pytest.raises(ValidationError):
        _SubscriptRead(arr=(7, 99, 99))


class _NonInvertableLeft(Component):
    equations = ["max(a, b) = foo"]

    def build(self):
        return cube(1)


def test_max_eq_drives_bare_name_target():
    # ``max(a, b) = foo`` solves ``foo`` by forward-eval when a and b
    # are known.
    p = _NonInvertableLeft(a=3, b=7)
    assert p.foo == pytest.approx(7.0)


class _SympyRearrange(Component):
    equations = ["2 * x = 5"]

    def build(self):
        return cube(1)


def test_sympy_rearranges_through_arithmetic():
    # ``2 * x = 5`` with no bare-Name LHS — sympy isolates x.
    p = _SympyRearrange()
    assert p.x == pytest.approx(2.5)
