"""Tests for the `?` optional-Param sigil in equations.

`?name` anywhere in an equations string auto-declares
`Param(float, default=None)` — the opt-out pattern without the separate
Param declaration. Constraints and cross-constraints skip when the value
is None; predicates and derivations see the value as None and handle it
via the user's own expression.
"""

from __future__ import annotations

import pytest

from scadwright import Component, Param
from scadwright.component.equations import _extract_optional_markers
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# =============================================================================
# Tokenizer unit tests
# =============================================================================


def test_strip_simple_marker():
    cleaned, opts = _extract_optional_markers("?fillet > 0")
    assert cleaned == "fillet > 0"
    assert opts == {"fillet"}


def test_strip_multiple_markers():
    cleaned, opts = _extract_optional_markers("(?a is None) != (?b is None)")
    assert cleaned == "(a is None) != (b is None)"
    assert opts == {"a", "b"}


def test_leaves_unmarked_names_alone():
    cleaned, opts = _extract_optional_markers("a + b + c")
    assert cleaned == "a + b + c"
    assert opts == set()


def test_ignores_question_inside_single_string():
    cleaned, opts = _extract_optional_markers("series in ('?AA', 'AAA')")
    assert cleaned == "series in ('?AA', 'AAA')"
    assert opts == set()


def test_ignores_question_inside_double_string():
    cleaned, opts = _extract_optional_markers('name == "?mystery"')
    assert cleaned == 'name == "?mystery"'
    assert opts == set()


def test_ignores_question_inside_triple_quoted_string():
    cleaned, opts = _extract_optional_markers('x == """?foo"""')
    assert cleaned == 'x == """?foo"""'
    assert opts == set()


def test_strips_around_string_literals():
    cleaned, opts = _extract_optional_markers("?a > 0 and '?b' == '?b'")
    assert cleaned == "a > 0 and '?b' == '?b'"
    assert opts == {"a"}


def test_handles_backslash_escapes_in_strings():
    """`?y` inside a backslash-escaped string stays; outer `?x` is stripped."""
    cleaned, opts = _extract_optional_markers("?x > 0 and s == 'has \\'?y\\' inside'")
    assert opts == {"x"}                         # only the outer ?x was stripped
    assert cleaned.startswith("x > 0")           # outer sigil gone
    assert "?y" in cleaned                       # inner ?y preserved (was in a string)


def test_question_followed_by_non_identifier_left_alone():
    # `?5` and `? foo` (with space) don't match the sigil.
    cleaned, opts = _extract_optional_markers("?5 + ? foo")
    assert cleaned == "?5 + ? foo"
    assert opts == set()


# =============================================================================
# Declaration
# =============================================================================


def test_question_auto_declares_param_float_default_none():
    class C(Component):
        equations = ["?fillet > 0"]
        def build(self): return cube(1)

    # No fillet supplied: default=None applies, construction succeeds.
    c = C()
    assert c.fillet is None


def test_question_with_value_supplied():
    class C(Component):
        equations = ["?fillet > 0"]
        def build(self): return cube(1)

    c = C(fillet=3.5)
    assert c.fillet == 3.5


def test_question_param_frozen_after_construction():
    """Freeze fires for a Component with an equality/derivation/predicate;
    `?`-declared Params are frozen alongside explicit Params."""
    class C(Component):
        equations = [
            "?fillet > 0",
            "edge = ?fillet if ?fillet else 1",   # derivation → triggers freeze
        ]
        def build(self): return cube(1)

    c = C(fillet=2.0)
    with pytest.raises(ValidationError, match="frozen"):
        c.fillet = 5.0


# =============================================================================
# Per-kind behavior
# =============================================================================


def test_constraint_skips_validator_when_none():
    """`?fillet > 0` with fillet omitted: constraint skips (value is None)."""
    class C(Component):
        equations = ["?fillet > 0"]
        def build(self): return cube(1)

    c = C()
    assert c.fillet is None


def test_constraint_validates_when_set():
    class C(Component):
        equations = ["?fillet > 0"]
        def build(self): return cube(1)

    C(fillet=5)
    with pytest.raises(ValidationError, match="positive"):
        C(fillet=-1)


