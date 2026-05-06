"""The ``adjusted(name)`` rule marker.

Inside a constraint expression, ``adjusted(name)`` reads the post-
adjustment value of ``name`` while bare-name references continue to
read the pre-adjustment (design-intent) value. The marker is only
valid in rules; using it in an equation or an adjustment's RHS is a
class-def-time error.
"""

from __future__ import annotations

import pytest

from scadwright import Component, Param
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# =============================================================================
# Default semantics: rules see pre-adjust values
# =============================================================================


def test_bare_name_in_rule_reads_pre_adjust():
    """A constraint like ``x > 5`` evaluates against the pre-adjust
    value of ``x``. Adjustments are layered after — by design — so a
    rule expressing a design-intent invariant (slip-fit, mating
    geometry) is unaffected by printer-error fudges."""

    class C(Component):
        equations = """
            x = 5.5
            x > 5     # holds against pre-adjust 5.5
            x -= 1.0  # post-adjust = 4.5; would FAIL `x > 5` if read here
        """

        def build(self):
            return cube(self.x)

    # No exception: pre-adjust 5.5 > 5 is true.
    c = C()
    assert c.x == pytest.approx(4.5)  # post-adjust value emitted


def test_bare_name_pre_adjust_violation_still_raises():
    """The pre-adjust rule fires before adjustments are layered on, so
    a violation on the pre-adjust value raises during resolution. The
    error message uses the per-Param validator format
    ("must be > 5.0, got 4.0") because the resolver delegates to it
    for ``name OP num`` shapes."""

    class C(Component):
        equations = """
            x = 4.0
            x > 5    # fails against pre-adjust 4.0
            x += 5   # post-adjust would be 9, but rule fired pre-adjust
        """

        def build(self):
            return cube(self.x)

    with pytest.raises(ValidationError, match=r"must be > 5\.0"):
        C()


# =============================================================================
# Opt-in: ``adjusted(name)`` reads post-adjust
# =============================================================================


def test_adjusted_name_reads_post_adjust():
    class C(Component):
        equations = """
            x = 4.0
            x += 1.5  # post-adjust = 5.5
            adjusted(x) > 5
        """

        def build(self):
            return cube(self.x)

    c = C()
    assert c.x == pytest.approx(5.5)


def test_adjusted_name_post_adjust_violation_raises():
    class C(Component):
        equations = """
            x = 5.5
            x -= 1.0   # post-adjust = 4.5
            adjusted(x) > 5
        """

        def build(self):
            return cube(self.x)

    with pytest.raises(ValidationError, match="constraint violated"):
        C()


# =============================================================================
# Mixed rules
# =============================================================================


def test_mixed_rule_pre_and_post_in_one_expression():
    """A single rule expression may freely mix pre-adjust bare names
    and ``adjusted(name)`` wrappers. Bare ``other`` reads pre-adjust;
    ``adjusted(x)`` reads post-adjust."""

    class C(Component):
        equations = """
            x = 4.0
            other = 6.0
            x += 1.0          # post-adjust x = 5.0
            adjusted(x) < other   # 5.0 < 6.0 → ok
        """

        def build(self):
            return cube(self.x)

    assert C().x == pytest.approx(5.0)


def test_mixed_rule_violation():
    class C(Component):
        equations = """
            x = 4.0
            other = 4.5
            x += 1.0          # post-adjust = 5.0
            adjusted(x) < other   # 5.0 < 4.5 → fails
        """

        def build(self):
            return cube(self.x)

    with pytest.raises(ValidationError, match="constraint violated"):
        C()


# =============================================================================
# Skipped adjustments leave adjusted() == pre-adjust
# =============================================================================


def test_skipped_adjustment_makes_adjusted_equal_pre_adjust():
    """When an adjustment is skipped (None RHS, etc.), the post-adjust
    value equals the pre-adjust value, so ``adjusted(x)`` reads the
    same as bare ``x``."""

    class C(Component):
        equations = """
            ?slop > 0       # plain optional, stays None unless supplied
            x = 5.5
            x += slop       # skips when slop is None
            adjusted(x) > 5
        """

        def build(self):
            return cube(self.x)

    # slop unsupplied → adjustment skips → x stays at 5.5 → 5.5 > 5 ok
    assert C().x == pytest.approx(5.5)


# =============================================================================
# Class-def-time validation: adjusted() outside rules
# =============================================================================


def test_adjusted_in_equation_rhs_rejected():
    with pytest.raises(
        ValidationError,
        match=r"`adjusted\(\.\.\.\)` is only valid inside a rule",
    ):
        class C(Component):
            equations = """
                x = 5
                y = adjusted(x) + 1
            """

            def build(self):
                return cube(self.y)


def test_adjusted_in_adjustment_rhs_rejected():
    with pytest.raises(
        ValidationError,
        match=r"`adjusted\(\.\.\.\)` is only valid inside a rule",
    ):
        class C(Component):
            equations = """
                x = 5
                y = 7
                x += adjusted(y)
            """

            def build(self):
                return cube(self.x)


def test_adjusted_with_no_args_rejected():
    with pytest.raises(
        ValidationError,
        match="exactly one argument",
    ):
        class C(Component):
            equations = """
                x = 5
                adjusted() > 0
            """

            def build(self):
                return cube(self.x)


def test_adjusted_with_multiple_args_rejected():
    with pytest.raises(
        ValidationError,
        match="exactly one argument",
    ):
        class C(Component):
            equations = """
                x = 5
                y = 7
                adjusted(x, y) > 0
            """

            def build(self):
                return cube(self.x)


def test_adjusted_with_non_name_arg_rejected():
    with pytest.raises(
        ValidationError,
        match="must be a bare name",
    ):
        class C(Component):
            equations = """
                x = 5
                adjusted(x + 1) > 0
            """

            def build(self):
                return cube(self.x)


def test_adjusted_with_keyword_arg_rejected():
    with pytest.raises(
        ValidationError,
        match="does not accept keyword arguments",
    ):
        class C(Component):
            equations = """
                x = 5
                adjusted(name=x) > 0
            """

            def build(self):
                return cube(self.x)


# =============================================================================
# Auto-declare interaction
# =============================================================================


def test_adjusted_wrapped_name_auto_declares():
    """A name that appears ONLY inside ``adjusted(...)`` still becomes
    a Param via auto-declare (because the wrapped name is included in
    referenced_names)."""

    class C(Component):
        equations = """
            x = 5.0
            x += 0.3
            adjusted(x) > 5
        """

        def build(self):
            return cube(self.x)

    # x got auto-declared and survives; adjustment fires; rule passes.
    assert C().x == pytest.approx(5.3)


def test_adjusted_does_not_become_param():
    """The ``adjusted`` name itself is a syntactic form, not a value
    reference. It must not be auto-declared as a Param."""

    class C(Component):
        equations = """
            x = 5.0
            x += 0.3
            adjusted(x) > 5
        """

        def build(self):
            return cube(self.x)

    assert "adjusted" not in C.__params__
