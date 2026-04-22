"""Regression tests for user-facing error messages.

These tests pin the exact substrings that should appear in framework
errors so silent message degradation gets caught. If a message changes
for a good reason, update the expected substring — don't weaken the
check.
"""

from __future__ import annotations

from collections import namedtuple

import pytest

from scadwright import Component, Param, anchor, bbox
from scadwright.boolops import difference, union
from scadwright.errors import BuildError, ValidationError
from scadwright.primitives import circle, cube, cylinder
from scadwright.render import render


# =============================================================================
# Param type coercion
# =============================================================================


def test_param_int_rejects_non_integer_float():
    """Param(int) must not silently truncate 3.5 to 3."""
    class C(Component):
        count = Param(int, positive=True)
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C(count=3.5)
    msg = str(exc_info.value)
    assert "C.count" in msg
    assert "expected int" in msg
    assert "3.5" in msg
    # The message hints at the silent-truncation risk explicitly.
    assert "truncate" in msg


def test_param_int_accepts_integer_valued_float():
    """Param(int) should accept 3.0 (integer-valued float)."""
    class C(Component):
        count = Param(int, positive=True)
        def build(self): return cube([1, 1, 1])

    c = C(count=3.0)
    assert c.count == 3
    assert isinstance(c.count, int)


def test_param_int_rejects_string_cleanly():
    class C(Component):
        count = Param(int, positive=True)
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C(count="not a number")
    msg = str(exc_info.value)
    assert "C.count" in msg
    assert "cannot coerce" in msg


def test_param_namedtuple_wrong_type_clean_error():
    """Passing a string where a namedtuple is expected gives a clear error."""
    Spec = namedtuple("Spec", "a b c")
    class C(Component):
        spec = Param(Spec)
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C(spec="not a spec")
    msg = str(exc_info.value)
    assert "C.spec" in msg
    assert "cannot coerce" in msg
    assert "Spec" in msg


def test_param_bool_rejected_where_int_expected():
    """isinstance(True, int) is True in Python; Param(int) must still reject bool."""
    class C(Component):
        count = Param(int, positive=True)
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C(count=True)
    msg = str(exc_info.value)
    assert "got bool" in msg


# =============================================================================
# through() on degenerate bbox
# =============================================================================


def test_through_on_2d_shape_errors_clearly():
    c = circle(r=5)
    box = cube([10, 10, 10])
    with pytest.raises(ValidationError) as exc_info:
        c.through(box)
    msg = str(exc_info.value)
    assert "through" in msg
    assert "zero extent" in msg
    assert "linear_extrude" in msg or "rotate_extrude" in msg


def test_through_non_overlapping_error_unchanged():
    """The pre-existing no-overlap error should continue to fire."""
    box = cube([10, 10, 10])
    cutter = cylinder(h=2, r=1).translate([100, 100, 100])
    with pytest.raises(ValidationError) as exc_info:
        cutter.through(box)
    msg = str(exc_info.value)
    assert "through" in msg
    assert "overlap" in msg


# =============================================================================
# Equation solver error messages
# =============================================================================


def test_contradictory_constant_equations():
    """a == 1 AND a == 2 with no user input identifies as inconsistent."""
    class C(Component):
        equations = ["a == 1", "a == 2"]
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C()
    msg = str(exc_info.value)
    assert "inconsistent" in msg
    assert "a" in msg
    assert "`a == 1`" in msg
    assert "`a == 2`" in msg


def test_contradictory_expression_equations():
    """Non-constant contradictions (a+b==1, a+b==5) also flagged."""
    class C(Component):
        equations = ["a + b == 1", "a + b == 5"]
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C()
    msg = str(exc_info.value)
    assert "inconsistent" in msg


def test_underspecified_equations_lists_options():
    """Underspecified case still produces 'need one of: {...}'."""
    class C(Component):
        equations = ["a + b + c == 10", "a, b, c > 0"]
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C(a=3)
    msg = str(exc_info.value)
    assert "cannot solve" in msg
    assert "need one of" in msg


def test_equation_violated_with_user_inputs():
    """Single equation with a contradicting user value gives a clean error."""
    class C(Component):
        equations = ["a == 5"]
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C(a=7)
    msg = str(exc_info.value)
    assert "equation violated" in msg
    assert "a == 5" in msg
    assert "7" in msg


def test_unknown_equation_function_caught_at_class_def():
    """Typo in a math function name is caught when the class is defined."""
    with pytest.raises(ValidationError) as exc_info:
        class C(Component):
            equations = ["y == snh(x)", "x, y > 0"]
            def build(self): return cube([1, 1, 1])
    msg = str(exc_info.value)
    assert "cannot parse equation" in msg or "cannot parse" in msg


# =============================================================================
# Params
# =============================================================================


def test_missing_required_params_listed():
    class C(Component):
        equations = ["w, h, d > 0"]
        def build(self): return cube([self.w, self.h, self.d])

    with pytest.raises(ValidationError) as exc_info:
        C()
    msg = str(exc_info.value)
    assert "C" in msg
    assert "missing required parameter" in msg
    # All three missing params should be listed.
    assert "w" in msg and "h" in msg and "d" in msg


