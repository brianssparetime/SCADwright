"""Tests for the centralized tolerances module and the ``tolerances()``
context-manager override.
"""

import pytest

from scadwright import (
    coincidence_tol,
    default_eps,
    tolerances,
)
from scadwright.boolops import difference, fuse
from scadwright.primitives import cube, cylinder


# --- Default user-tunable values ---


def test_default_eps_default():
    assert default_eps() == 0.01


def test_default_coincidence_tol_default():
    assert coincidence_tol() == 1e-4


# --- Context manager basics ---


def test_tolerances_overrides_eps():
    assert default_eps() == 0.01
    with tolerances(eps=0.001):
        assert default_eps() == 0.001
    assert default_eps() == 0.01


def test_tolerances_overrides_coincidence():
    assert coincidence_tol() == 1e-4
    with tolerances(coincidence=1e-5):
        assert coincidence_tol() == 1e-5
    assert coincidence_tol() == 1e-4


def test_tolerances_overrides_both():
    with tolerances(eps=0.005, coincidence=5e-4):
        assert default_eps() == 0.005
        assert coincidence_tol() == 5e-4
    assert default_eps() == 0.01
    assert coincidence_tol() == 1e-4


def test_tolerances_no_kwargs_is_no_op():
    """Calling tolerances() with no overrides should leave defaults."""
    with tolerances():
        assert default_eps() == 0.01
        assert coincidence_tol() == 1e-4


def test_tolerances_nested_compose():
    with tolerances(eps=0.005):
        assert default_eps() == 0.005
        with tolerances(eps=0.001):
            assert default_eps() == 0.001
        # Outer scope restored.
        assert default_eps() == 0.005
    assert default_eps() == 0.01


def test_tolerances_partial_nesting():
    """Inner only sets one var; the other inherits from outer."""
    with tolerances(eps=0.005, coincidence=5e-5):
        assert default_eps() == 0.005
        assert coincidence_tol() == 5e-5
        with tolerances(eps=0.001):
            assert default_eps() == 0.001
            # coincidence inherited from outer
            assert coincidence_tol() == 5e-5
        assert default_eps() == 0.005
        assert coincidence_tol() == 5e-5


def test_tolerances_exit_on_exception_restores():
    try:
        with tolerances(eps=0.001):
            assert default_eps() == 0.001
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    # Restored after exception.
    assert default_eps() == 0.01


# --- Integration: attach/fuse/through pick up the override ---


def test_attach_fuse_uses_overridden_eps():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    # Default eps=0.01: bond="shift" produces a translate of (8, 8, 1.99).
    placed_default = peg.attach(plate, bond="shift")
    assert placed_default.v[2] == pytest.approx(2.0 - 0.01)

    with tolerances(eps=0.001):
        placed_tight = peg.attach(plate, bond="shift")
    assert placed_tight.v[2] == pytest.approx(2.0 - 0.001)


def test_fuse_function_uses_overridden_eps():
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with tolerances(eps=0.005):
        result = fuse(peg, plate, on="top", using_anchor="bottom", bond="shift")
    # Pull out the Translate's shift to verify eps applied.
    from scadwright.ast.transforms import Translate
    placed = next(c for c in result.children if isinstance(c, Translate))
    assert placed.v[2] == pytest.approx(2.0 - 0.005)


def test_explicit_eps_overrides_context_value():
    """A per-call eps= still wins over the context-manager value."""
    plate = cube([20, 20, 2])
    peg = cube([4, 4, 5])
    with tolerances(eps=0.001):
        # Explicit eps=0.05 should win, not the context-manager 0.001.
        placed = peg.attach(plate, bond="shift", eps=0.05)
    assert placed.v[2] == pytest.approx(2.0 - 0.05)


def test_through_uses_overridden_eps():
    box = cube([20, 20, 10])
    cyl = cylinder(h=10, r=3)
    # Default eps=0.01: through extends by 0.01 on each end.
    extended_default = cyl.through(box)
    # The result should be a Translate(Scale(...)) — extract the scale.
    from scadwright.ast.transforms import Scale, Translate
    if isinstance(extended_default, Translate):
        scaled = extended_default.child
        assert isinstance(scaled, Scale)
        # Original h=10, extended to 10 + 2 * 0.01 = 10.02 along z.
        assert scaled.factor[2] == pytest.approx(10.02 / 10.0)

    with tolerances(eps=0.005):
        extended_tight = cyl.through(box)
    if isinstance(extended_tight, Translate):
        scaled = extended_tight.child
        assert scaled.factor[2] == pytest.approx(10.01 / 10.0)


# --- coincidence_tol affects through()'s face-matching ---


def test_through_coincidence_tol_default_matches():
    """A cutter offset by less than coincidence_tol from the parent's
    face is treated as coincident (extends through that face)."""
    box = cube([20, 20, 10])
    # Cylinder offset by 5e-5 from the bottom — within default 1e-4 tol.
    cyl = cylinder(h=10, r=3).up(5e-5)
    extended = cyl.through(box)
    # Should be wrapped (= face was found coincident).
    from scadwright.ast.transforms import Translate
    assert isinstance(extended, Translate)


def test_through_coincidence_tol_tightened_misses():
    """With coincidence tightened to 1e-6, the same 5e-5-offset cutter
    no longer counts as coincident with any face."""
    box = cube([20, 20, 10])
    cyl = cylinder(h=10, r=3).up(5e-5)
    with tolerances(coincidence=1e-6):
        extended = cyl.through(box)
    # No coincident face found — through is a no-op (returns self).
    assert extended is cyl
