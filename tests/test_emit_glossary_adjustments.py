"""Glossary inline rendering for adjustment provenance.

When a name carries one or more applied adjustments, the glossary
line shows the full source-to-literal path: starting value, the
chain of operations with their comments, and the post-adjust value
that appears in the emitted geometry below.
"""

from __future__ import annotations

from scadwright import Component
from scadwright.emit import emit_str
from scadwright.primitives import cube


# =============================================================================
# Adjusted derivation: ``name = expr <chain> = post_value``
# =============================================================================


def test_derived_name_with_one_additive_adjustment():
    class C(Component):
        equations = """
            a = 4.0
            b = 1.0
            x = a + b
            x += 0.3  # printer overshoot
        """

        def build(self):
            return cube(self.x)

    out = emit_str(C())
    # Expression on the left, chain in the middle, post-adjust at end.
    assert "x = a + b + 0.3 (printer overshoot) = 5.3" in out


def test_derived_name_with_subtraction_renders_minus():
    class C(Component):
        equations = """
            x = 5.0
            x -= 0.25  # cal
        """

        def build(self):
            return cube(self.x)

    out = emit_str(C())
    assert "x = 5.0 - 0.25 (cal) = 4.75" in out


def test_multiplicative_chain_renders_with_original_op():
    class C(Component):
        equations = """
            x = 10.0
            x *= 1.05  # slop
            x /= 2.0   # halve
        """

        def build(self):
            return cube(self.x)

    out = emit_str(C())
    # /= renders as `/ divisor`, NOT as `* (1/divisor)`. The faithful
    # rendering matches what the user wrote even though the stored
    # delta is the reciprocal.
    assert "x = 10.0 * 1.05 (slop) / 2.0 (halve) = 5.25" in out


def test_multiple_additive_adjustments_chain():
    class C(Component):
        equations = """
            x = 10.0
            x += 0.3   # first
            x += 0.2   # second
            x -= 0.1   # third
        """

        def build(self):
            return cube(self.x)

    out = emit_str(C())
    assert "x = 10.0 + 0.3 (first) + 0.2 (second) - 0.1 (third) = 10.4" in out


# =============================================================================
# Input + adjusted: ``name = pre_value <chain> = post_value  (input)``
# =============================================================================


def test_input_name_with_adjustment():
    class C(Component):
        equations = """
            x > 0
            x += 0.3  # printer overshoot
        """

        def build(self):
            return cube(self.x)

    out = emit_str(C(x=10.0))
    # Pre-adjust 10 starts the chain; post-adjust 10.3 ends it.
    assert "x = 10 + 0.3 (printer overshoot) = 10.3  (input)" in out


# =============================================================================
# Skipped adjustments don't appear
# =============================================================================


def test_skipped_adjustment_not_in_glossary():
    class C(Component):
        equations = """
            ?slop > 0     # plain optional, stays None unless supplied
            x = 10.0
            x += slop     # skips when slop is None
        """

        def build(self):
            return cube(self.x)

    # slop unsupplied: adjustment skips, so the glossary shows the
    # plain unadjusted derivation (expression on the left, post-adjust
    # value on the right — equal to pre-adjust because no adjustment
    # fired).
    out = emit_str(C())
    assert "x = 10.0 = 10" in out
    # The glossary line for x must not mention `slop` (no chain term).
    x_line = next(
        line for line in out.split("\n")
        if line.lstrip().startswith("//") and "x =" in line
    )
    assert "slop" not in x_line


# =============================================================================
# Empty comment renders without parenthetical
# =============================================================================


def test_no_comment_omits_parenthetical():
    class C(Component):
        equations = """
            x = 10.0
            x += 0.3
        """

        def build(self):
            return cube(self.x)

    out = emit_str(C())
    # No comment → no `( ... )` after the term.
    assert "x = 10.0 + 0.3 = 10.3" in out


# =============================================================================
# Comma-broadcast: each name shows its own (identical) chain
# =============================================================================


def test_comma_broadcast_each_name_shows_chain():
    class C(Component):
        equations = """
            a = 5.0
            b = 10.0
            a, b += 0.1  # both fudge
        """

        def build(self):
            return cube([self.a, self.b, 1])

    out = emit_str(C())
    assert "a = 5.0 + 0.1 (both fudge) = 5.1" in out
    assert "b = 10.0 + 0.1 (both fudge) = 10.1" in out


# =============================================================================
# Unadjusted Component still renders as before (regression guard)
# =============================================================================


def test_unadjusted_component_unchanged():
    class C(Component):
        equations = """
            a = 4.0
            b = 1.0
            x = a + b
        """

        def build(self):
            return cube(self.x)

    out = emit_str(C())
    assert "x = a + b = 5" in out
    # No chain artifacts for an unadjusted derivation.
    assert "+ 0" not in out.split("x =")[1].split("\n")[0]