def test_unknown_kwarg_listed():
    class C(Component):
        equations = ["w, h > 0"]
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C(w=10, h=20, wdith=5)  # typo
    msg = str(exc_info.value)
    assert "unknown parameter" in msg
    assert "wdith" in msg


def test_constraint_violation_names_field_and_value():
    class C(Component):
        equations = ["w, h > 0"]
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C(w=10, h=-5)
    msg = str(exc_info.value)
    assert "C.h" in msg
    assert "positive" in msg
    assert "-5" in msg


# =============================================================================
# Anchors and attach()
# =============================================================================


def test_attach_unknown_anchor_suggests_available():
    class Plate(Component):
        equations = ["w, h, thk > 0"]
        top_face = anchor(at="w/2, h/2, thk", normal=(0, 0, 1))
        def build(self): return cube([self.w, self.h, self.thk])

    p = Plate(w=20, h=20, thk=3)
    with pytest.raises(ValidationError) as exc_info:
        cylinder(h=5, r=2).attach(p, face="nonexistnt")
    msg = str(exc_info.value)
    assert "attach" in msg
    assert "nonexistnt" in msg
    # The list of valid anchors should be shown (it includes 'top_face').
    assert "top_face" in msg


def test_attach_custom_anchor_on_primitive_errors_with_guidance():
    """Using a custom anchor name on a primitive must tell the user
    that primitives only have standard face names."""
    a = cube([10, 10, 10])
    b = cube([5, 5, 5])
    with pytest.raises(ValidationError) as exc_info:
        b.attach(a, face="top", at="custom_thing")
    msg = str(exc_info.value)
    assert "custom anchor" in msg
    assert "Components" in msg or "Component" in msg


def test_anchor_at_expr_unknown_symbol():
    """anchor(at=...) referencing an undeclared name fails with the
    offending name in the message."""
    class C(Component):
        equations = ["w, h > 0"]
        bad = anchor(at="w/2, nonexistent, 0", normal=(0, 0, 1))
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C(w=10, h=5)
    msg = str(exc_info.value)
    assert "bad" in msg
    assert "nonexistent" in msg


# =============================================================================
# build() missing
# =============================================================================


def test_missing_build_caught_at_render_time():
    """A Component without build() can be instantiated (so published
    attributes remain readable), but rendering it produces a clear
    error that names the class."""
    class NoBuild(Component):
        equations = ["w > 0"]

    nb = NoBuild(w=5)  # construction fine — allows reading equation-solved attrs
    assert nb.w == 5

    with pytest.raises(BuildError) as exc_info:
        render(nb, "/tmp/nobuild.scad")
    msg = str(exc_info.value)
    assert "NoBuild" in msg
    assert "build" in msg


# =============================================================================
# Derivations and predicates
# =============================================================================


def test_derivation_collision_with_param_names_param():
    with pytest.raises(ValidationError) as exc_info:
        class C(Component):
            x = Param(float)
            equations = ["x = 5"]
            def build(self): return cube([1, 1, 1])
    msg = str(exc_info.value)
    assert "collides with Param" in msg
    assert "'x'" in msg


def test_derivation_undefined_name_message_includes_raw():
    class C(Component):
        equations = ["a > 0", "b = a + unknown"]
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C(a=5)
    msg = str(exc_info.value)
    assert "derivation" in msg
    assert "b = a + unknown" in msg
    assert "unknown" in msg


def test_derivation_syntax_error_class_def_time():
    with pytest.raises(ValidationError) as exc_info:
        class C(Component):
            equations = ["pitch = (incomplete"]
            def build(self): return cube([1, 1, 1])
    assert "cannot parse" in str(exc_info.value)


def test_predicate_failure_compare_shows_values():
    from collections import namedtuple
    Spec = namedtuple("Spec", "length")
    class C(Component):
        spec = Param(Spec)
        equations = ["depth > 0", "depth < spec.length"]
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C(spec=Spec(length=40.0), depth=50.0)
    msg = str(exc_info.value)
    assert "depth < spec.length" in msg
    assert "left=50.0" in msg
    assert "right=40.0" in msg


def test_predicate_failure_all_shows_offending_index():
    from collections import namedtuple
    E = namedtuple("E", "dia")
    class C(Component):
        elements = Param(tuple)
        cap = Param(float, positive=True)
        equations = ["all(e.dia <= cap for e in elements)"]
        def build(self): return cube([1, 1, 1])

    with pytest.raises(ValidationError) as exc_info:
        C(elements=(E(5.0), E(8.0), E(20.0)), cap=10.0)
    msg = str(exc_info.value)
    assert "index 2" in msg
    assert "left=20.0" in msg
    assert "right=10.0" in msg


def test_predicate_not_boolean_shape_rejected_at_class_def():
    with pytest.raises(ValidationError) as exc_info:
        class C(Component):
            equations = ["len(size)"]  # no comparison — ambiguous as a predicate
            def build(self): return cube([1, 1, 1])
    assert "not a boolean predicate" in str(exc_info.value)
