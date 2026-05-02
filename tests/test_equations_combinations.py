"""Equation-DSL stress tests: feature *mixtures*, not single features.

Existing equation tests cover each DSL feature in isolation
(optionals, tuples, conditionals, cardinality helpers, comma broadcast,
inline type tags). This file pins behavior of *combinations* — the
shapes users actually write. A regression in the resolver's iteration,
override pre-resolve, or constraint-evaluation order will likely show
up here first.

Phase 1 groups (per design_docs/MajorReview4_tests.md):
- A: optionals × derivations × constraints
- B: tuples / list / dict comprehensions
- C: conditionals (if/else) in equation RHS
- F: cardinality helpers in mixtures
- G: comma-broadcast edge cases
- I: inline `:type` × override × constraint
"""

from __future__ import annotations

import pytest

from scadwright import Component, Param
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# =============================================================================
# Group A — optionals × derivations × constraints
# =============================================================================


def test_A1_optional_in_arithmetic_with_or_zero_fallback():
    """`(?offset or 0) + base` — pin the truthy-or-zero behavior.

    The `or 0` collapses None to 0 *and* 0 to 0; the `total` derivation
    sees 0 either way. Caller-passed 0 must produce the same `total` as
    no input. (Different from the `is None` form, which would let an
    explicit 0 stay 0.)
    """
    class C(Component):
        equations = [
            "?offset > 0",
            "base > 0",
            "total = (?offset or 0) + base",
        ]

        def build(self):
            return cube(1)

    assert C(base=10).total == 10.0
    assert C(base=10, offset=3).total == 13.0


def test_A2_optional_gates_cross_constraint():
    class C(Component):
        equations = [
            "?max_w > 0",
            "w > 0",
            "w < ?max_w",
        ]

        def build(self):
            return cube(1)

    C(w=5)                    # max_w None: cross-constraint skips
    C(w=5, max_w=10)          # 5 < 10
    with pytest.raises(ValidationError, match="w < .?max_w"):
        C(w=10, max_w=5)


def test_A3_optional_used_with_or_in_derivation():
    """`?offset` used in arithmetic via `or` fallback — both modes."""
    class C(Component):
        equations = [
            "?offset > 0",
            "scaled = (?offset or 1) * 10",
        ]

        def build(self):
            return cube(1)

    a = C()
    assert a.scaled == 10.0           # or 1 → 10
    b = C(offset=3)
    assert b.scaled == 30.0


def test_A4_three_alternative_optionals_with_exactly_one():
    """ChamferedBox-style with three alternatives, each routed into a
    derivation through the truthy-or chain. Verify the chosen one wins."""
    class C(Component):
        equations = [
            "?fillet > 0",
            "?chamfer > 0",
            "?bevel > 0",
            "exactly_one(?fillet, ?chamfer, ?bevel)",
            "edge = ?fillet or ?chamfer or ?bevel",
        ]

        def build(self):
            return cube(1)

    assert C(fillet=2).edge == 2.0
    assert C(chamfer=3).edge == 3.0
    assert C(bevel=4).edge == 4.0
    with pytest.raises(ValidationError, match="exactly_one"):
        C()
    with pytest.raises(ValidationError, match="exactly_one"):
        C(fillet=2, chamfer=3)


def test_A5_override_pattern_referencing_another_override():
    """`?b = ?b or (?a + 1)` — `?a` resolves first via its own override,
    then `?b`'s pre-resolve uses the resolved value of `?a`."""
    class C(Component):
        equations = [
            "?a = ?a or 5",
            "?b = ?b or (?a + 1)",
        ]

        def build(self):
            return cube(1)

    c = C()
    assert c.a == 5.0
    assert c.b == 6.0
    c2 = C(a=10)
    assert c2.a == 10.0
    assert c2.b == 11.0
    c3 = C(a=10, b=20)
    assert c3.a == 10.0
    assert c3.b == 20.0


def test_A6_override_target_used_in_comprehension():
    """The override pre-resolve fills `?count`, then the comprehension
    in `positions` runs with the resolved value."""
    class C(Component):
        equations = [
            "pitch > 0",
            "?count:int = ?count or 4",
            "positions = tuple(i * pitch for i in range(count))",
        ]

        def build(self):
            return cube(1)

    a = C(pitch=2.0)
    assert a.count == 4
    assert a.positions == (0.0, 2.0, 4.0, 6.0)
    b = C(pitch=2.0, count=2)
    assert b.positions == (0.0, 2.0)


