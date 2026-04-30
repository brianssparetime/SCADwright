from __future__ import annotations

# Inline type annotations in equations (`name:type`, `?name:type`).
# Covers: scanner extraction, allowlist enforcement, auto-declare,
# `==` placement, asymmetric coercion, bool-in-arithmetic rejection,
# non-float-as-solver-target rejection, and the optional-name override
# pattern.

import pytest

from scadwright import Component, Param
from scadwright.component.equations import (
    _INLINE_TYPE_ALLOWLIST,
    _extract_name_annotations,
)
from scadwright.component.resolver import parse_equations_unified
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# =============================================================================
# Scanner: type-tag extraction
# =============================================================================


def test_scanner_extracts_basic_type_tag():
    cleaned, opt, typed = _extract_name_annotations("count:int = base + 1")
    assert cleaned == "count = base + 1"
    assert opt == set()
    assert typed == {"count": "int"}


def test_scanner_extracts_optional_type_tag():
    cleaned, opt, typed = _extract_name_annotations("?direction:bool")
    assert cleaned == "direction"
    assert opt == {"direction"}
    assert typed == {"direction": "bool"}


def test_scanner_extracts_tag_inside_expression():
    cleaned, opt, typed = _extract_name_annotations(
        "x = a if axis:str == 'xy' else b"
    )
    assert cleaned == "x = a if axis == 'xy' else b"
    assert typed == {"axis": "str"}


def test_scanner_extracts_multiple_tags_per_line():
    cleaned, opt, typed = _extract_name_annotations(
        "y = base + (count:int - 1) * spacing if ?direction:bool else 0"
    )
    assert "count" in typed and typed["count"] == "int"
    assert "direction" in typed and typed["direction"] == "bool"
    assert opt == {"direction"}


def test_scanner_ignores_slice_colons():
    # `a[1:2]` is a slice; the colon between `1` and `2` is not a type tag.
    cleaned, opt, typed = _extract_name_annotations("x = a[1:2]")
    assert cleaned == "x = a[1:2]"
    assert typed == {}


def test_scanner_ignores_dict_key_colons_in_strings():
    cleaned, opt, typed = _extract_name_annotations('d = {"a:int": 5}')
    assert cleaned == 'd = {"a:int": 5}'
    assert typed == {}


def test_scanner_requires_no_space_before_colon():
    # `count: int` (with a space) is NOT a type tag.
    cleaned, opt, typed = _extract_name_annotations("count: int = 5")
    assert typed == {}


def test_scanner_left_alone_inside_string_literal():
    cleaned, opt, typed = _extract_name_annotations(
        '?a > 0 and "axis:str = match"'
    )
    assert "a" in opt
    # The :str inside the string literal is not extracted.
    assert typed == {}


# =============================================================================
# Type allowlist
# =============================================================================


def test_allowlist_contains_expected_types():
    assert set(_INLINE_TYPE_ALLOWLIST) == {
        "bool", "int", "str", "tuple", "list", "dict",
    }


def test_unknown_type_tag_rejected():
    with pytest.raises(ValidationError, match="unknown type tag"):
        parse_equations_unified(["count:integer = 5"])


def test_disagreement_across_sites_rejected():
    with pytest.raises(ValidationError, match="type disagreement"):
        parse_equations_unified([
            "count:int > 0",
            "y = count:str",
        ])


# =============================================================================
# Auto-declare: each accepted type
# =============================================================================


def test_auto_declare_int():
    class C(Component):
        equations = ["count:int > 0", "y = count * 2"]
        def build(self): return cube(1)

    c = C(count=3)
    assert c.count == 3
    assert isinstance(c.count, int)
    assert C.__params__["count"].type is int


def test_auto_declare_bool():
    class C(Component):
        equations = ["x = 1 if ?direction:bool else 2"]
        def build(self): return cube(1)

    a = C(direction=True)
    assert a.direction is True and a.x == 1.0
    b = C()
    assert b.direction is None and b.x == 2.0


def test_auto_declare_str():
    class C(Component):
        equations = ["axis:str in ('x', 'y', 'z')"]
        def build(self): return cube(1)

    c = C(axis="y")
    assert c.axis == "y"
    assert C.__params__["axis"].type is str


