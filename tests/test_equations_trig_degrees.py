"""Trig inside `equations` takes and returns degrees.

Matches `scadwright.math` (`scmath`) and SCAD. Forward calls
(`sin`, `cos`, `tan`) accept degrees; inverse calls (`asin`,
`acos`, `atan`, `atan2`) return degrees. The wrappers live in
`_CURATED_MATH` for numeric eval and in `_ensure_algebraic_functions`
for sympy substitution / solving.
"""

from __future__ import annotations

import pytest

from scadwright import Component
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# =============================================================================
# Forward trig: degrees in
# =============================================================================


class _SinForward(Component):
    equations = """
        a = sin(theta)
    """

    def build(self):
        return cube(1)


@pytest.mark.parametrize(
    "theta, expected",
    [(0, 0.0), (30, 0.5), (90, 1.0), (180, 0.0)],
)
def test_sin_takes_degrees(theta, expected):
    p = _SinForward(theta=theta)
    assert p.a == pytest.approx(expected, abs=1e-9)


class _CosForward(Component):
    equations = """
        a = cos(theta)
    """

    def build(self):
        return cube(1)


@pytest.mark.parametrize(
    "theta, expected",
    [(0, 1.0), (60, 0.5), (90, 0.0)],
)
def test_cos_takes_degrees(theta, expected):
    p = _CosForward(theta=theta)
    assert p.a == pytest.approx(expected, abs=1e-9)


class _TanForward(Component):
    equations = """
        a = tan(theta)
    """

    def build(self):
        return cube(1)


def test_tan_takes_degrees():
    p = _TanForward(theta=45)
    assert p.a == pytest.approx(1.0, abs=1e-9)


# =============================================================================
# Inverse trig: degrees out
# =============================================================================


class _AsinInverse(Component):
    equations = """
        theta = asin(x)
    """

    def build(self):
        return cube(1)


@pytest.mark.parametrize(
    "x, expected",
    [(0.5, 30.0), (1.0, 90.0)],
)
def test_asin_returns_degrees(x, expected):
    p = _AsinInverse(x=x)
    assert p.theta == pytest.approx(expected, abs=1e-9)


class _AcosInverse(Component):
    equations = """
        theta = acos(x)
    """

    def build(self):
        return cube(1)


@pytest.mark.parametrize(
    "x, expected",
    [(1.0, 0.0), (0.0, 90.0)],
)
def test_acos_returns_degrees(x, expected):
    p = _AcosInverse(x=x)
    assert p.theta == pytest.approx(expected, abs=1e-9)


class _AtanInverse(Component):
    equations = """
        theta = atan(x)
    """

    def build(self):
        return cube(1)


def test_atan_returns_degrees():
    p = _AtanInverse(x=1.0)
    assert p.theta == pytest.approx(45.0, abs=1e-9)


class _Atan2(Component):
    equations = """
        theta = atan2(y, x)
    """

    def build(self):
        return cube(1)


@pytest.mark.parametrize(
    "y, x, expected",
    [(1, 1, 45.0), (1, 0, 90.0)],
)
def test_atan2_returns_degrees(y, x, expected):
    p = _Atan2(y=y, x=x)
    assert p.theta == pytest.approx(expected, abs=1e-9)


# =============================================================================
# Sympy back-solve through wrapped sin
# =============================================================================


class _SympySolveSin(Component):
    # Two solutions for `theta`: 30° and 150°. The cross-equation
    # constraint `theta < 90` rules out the 150 candidate.
    equations = """
        sin(theta) = 0.5
        theta < 90
        theta > 0
    """

    def build(self):
        return cube(1)


def test_sympy_solve_returns_degrees():
    p = _SympySolveSin()
    assert p.theta == pytest.approx(30.0, abs=1e-9)


# =============================================================================
# Pythagorean identity round-trip — guards against forward/inverse desync
# =============================================================================


class _Pythag(Component):
    equations = """
        # If sin/cos disagree on units, this diverges from 1.
        identity = sin(theta) ** 2 + cos(theta) ** 2
    """

    def build(self):
        return cube(1)


@pytest.mark.parametrize("theta", [0, 17, 45, 89, 180, -30])
def test_pythagorean_identity(theta):
    p = _Pythag(theta=theta)
    assert p.identity == pytest.approx(1.0, abs=1e-9)


# =============================================================================
# Explicit conversion helpers
# =============================================================================


class _Radians(Component):
    equations = """
        rad = radians(deg)
    """

    def build(self):
        return cube(1)


def test_radians_helper_in_dsl():
    import math as _m
    p = _Radians(deg=180)
    assert p.rad == pytest.approx(_m.pi, abs=1e-12)


class _Degrees(Component):
    equations = """
        deg = degrees(rad)
    """

    def build(self):
        return cube(1)


def test_degrees_helper_in_dsl():
    import math as _m
    p = _Degrees(rad=_m.pi)
    assert p.deg == pytest.approx(180.0, abs=1e-9)


# =============================================================================
# Sympy multi-branch with degree-bounded constraint (matches v-block pattern)
# =============================================================================


class _MultiBranchDegrees(Component):
    # The classic V-block-style equation. `half_angle` has two sympy
    # candidates (52.7° and 127.3°); the cross-equation `angle < 180`
    # keeps only the first via `angle = 2 * half_angle`.
    equations = """
        max_d = 2 * groove_depth * sin(half_angle)
        angle = 2 * half_angle
        max_d, groove_depth, angle, half_angle > 0
        angle < 180
    """

    def build(self):
        return cube(1)


def test_multi_branch_disambiguated_in_degrees():
    p = _MultiBranchDegrees(max_d=35, groove_depth=22)
    assert p.half_angle == pytest.approx(52.6982097, rel=1e-5)
    assert p.angle == pytest.approx(105.396419, rel=1e-5)


# =============================================================================
# Bools rejected as trig arguments — cross-check the existing typed-name guard
# still fires when the wrapped trig sits in `_NUMERIC_YIELDING_CALLS`.
# =============================================================================


def test_bool_in_sin_rejected_at_classdef():
    with pytest.raises(ValidationError, match=r"bool-tagged"):
        class _Bad(Component):
            equations = """
                x = sin(?direction:bool)
            """

            def build(self):
                return cube(1)