def test_A7_optional_with_explicit_is_not_none_and_zero_is_legitimate():
    """`?n = ?n if ?n is not None else 0` — explicit-None form lets 0
    survive (truthy-or would have replaced it)."""
    class C(Component):
        equations = [
            "?n = ?n if ?n is not None else 0",
        ]

        def build(self):
            return cube(1)

    assert C().n == 0.0
    assert C(n=0).n == 0.0          # explicit 0 stays 0
    assert C(n=5).n == 5.0


# =============================================================================
# Group B — tuples / list / dict comprehensions
# =============================================================================


def test_B1_tuple_length_and_element_constraint():
    class C(Component):
        equations = [
            "len(size:tuple) = 3",
            "all(s > 0 for s in size)",
        ]

        def build(self):
            return cube(1)

    C(size=(1, 2, 3))
    with pytest.raises(ValidationError, match="all"):
        C(size=(1, -2, 3))
    with pytest.raises(ValidationError, match="len"):
        C(size=(1, 2))


def test_B2_tuple_derivation_feeds_another_derivation():
    class C(Component):
        equations = [
            "len(size:tuple) = 3",
            "pad > 0",
            "padded = tuple(s + 2*pad for s in size)",
            "outer_volume = padded[0] * padded[1] * padded[2]",
        ]

        def build(self):
            return cube(1)

    c = C(size=(10, 20, 30), pad=1)
    assert c.padded == (12.0, 22.0, 32.0)
    assert c.outer_volume == pytest.approx(12 * 22 * 32)


def test_B3_comprehension_with_if_filter_referencing_derivation():
    class C(Component):
        equations = [
            "n:int > 0",
            "evens = tuple(i for i in range(n) if i % 2 == 0)",
        ]

        def build(self):
            return cube(1)

    assert C(n=6).evens == (0, 2, 4)
    assert C(n=1).evens == (0,)


def test_B4_nested_comprehension_grid():
    class C(Component):
        equations = [
            "rows:int > 0",
            "cols:int > 0",
            "grid = tuple((i, j) for i in range(rows) for j in range(cols))",
        ]

        def build(self):
            return cube(1)

    g = C(rows=2, cols=3).grid
    assert g == ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2))


def test_B5_dict_comprehension():
    """Dict comprehension at top level. The scanner must not treat the
    dict-key `:` as a `name:type` tag — bracket-depth tracking inside
    `{...}` suppresses tag recognition.
    """
    class C(Component):
        equations = [
            "n:int > 0",
            "pitch > 0",
            "lookup = {i: i * pitch for i in range(n)}",
        ]

        def build(self):
            return cube(1)

    c = C(n=3, pitch=5.0)
    assert c.lookup == {0: 0.0, 1: 5.0, 2: 10.0}


def test_B5b_dict_comprehension_workaround_with_str_key():
    """Workaround for the scanner bug: wrapping the key in a call
    sidesteps the bare-name-followed-by-colon trigger."""
    class C(Component):
        equations = [
            "n:int > 0",
            "pitch > 0",
            "lookup = {str(i): i * pitch for i in range(n)}",
        ]

        def build(self):
            return cube(1)

    c = C(n=3, pitch=5.0)
    assert c.lookup == {"0": 0.0, "1": 5.0, "2": 10.0}


def test_B6_list_comprehension_target_typed_list():
    class C(Component):
        equations = [
            "n:int > 0",
            "items = list(i*i for i in range(n))",
        ]

        def build(self):
            return cube(1)

    assert C(n=4).items == [0, 1, 4, 9]


def test_B7_tuple_of_tuples_corners():
    class C(Component):
        equations = [
            "w > 0",
            "h > 0",
            "corners = tuple((x, y) for x in (-w, w) for y in (-h, h))",
        ]

        def build(self):
            return cube(1)

    c = C(w=5, h=2)
    assert c.corners == ((-5.0, -2.0), (-5.0, 2.0), (5.0, -2.0), (5.0, 2.0))