def test_auto_declare_tuple():
    class C(Component):
        equations = ["len(size:tuple) = 3"]
        def build(self): return cube(1)

    c = C(size=(1, 2, 3))
    assert c.size == (1, 2, 3)
    assert C.__params__["size"].type is tuple


def test_auto_declare_list():
    class C(Component):
        equations = ["len(items:list) > 0"]
        def build(self): return cube(1)

    c = C(items=[1, 2])
    assert c.items == [1, 2]


def test_auto_declare_dict():
    class C(Component):
        equations = ["len(lookup:dict) > 0"]
        def build(self): return cube(1)

    c = C(lookup={"a": 1})
    assert c.lookup == {"a": 1}


# =============================================================================
# Required (no `?`) vs optional (`?name:type`)
# =============================================================================


def test_required_typed_param_must_be_supplied():
    class C(Component):
        equations = ["axis:str in ('x', 'y')"]
        def build(self): return cube(1)

    with pytest.raises(ValidationError, match="missing required"):
        C()


def test_optional_typed_param_defaults_to_none():
    class C(Component):
        equations = ["x = 1 if ?direction:bool else 2"]
        def build(self): return cube(1)

    c = C()
    assert c.direction is None


# =============================================================================
# Collision with explicit Param(...)
# =============================================================================


def test_inline_collision_with_param_raises():
    with pytest.raises(ValidationError, match="both an inline"):
        class C(Component):
            count = Param(int)
            equations = ["count:int > 0"]
            def build(self): return cube(1)


# =============================================================================
# `==` reclassification + placement
# =============================================================================


def test_top_level_eq_outside_if_rejected():
    with pytest.raises(ValidationError, match="`==` as a top-level"):
        parse_equations_unified(["a == 5"])


def test_eq_inside_ifexp_test_allowed():
    eqs, _, _, _ = parse_equations_unified(["x = a if count == 1 else b"])
    assert len(eqs) == 1


def test_eq_with_boolop_in_ifexp_test_allowed():
    eqs, _, _, _ = parse_equations_unified([
        "x = a if axis == 'xy' and count > 0 else b",
    ])
    assert len(eqs) == 1


def test_assign_eq_still_works():
    # `=` is the equation operator; `==` is no longer accepted.
    eqs, _, _, _ = parse_equations_unified(["od = id + 2*thk"])
    assert len(eqs) == 1


# =============================================================================
# Asymmetric coercion: int → float widens, others strict
# =============================================================================


def test_int_to_float_widens():
    # No tag — auto-declared as float. Passing int widens losslessly.
    class C(Component):
        equations = ["thk > 0", "od = id + 2 * thk"]
        def build(self): return cube(1)

    c = C(id=8, thk=1)
    assert c.thk == 1.0
    assert isinstance(c.thk, float)


def test_int_tag_rejects_float():
    class C(Component):
        equations = ["count:int > 0"]
        def build(self): return cube(1)

    with pytest.raises(ValidationError, match="expected int"):
        C(count=3.0)


def test_int_tag_rejects_bool():
    class C(Component):
        equations = ["count:int > 0"]
        def build(self): return cube(1)

    with pytest.raises(ValidationError, match="expected int, got bool"):
        C(count=True)


def test_bool_tag_rejects_int():
    class C(Component):
        equations = ["x = 1 if ?direction:bool else 2"]
        def build(self): return cube(1)

    with pytest.raises(ValidationError, match="expected bool"):
        C(direction=1)


def test_str_tag_rejects_non_str():
    class C(Component):
        equations = ["axis:str in ('x', 'y')"]
        def build(self): return cube(1)

    with pytest.raises(ValidationError, match="expected str"):
        C(axis=42)


def test_tuple_tag_rejects_list():
    class C(Component):
        equations = ["len(size:tuple) = 3"]
        def build(self): return cube(1)

    with pytest.raises(ValidationError, match="expected tuple"):
        C(size=[1, 2, 3])


# Truthiness still works — type tags don't intervene once a value is bound.
def test_truthiness_unaffected_for_optional_bool():
    class C(Component):
        equations = ["x = 1 if ?direction:bool else 2"]
        def build(self): return cube(1)

    assert C(direction=True).x == 1.0
    assert C(direction=False).x == 2.0
    assert C().x == 2.0   # None is falsy


