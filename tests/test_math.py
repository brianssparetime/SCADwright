from scadwright import math as scmath
import pytest


def test_sin_degrees():
    assert scmath.sin(0) == pytest.approx(0.0)
    assert scmath.sin(90) == pytest.approx(1.0)
    assert scmath.sin(180) == pytest.approx(0.0, abs=1e-10)


def test_cos_degrees():
    assert scmath.cos(0) == pytest.approx(1.0)
    assert scmath.cos(90) == pytest.approx(0.0, abs=1e-10)


def test_atan2_degrees():
    assert scmath.atan2(1, 1) == pytest.approx(45.0)
    assert scmath.atan2(1, 0) == pytest.approx(90.0)


def test_acos_returns_degrees():
    assert scmath.acos(0) == pytest.approx(90.0)


def test_sum_basic():
    assert scmath.sum([1, 2, 3]) == 6.0


def test_min_max_variadic():
    assert scmath.min(3, 1, 2) == 1
    assert scmath.max(3, 1, 2) == 3


def test_min_max_iterable():
    assert scmath.min([3, 1, 2]) == 1
    assert scmath.max([3, 1, 2]) == 3


def test_abs_sign():
    assert scmath.abs(-5) == 5
    assert scmath.sign(-3) == -1
    assert scmath.sign(0) == 0
    assert scmath.sign(7) == 1


def test_floor_ceil():
    assert scmath.floor(2.7) == 2
    assert scmath.ceil(2.1) == 3


def test_round_half_away_from_zero():
    """SCAD rounds 2.5 to 3 (half-away). Python's round() does banker's (2.5 -> 2)."""
    assert scmath.round(2.5) == 3
    assert scmath.round(-2.5) == -3
    assert scmath.round(2.4) == 2


def test_pow_sqrt():
    assert scmath.pow(2, 10) == 1024
    assert scmath.sqrt(16) == 4


def test_log_default_base_10():
    assert scmath.log(100) == pytest.approx(2.0)


def test_ln():
    import math as stdmath

    assert scmath.ln(stdmath.e) == pytest.approx(1.0)


def test_norm_2d():
    assert scmath.norm([3, 4]) == pytest.approx(5.0)


def test_norm_3d():
    assert scmath.norm([1, 2, 2]) == pytest.approx(3.0)


def test_cross_unit_vectors():
    assert scmath.cross([1, 0, 0], [0, 1, 0]) == (0.0, 0.0, 1.0)
    assert scmath.cross([0, 1, 0], [0, 0, 1]) == (1.0, 0.0, 0.0)


def test_cross_dimension_check():
    from scadwright.errors import ValidationError
    with pytest.raises(ValidationError):
        scmath.cross([1, 0], [0, 1])