def test_B8_comprehension_over_param_tuple():
    class C(Component):
        equations = [
            "len(size:tuple) > 0",
            "factor > 0",
            "scaled = tuple(s * factor for s in size)",
        ]

        def build(self):
            return cube(1)

    assert C(size=(1, 2, 3), factor=10).scaled == (10.0, 20.0, 30.0)


def test_B9_empty_comprehension_then_length_constraint():
    """`n=0` makes positions empty; the length constraint catches it."""
    class C(Component):
        equations = [
            "n:int >= 0",
            "pitch > 0",
            "positions = tuple(i * pitch for i in range(n))",
            "len(positions) > 0",
        ]

        def build(self):
            return cube(1)

    C(n=3, pitch=1)
    with pytest.raises(ValidationError):
        C(n=0, pitch=1)


# =============================================================================
# Group C — conditionals in equation RHS
# =============================================================================


def test_C1_nested_ternary_three_branches():
    class C(Component):
        equations = [
            "axis:str in ('x', 'y', 'z')",
            "v = 1 if axis == 'x' else 2 if axis == 'y' else 3",
        ]

        def build(self):
            return cube(1)

    assert C(axis="x").v == 1.0
    assert C(axis="y").v == 2.0
    assert C(axis="z").v == 3.0


def test_C2_ternary_picking_between_derivations():
    """Pick between two derivations via an optional bool default.

    Note: a standalone `?mode:bool` line is not a valid declaration
    (no operator), so the override pattern is used to declare and
    default the bool in one step.
    """
    class C(Component):
        equations = [
            "a > 0",
            "b > 0",
            "?mode:bool = False if ?mode is None else ?mode",
            "double = a * 2",
            "triple = b * 3",
            "pick = double if mode else triple",
        ]

        def build(self):
            return cube(1)

    assert C(a=2, b=3, mode=True).pick == 4.0   # double = 4
    assert C(a=2, b=3, mode=False).pick == 9.0  # triple = 9
    assert C(a=2, b=3).pick == 9.0              # mode None → False


def test_C3_compare_chain_in_ifexp_test():
    class C(Component):
        equations = [
            "x:int > 0",
            "tag = 'a' if x == 1 else 'b' if x == 2 else 'c'",
        ]

        def build(self):
            return cube(1)

    assert C(x=1).tag == "a"
    assert C(x=2).tag == "b"
    assert C(x=5).tag == "c"


def test_C4_conditional_over_optional_with_is_not_none():
    class C(Component):
        equations = [
            "?fillet > 0",
            "base > 0",
            "x = ?fillet * 2 if ?fillet is not None else base / 2",
        ]

        def build(self):
            return cube(1)

    assert C(base=10).x == 5.0          # base / 2
    assert C(base=10, fillet=3).x == 6.0  # 3 * 2


def test_C5_ifexp_with_boolop_in_test():
    class C(Component):
        equations = [
            "axis:str in ('xy', 'xz', 'yz')",
            "count:int > 0",
            "extra = 1 if axis == 'xy' and count > 2 else 0",
        ]

        def build(self):
            return cube(1)

    assert C(axis="xy", count=5).extra == 1.0
    assert C(axis="xy", count=1).extra == 0.0
    assert C(axis="xz", count=5).extra == 0.0


# =============================================================================
# Group F — cardinality helpers in mixtures
# =============================================================================


def test_F1_exactly_one_three_alternatives():
    class C(Component):
        equations = [
            "?a > 0",
            "?b > 0",
            "?c > 0",
            "exactly_one(?a, ?b, ?c)",
        ]

        def build(self):
            return cube(1)

    C(a=1)
    C(b=1)
    C(c=1)
    with pytest.raises(ValidationError, match="exactly_one"):
        C()
    with pytest.raises(ValidationError, match="exactly_one"):
        C(a=1, b=1)
    with pytest.raises(ValidationError, match="exactly_one"):
        C(a=1, b=1, c=1)


@pytest.mark.parametrize(
    "kwargs, ok",
    [
        ({}, False),
        ({"a": 1}, True),
        ({"b": 1}, True),
        ({"a": 1, "b": 1}, True),
        ({"a": 1, "b": 1, "c": 1}, True),
    ],
)
def test_F2_at_least_one_matrix(kwargs, ok):
    class C(Component):
        equations = [
            "?a > 0",
            "?b > 0",
            "?c > 0",
            "at_least_one(?a, ?b, ?c)",
        ]

        def build(self):
            return cube(1)

    if ok:
        C(**kwargs)
    else:
        with pytest.raises(ValidationError, match="at_least_one"):
            C(**kwargs)