# =============================================================================
# Bool-in-arithmetic rejection
# =============================================================================


def test_bool_in_binop_rejected():
    with pytest.raises(ValidationError, match="bool-tagged"):
        class C(Component):
            equations = ["x = direction:bool * 2"]
            def build(self): return cube(1)


def test_bool_in_numeric_call_rejected():
    with pytest.raises(ValidationError, match="bool-tagged"):
        class C(Component):
            equations = ["x = sin(direction:bool)"]
            def build(self): return cube(1)


def test_bool_in_conditional_allowed():
    # Truthiness use is fine — that's what bool is for.
    class C(Component):
        equations = ["x = 1 if direction:bool else 2"]
        def build(self): return cube(1)

    assert C(direction=True).x == 1.0


# =============================================================================
# Non-float as solver target rejection
# =============================================================================


def test_non_float_as_solver_target_rejected():
    with pytest.raises(
        ValidationError, match="cannot be derived from an equation"
    ):
        class C(Component):
            equations = ["count:int = total / size"]
            def build(self): return cube(1)


def test_non_float_as_solver_target_rhs_rejected():
    with pytest.raises(
        ValidationError, match="cannot be derived from an equation"
    ):
        class C(Component):
            equations = ["total / size = count:int"]
            def build(self): return cube(1)


def test_non_float_as_input_allowed():
    # count:int is an input; size is the solver target.
    class C(Component):
        equations = ["total = count:int * size", "size > 0", "total > 0"]
        def build(self): return cube(1)

    c = C(count=3, total=15)
    assert c.size == 5.0


# =============================================================================
# Optional-name override pattern
# =============================================================================


def test_override_or_form():
    class C(Component):
        equations = ["?dividers:int = ?dividers or 1"]
        def build(self): return cube(1)

    a = C()
    assert a.dividers == 1
    b = C(dividers=4)
    assert b.dividers == 4


def test_override_is_none_form():
    class C(Component):
        equations = ["?count:int = 3 if ?count is None else ?count"]
        def build(self): return cube(1)

    assert C().count == 3
    assert C(count=7).count == 7


def test_override_is_not_none_form():
    class C(Component):
        equations = ["?n:int = ?n if ?n is not None else 5"]
        def build(self): return cube(1)

    assert C().n == 5
    assert C(n=12).n == 12


def test_override_with_other_name_in_rhs():
    # The override RHS may reference other names; the iterative loop
    # fills the override target after those names resolve.
    class C(Component):
        x = Param(float, default=2.0)
        equations = ["?pitch = 3 * x"]
        def build(self): return cube(1)

    c = C()
    assert c.pitch == 6.0


def test_non_float_override_rejected_when_rhs_uses_target_in_arithmetic():
    # `?n:int = n + 1` is NOT one of the accepted override shapes.
    with pytest.raises(
        ValidationError, match="cannot be derived from an equation"
    ):
        class C(Component):
            equations = ["?n:int = ?n + 1"]
            def build(self): return cube(1)


def test_user_supplied_override_consistency_check():
    # When the user supplies the value, the equation consistency-checks.
    class C(Component):
        equations = ["?count:int = 3 if ?count is None else ?count"]
        def build(self): return cube(1)

    c = C(count=7)
    assert c.count == 7  # consistency: 7 == (7 if 7 is None else 7) == 7


# =============================================================================
# Existing patterns still work (regression guards)
# =============================================================================


def test_cardinality_helper_with_optionals_still_works():
    # ?fillet and ?chamfer are NOT equation targets, so they keep
    # their None-means-not-supplied semantic and the cardinality
    # helper works as before.
    class C(Component):
        size = Param(tuple)
        equations = [
            "?fillet > 0",
            "?chamfer > 0",
            "len(size) = 3",
            "exactly_one(?fillet, ?chamfer)",
            "edge = ?fillet if ?fillet else ?chamfer",
            "all(s > 2 * edge for s in size)",
        ]
        def build(self): return cube(1)

    c = C(size=(20, 15, 10), fillet=2)
    assert c.edge == 2.0
    d = C(size=(20, 15, 10), chamfer=3)
    assert d.edge == 3.0