def test_cross_constraint_skips_when_none():
    """Cross-constraint with `?` skips when the optional side is None."""
    class C(Component):
        equations = [
            "thk > 0",
            "?fillet < thk",
        ]
        def build(self): return cube(1)

    C(thk=3.0)                 # fillet=None → cross-constraint skips
    C(thk=3.0, fillet=2.0)     # satisfied
    with pytest.raises(ValidationError):
        C(thk=3.0, fillet=5.0)  # violated


def test_predicate_xor_with_is_none():
    """XOR via `is None` on two `?`-marked Params."""
    class C(Component):
        equations = [
            "?fillet > 0",
            "?chamfer > 0",
            "(?fillet is None) != (?chamfer is None)",
        ]
        def build(self): return cube(1)

    C(fillet=3)
    C(chamfer=3)
    with pytest.raises(ValidationError):
        C()                               # neither
    with pytest.raises(ValidationError):
        C(fillet=3, chamfer=3)            # both


def test_derivation_with_truthy_conditional():
    """Truthy conditional over `?`-marked Params."""
    class C(Component):
        equations = [
            "?fillet > 0",
            "?chamfer > 0",
            "edge = ?fillet if ?fillet else ?chamfer",
        ]
        def build(self): return cube(1)

    a = C(fillet=3)
    assert a.edge == 3

    b = C(chamfer=5)
    assert b.edge == 5


# =============================================================================
# Class-definition errors
# =============================================================================


def test_top_level_eq_outside_if_raises():
    # ``?fillet == x + 1`` is no longer an equation; ``==`` is a Python
    # comparison and is rejected when it appears outside an ``if``
    # condition. The old ``=``-form rejection (target marked optional)
    # is covered by ``test_question_on_assign_target_raises`` below.
    with pytest.raises(ValidationError, match="`==` as a top-level"):
        class C(Component):
            equations = ["?fillet == x + 1"]
            def build(self): return cube(1)


def test_question_on_assign_target_resolves_via_equation():
    # An equation `?pitch = 2 * x` makes `pitch` optional: when the
    # user doesn't supply it, the equation fills the value (the
    # optional-default override path). When the user does supply it,
    # the equation consistency-checks.
    class C(Component):
        x = Param(float, default=1.0)
        equations = ["?pitch = 2 * x"]
        def build(self): return cube(1)

    c = C()
    assert c.pitch == 2.0
    c2 = C(pitch=4.0, x=2.0)
    assert c2.pitch == 4.0


def test_question_on_reserved_name_raises():
    with pytest.raises(ValidationError, match="reserved name"):
        class C(Component):
            equations = ["?all > 0"]
            def build(self): return cube(1)


def test_question_on_reserved_math_name_raises():
    with pytest.raises(ValidationError, match="reserved name"):
        class C(Component):
            equations = ["?sin > 0"]
            def build(self): return cube(1)


# =============================================================================
# Interactions with explicit declarations
# =============================================================================


def test_explicit_param_wins_over_sigil():
    """An explicit Param with a non-None default isn't overridden by ?."""
    class C(Component):
        fillet = Param(float, default=5.0)
        equations = ["?fillet > 0"]
        def build(self): return cube(1)

    # The explicit default (5.0) wins; optional-auto-decl is a no-op.
    c = C()
    assert c.fillet == 5.0


def test_multiple_lines_share_sigil_declaration():
    """Multiple lines referencing ?name all share one auto-declared Param."""
    class C(Component):
        equations = [
            "?fillet > 0",
            "?fillet < 10",
        ]
        def build(self): return cube(1)

    C()               # both constraints skip when fillet is None
    C(fillet=5)       # both constraints satisfied
    with pytest.raises(ValidationError):
        C(fillet=15)  # upper bound violated


def test_question_with_downstream_use_in_build():
    """`?`-declared Params are accessible in build() via self.name."""
    class C(Component):
        equations = ["?extra > 0", "base > 0"]
        def build(self):
            side = self.base + (self.extra if self.extra else 0)
            return cube(side)

    c = C(base=10)
    assert c.extra is None
    c2 = C(base=10, extra=5)
    assert c2.extra == 5
