"""The ``Spec`` class — frozen, equation-resolved value bag for
cross-file shared dimensions.

Two access modes:

- Fixed (no ``?param``): resolves at class-define time; values become
  class attributes; class is frozen.
- Parameterized (any ``?param``): class-attr access errors with an
  "instantiate this Spec" hint; instances resolve per construction
  and are frozen.
"""

from __future__ import annotations

import pytest

from scadwright import Component, Spec
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# =============================================================================
# Fixed Spec: class-time resolution
# =============================================================================


def test_fixed_spec_resolves_at_class_define_time():
    class S(Spec):
        equations = """
            cam_barrel_od = 60.5
            max_lug_proj = 1.8
            mount_wall_thk = 2.0
            lens_mount_od = cam_barrel_od + 2*max_lug_proj + 2*mount_wall_thk
        """

    # No instance needed — resolved values are class attributes.
    assert S.cam_barrel_od == pytest.approx(60.5)
    assert S.max_lug_proj == pytest.approx(1.8)
    assert S.mount_wall_thk == pytest.approx(2.0)
    assert S.lens_mount_od == pytest.approx(60.5 + 3.6 + 4.0)


def test_fixed_spec_class_attr_reassignment_raises():
    class S(Spec):
        equations = """
            x = 5.0
            y = x * 2
        """

    with pytest.raises(ValidationError, match="frozen"):
        S.x = 99


def test_fixed_spec_with_adjustments():
    class S(Spec):
        equations = """
            cam_barrel_od = 60.5
            cam_barrel_od += 0.3   # printer overshoot
            cam_barrel_od += 0.05  # extra slop
        """

    assert S.cam_barrel_od == pytest.approx(60.85)


def test_fixed_spec_adjustments_introspection_class_level():
    """Fixed Specs expose ``adjustments_for`` and ``all_adjustments``
    directly on the class — no instance needed."""

    class S(Spec):
        equations = """
            x = 10.0
            x += 0.3   # overshoot
            y = 5.0
        """

    adjs = S.adjustments_for("x")
    assert len(adjs) == 1
    assert adjs[0].comment == "overshoot"
    assert adjs[0].delta == pytest.approx(0.3)

    # Unadjusted name returns empty list.
    assert S.adjustments_for("y") == []

    # Unknown name raises.
    with pytest.raises(ValidationError, match="unknown name"):
        S.adjustments_for("ghost")

    # all_adjustments returns the full map.
    all_adjs = S.all_adjustments()
    assert set(all_adjs.keys()) == {"x"}


def test_fixed_spec_no_adjustments_class_level():
    """Fixed Spec with no adjustments at all returns empty introspection
    via the class form."""

    class S(Spec):
        equations = """
            x = 5.0
            y = x * 2
        """

    assert S.adjustments_for("x") == []
    assert S.adjustments_for("y") == []
    assert S.all_adjustments() == {}


def test_parameterized_spec_class_level_introspection_errors():
    """Parameterized Specs reject class-level introspection — the
    user has to instantiate first because provenance is per-instance."""

    class S(Spec):
        equations = """
            ?scale > 0
            x = 10.0 * scale
            x += 0.3  # overshoot
        """

    with pytest.raises(ValidationError, match="call on an instance"):
        S.adjustments_for("x")
    with pytest.raises(ValidationError, match="call on an instance"):
        S.all_adjustments()


def test_fixed_spec_with_constraints_pre_adjust():
    """Rules see pre-adjust values by default — same semantic as
    Components."""

    class S(Spec):
        equations = """
            x = 5.5
            x > 5     # holds against pre-adjust 5.5
            x -= 1.0  # post-adjust = 4.5; rule already passed
        """

    assert S.x == pytest.approx(4.5)


def test_fixed_spec_with_adjusted_marker():
    class S(Spec):
        equations = """
            x = 4.0
            x += 1.5  # post-adjust = 5.5
            adjusted(x) > 5
        """

    assert S.x == pytest.approx(5.5)


def test_fixed_spec_constraint_violation_raises_at_class_define():
    """A constraint violation in a fixed Spec surfaces immediately at
    class-define time, not at first attribute access."""

    with pytest.raises(ValidationError):
        class S(Spec):
            equations = """
                x = 4.0
                x > 5
            """


# =============================================================================
# Parameterized Spec: instance form
# =============================================================================


def test_parameterized_spec_class_attr_access_errors():
    class S(Spec):
        equations = """
            ?profile_scale > 0
            x = 10.0 * profile_scale
        """

    with pytest.raises(AttributeError, match="this Spec has parameters"):
        _ = S.x


def test_parameterized_spec_instance_resolves():
    class S(Spec):
        equations = """
            ?scale > 0
            x = 10.0 * scale
        """

    s = S(scale=1.05)
    assert s.x == pytest.approx(10.5)


def test_parameterized_spec_instance_frozen():
    class S(Spec):
        equations = """
            ?scale > 0
            x = 10.0 * scale
        """

    s = S(scale=1.05)
    with pytest.raises(ValidationError, match="frozen"):
        s.x = 99


def test_parameterized_spec_with_adjustments():
    class S(Spec):
        equations = """
            ?scale > 0
            x = 10.0 * scale
            x += 0.3   # printer overshoot
        """

    s = S(scale=1.0)
    assert s.x == pytest.approx(10.3)


def test_parameterized_spec_introspection_per_instance():
    class S(Spec):
        equations = """
            ?scale > 0
            x = 10.0 * scale
            x += 0.3   # overshoot
        """

    s = S(scale=1.0)
    adjs = s.adjustments_for("x")
    assert len(adjs) == 1
    assert adjs[0].comment == "overshoot"

    # Empty list for a name with no adjustments.
    assert s.adjustments_for("scale") == []

    # Unknown name raises.
    with pytest.raises(ValidationError, match="unknown name"):
        s.adjustments_for("ghost")


def test_parameterized_spec_unknown_kwarg_rejected():
    class S(Spec):
        equations = """
            ?scale > 0
            x = 10.0 * scale
        """

    with pytest.raises(ValidationError, match="unknown parameter"):
        S(scale=1.0, ghost=2.0)


# =============================================================================
# Cross-reference: a Component reads from a Spec class attr
# =============================================================================


def test_component_reads_from_fixed_spec():
    """The whole point of a Spec is being a single source of truth for
    cross-file dimensions. A Component reads the class attribute and
    uses it like any other value."""

    class S(Spec):
        equations = """
            mount_od = 60.5
            mount_id = mount_od - 4.0
        """

    class C(Component):
        equations = """
            ring_od > 0
            ring_id > 0
            ring_od < ring_id + 10
        """

        def build(self):
            return cube([self.ring_od, self.ring_od, 1])

    # Read from S at instantiation time.
    c = C(ring_od=S.mount_od, ring_id=S.mount_id)
    assert c.ring_od == pytest.approx(60.5)
    assert c.ring_id == pytest.approx(56.5)


# =============================================================================
# Empty Spec edge case
# =============================================================================


def test_empty_spec_is_fine():
    """A Spec with no equations is degenerate but allowed — useful for
    namespaces or as a base class."""

    class S(Spec):
        pass

    # Class attrs untouched, no resolved values, no errors.
    assert hasattr(S, "_unified_equations")