@pytest.mark.parametrize(
    "kwargs, ok",
    [
        ({}, True),
        ({"a": 1}, True),
        ({"b": 1}, True),
        ({"a": 1, "b": 1}, False),
    ],
)
def test_F3_at_most_one_matrix(kwargs, ok):
    class C(Component):
        equations = [
            "?a > 0",
            "?b > 0",
            "at_most_one(?a, ?b)",
        ]

        def build(self):
            return cube(1)

    if ok:
        C(**kwargs)
    else:
        with pytest.raises(ValidationError, match="at_most_one"):
            C(**kwargs)


@pytest.mark.parametrize(
    "kwargs, ok",
    [
        ({}, True),
        ({"a": 1}, False),
        ({"a": 1, "b": 1}, False),
        ({"a": 1, "b": 1, "c": 1}, True),
    ],
)
def test_F4_all_or_none_three_args(kwargs, ok):
    class C(Component):
        equations = [
            "?a > 0",
            "?b > 0",
            "?c > 0",
            "all_or_none(?a, ?b, ?c)",
        ]

        def build(self):
            return cube(1)

    if ok:
        C(**kwargs)
    else:
        with pytest.raises(ValidationError, match="all_or_none"):
            C(**kwargs)


def test_F5_cardinality_with_downstream_derivation_and_check():
    """ChamferedBox-style: `exactly_one` selects, derivation names the
    chosen value, downstream constraint reads the derivation."""
    class C(Component):
        equations = [
            "?fillet > 0",
            "?chamfer > 0",
            "exactly_one(?fillet, ?chamfer)",
            "len(size:tuple) = 3",
            "edge = ?fillet if ?fillet else ?chamfer",
            "all(s > 2 * edge for s in size)",
        ]

        def build(self):
            return cube(1)

    C(size=(20, 15, 10), fillet=2)
    C(size=(20, 15, 10), chamfer=3)
    with pytest.raises(ValidationError, match="all"):
        C(size=(4, 4, 4), fillet=3)


def test_F6_cardinality_failure_names_args_and_values():
    class C(Component):
        equations = [
            "?a > 0",
            "?b > 0",
            "exactly_one(?a, ?b)",
        ]

        def build(self):
            return cube(1)

    with pytest.raises(ValidationError) as exc:
        C(a=2, b=3)
    msg = str(exc.value)
    # Both arg names and their values appear in the enriched message.
    assert "a=" in msg and "b=" in msg
    assert "2" in msg and "3" in msg


# =============================================================================
# Group G — comma-broadcast edge cases
# =============================================================================


def test_G1_comma_broadcast_constraint_three_names():
    class C(Component):
        equations = [
            "x, y, z > 0",
        ]

        def build(self):
            return cube(1)

    C(x=1, y=2, z=3)
    with pytest.raises(ValidationError, match="positive"):
        C(x=1, y=-2, z=3)
    with pytest.raises(ValidationError, match="positive"):
        C(x=1, y=2, z=-3)


def test_G2_comma_broadcast_equation_three_names_to_same_value():
    """`x, y, z = 5` produces three independent equations all pinning to 5."""
    class C(Component):
        equations = [
            "x, y, z = 5",
        ]

        def build(self):
            return cube(1)

    c = C()
    assert c.x == 5.0 and c.y == 5.0 and c.z == 5.0


def test_G3_comma_broadcast_cross_constraint_with_variable_rhs():
    class C(Component):
        equations = [
            "a, b, base > 0",
            "a, b < base",
        ]

        def build(self):
            return cube(1)

    C(a=1, b=2, base=10)
    with pytest.raises(ValidationError, match="a < base"):
        C(a=15, b=2, base=10)
    with pytest.raises(ValidationError, match="b < base"):
        C(a=1, b=15, base=10)


