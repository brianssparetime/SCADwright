"""Public introspection API for adjustment provenance.

``component.adjustments_for(name)`` returns the ordered list of
:class:`Adjustment` records for a name; ``component.all_adjustments()``
returns the full ``{name: [...]}`` map. Skipped adjustments do not
appear in either result.
"""

from __future__ import annotations

import pytest

from scadwright import Adjustment, Component, Param
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# =============================================================================
# Adjustment namedtuple is exported and well-shaped
# =============================================================================


def test_adjustment_is_namedtuple():
    a = Adjustment(line=2, delta=0.3, comment="overshoot")
    assert a.line == 2
    assert a.delta == 0.3
    assert a.comment == "overshoot"
    # Namedtuple positional access works.
    assert a[0] == 2
    assert a[1] == 0.3
    assert a[2] == "overshoot"


# =============================================================================
# adjustments_for: line, delta, comment
# =============================================================================


def test_simple_additive_provenance():
    class C(Component):
        equations = """
            x = 10.0
            x += 0.3   # overshoot
        """

        def build(self):
            return cube(self.x)

    c = C()
    adjs = c.adjustments_for("x")
    assert len(adjs) == 1
    # 1-indexed across logical lines: `x = 10.0` is line 1,
    # `x += 0.3 # overshoot` is line 2. Blank lines and whole-line
    # comments don't increment the index.
    assert adjs[0].line == 2
    assert adjs[0].delta == pytest.approx(0.3)
    assert adjs[0].comment == "overshoot"


def test_subtraction_stored_as_negative_delta():
    class C(Component):
        equations = """
            x = 10.0
            x -= 0.25  # calibration
        """

        def build(self):
            return cube(self.x)

    adjs = C().adjustments_for("x")
    assert adjs[0].delta == pytest.approx(-0.25)


def test_multiplicative_stored_as_factor():
    class C(Component):
        equations = """
            x = 10.0
            x *= 1.05  # slop
        """

        def build(self):
            return cube(self.x)

    adjs = C().adjustments_for("x")
    assert adjs[0].delta == pytest.approx(1.05)


def test_division_stored_as_reciprocal():
    """``x /= 2.0`` stores delta = 1/2.0 = 0.5 so the chain of factors
    composes as multiplication regardless of the operator written."""

    class C(Component):
        equations = """
            x = 10.0
            x /= 2.0  # halve
        """

        def build(self):
            return cube(self.x)

    adjs = C().adjustments_for("x")
    assert adjs[0].delta == pytest.approx(0.5)


def test_multiple_adjustments_in_source_order():
    class C(Component):
        equations = """
            x = 10.0
            x += 0.3   # first
            x += 0.2   # second
            x -= 0.1   # third
        """

        def build(self):
            return cube(self.x)

    adjs = C().adjustments_for("x")
    assert len(adjs) == 3
    assert [a.delta for a in adjs] == pytest.approx([0.3, 0.2, -0.1])
    assert [a.comment for a in adjs] == ["first", "second", "third"]
    # Lines preserve declaration order.
    assert adjs[0].line < adjs[1].line < adjs[2].line


def test_empty_comment_when_none_present():
    class C(Component):
        equations = """
            x = 10.0
            x += 0.3
        """

        def build(self):
            return cube(self.x)

    adjs = C().adjustments_for("x")
    assert adjs[0].comment == ""


def test_preceding_comment_captured():
    class C(Component):
        equations = """
            x = 10.0
            # printer overshoot, X-axis
            x += 0.3
        """

        def build(self):
            return cube(self.x)

    adjs = C().adjustments_for("x")
    assert adjs[0].comment == "printer overshoot, X-axis"


# =============================================================================
# Empty list for unadjusted name
# =============================================================================


def test_unadjusted_name_returns_empty_list():
    class C(Component):
        x = Param(float, default=10.0)
        equations = """
            y = 5.0
            y += 0.3  # only y is adjusted
        """

        def build(self):
            return cube([self.x, self.y, 1])

    c = C()
    assert c.adjustments_for("x") == []


# =============================================================================
# Unknown name raises
# =============================================================================


def test_unknown_name_raises():
    class C(Component):
        equations = """
            x = 10.0
            x += 0.3
        """

        def build(self):
            return cube(self.x)

    with pytest.raises(ValidationError, match="unknown name"):
        C().adjustments_for("ghost")


# =============================================================================
# Skipped adjustments not recorded
# =============================================================================


def test_skipped_adjustment_not_in_provenance():
    class C(Component):
        equations = """
            ?slop > 0    # plain optional, stays None unless supplied
            x = 10.0
            x += slop    # skips when slop is None
        """

        def build(self):
            return cube(self.x)

    # slop unsupplied: adjustment skips silently.
    assert C().adjustments_for("x") == []
    # Supply slop: adjustment fires and is recorded.
    adjs = C(slop=0.05).adjustments_for("x")
    assert len(adjs) == 1
    assert adjs[0].delta == pytest.approx(0.05)


# =============================================================================
# all_adjustments
# =============================================================================


def test_all_adjustments_returns_full_map():
    class C(Component):
        equations = """
            x = 10.0
            y = 20.0
            x += 0.1   # x fudge
            y *= 1.05  # y scale
        """

        def build(self):
            return cube([self.x, self.y, 1])

    all_adjs = C().all_adjustments()
    assert set(all_adjs.keys()) == {"x", "y"}
    assert all_adjs["x"][0].delta == pytest.approx(0.1)
    assert all_adjs["y"][0].delta == pytest.approx(1.05)


def test_all_adjustments_excludes_unadjusted_names():
    class C(Component):
        equations = """
            x = 10.0
            y = 20.0
            x += 0.1
        """

        def build(self):
            return cube([self.x, self.y, 1])

    assert set(C().all_adjustments().keys()) == {"x"}


def test_all_adjustments_empty_for_no_adjustments():
    class C(Component):
        equations = """
            x = 10.0
        """

        def build(self):
            return cube(self.x)

    assert C().all_adjustments() == {}


# =============================================================================
# Independence across instances
# =============================================================================


def test_provenance_independent_across_instances():
    class C(Component):
        equations = """
            ?slop > 0
            x = 10.0
            x += slop
        """

        def build(self):
            return cube(self.x)

    a = C()  # adjustment skipped
    b = C(slop=0.05)  # adjustment fired
    assert a.adjustments_for("x") == []
    assert len(b.adjustments_for("x")) == 1


# =============================================================================
# Comma-broadcast: each broadcast sibling gets its own provenance entry
# =============================================================================


def test_comma_broadcast_each_name_has_own_entry():
    class C(Component):
        equations = """
            a = 10.0
            b = 20.0
            a, b += 0.1   # both fudge
        """

        def build(self):
            return cube([self.a, self.b, 1])

    c = C()
    a_adjs = c.adjustments_for("a")
    b_adjs = c.adjustments_for("b")
    assert len(a_adjs) == 1
    assert len(b_adjs) == 1
    # Both share the same source line and comment.
    assert a_adjs[0].line == b_adjs[0].line
    assert a_adjs[0].comment == b_adjs[0].comment == "both fudge"


# =============================================================================
# Returned list is a copy (caller can mutate without affecting state)
# =============================================================================


def test_returned_list_is_copy():
    class C(Component):
        equations = """
            x = 10.0
            x += 0.3
        """

        def build(self):
            return cube(self.x)

    c = C()
    adjs = c.adjustments_for("x")
    adjs.clear()
    # Internal state untouched.
    assert len(c.adjustments_for("x")) == 1