def test_G4_comma_broadcast_with_expression_rhs():
    """`a, b = c + 1` — both equations against the same expression.
    With `c` known, both `a` and `b` resolve to the same value."""
    class C(Component):
        equations = [
            "c > 0",
            "a, b = c + 1",
        ]

        def build(self):
            return cube(1)

    c = C(c=4)
    assert c.a == 5.0
    assert c.b == 5.0
    # Over-supplied consistent values pass.
    c2 = C(c=4, a=5)
    assert c2.b == 5.0
    # Inconsistent supply raises.
    with pytest.raises(ValidationError):
        C(c=4, a=99)


def test_G5_tuple_literal_rhs_with_matching_arity_rejected():
    """`x, y = (5, 7)` reads as broadcast not unpack — the framework
    rejects with a clear error when a literal-tuple RHS has matching
    arity."""
    with pytest.raises(ValidationError, match="comma broadcasts"):
        class C(Component):
            equations = ["x, y = (5, 7)"]

            def build(self):
                return cube(1)


def test_G6_comma_broadcast_with_optional_sigil_on_some_names():
    """`?a, ?b > 0` — both names auto-declare optional. Both constraints
    skip when omitted, both fire when set."""
    class C(Component):
        equations = ["?a, ?b > 0"]

        def build(self):
            return cube(1)

    C()                 # both None: both skip
    C(a=5)              # only a: a's check fires, b skips
    C(a=5, b=10)
    with pytest.raises(ValidationError, match="positive"):
        C(a=-1)


# =============================================================================
# Group I — inline `:type` × override × constraint
# =============================================================================


def test_I1_int_override_with_or_default():
    class C(Component):
        equations = [
            "?count:int = ?count or 1",
            "count >= 1",
        ]

        def build(self):
            return cube(1)

    assert C().count == 1
    assert isinstance(C().count, int)
    assert C(count=5).count == 5


def test_I2_bool_override_with_or_truthy_trap():
    """`?flag:bool = ?flag or False` — the truthy-or trap.

    When caller passes `False`, the `or False` collapses False to False
    (which is what we want here since the default is also False). When
    caller passes None or omits, default applies. Pin the resolved
    value across all three modes to lock semantics.
    """
    class C(Component):
        equations = [
            "?flag:bool = False if ?flag is None else ?flag",
        ]

        def build(self):
            return cube(1)

    assert C().flag is False
    assert C(flag=False).flag is False
    assert C(flag=True).flag is True


def test_I3_str_override_with_membership_constraint():
    class C(Component):
        equations = [
            "?axis:str = ?axis or 'z'",
            "axis in ('x', 'y', 'z')",
        ]

        def build(self):
            return cube(1)

    assert C().axis == "z"
    assert C(axis="x").axis == "x"
    with pytest.raises(ValidationError):
        C(axis="diagonal")


def test_I4_tuple_with_length_and_element_constraint():
    class C(Component):
        equations = [
            "len(size:tuple) = 3",
            "all(s > 0 for s in size)",
        ]

        def build(self):
            return cube(1)

    C(size=(1, 2, 3))
    with pytest.raises(ValidationError):
        C(size=(1, 2))
    with pytest.raises(ValidationError):
        C(size=(1, 0, 3))


def test_I5_int_param_drives_float_derivation_with_constraint():
    """`count:int >= 1` ; `pitch = 10 / count` ; `pitch > 0`."""
    class C(Component):
        equations = [
            "count:int >= 1",
            "pitch = 10 / count",
            "pitch > 0",
        ]

        def build(self):
            return cube(1)

    c = C(count=4)
    assert c.pitch == 2.5
    assert c.count == 4
    with pytest.raises(ValidationError):
        C(count=0)


def test_I6_int_override_with_arithmetic_rhs_rejected_at_classdef():
    """`?n:int = 2 * x` is NOT one of the accepted override shapes for
    a non-float type. Class-define-time error."""
    with pytest.raises(ValidationError, match="cannot be derived"):
        class C(Component):
            equations = [
                "x > 0",
                "?n:int = 2 * x",
            ]

            def build(self):
                return cube(1)


def test_I7_typed_tuple_override_with_empty_tuple_default():
    class C(Component):
        equations = [
            "?items:tuple = ?items if ?items is not None else ()",
        ]

        def build(self):
            return cube(1)

    assert C().items == ()
    assert isinstance(C().items, tuple)
    assert C(items=(1, 2, 3)).items == (1, 2, 3)
