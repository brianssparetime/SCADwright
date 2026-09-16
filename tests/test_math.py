from scadwright import emit_str, math as scmath
from scadwright.animation import t
from scadwright.primitives import cube
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


# ---------- symbolic arguments emit SCAD calls ----------


@pytest.mark.parametrize("name", [
    "sin", "cos", "tan", "asin", "acos", "atan",
    "sqrt", "exp", "abs", "sign", "floor", "ceil", "round",
])
def test_unary_functions_emit_same_named_scad_call(name):
    assert getattr(scmath, name)(t() * 2).emit() == f"{name}($t * 2)"


def test_two_argument_functions_emit_scad_call():
    assert scmath.atan2(t(), 1).emit() == "atan2($t, 1)"
    assert scmath.pow(2, t()).emit() == "pow(2, $t)"


def test_ln_and_log_emit_scad_call():
    assert scmath.ln(t()).emit() == "ln($t)"
    assert scmath.log(t()).emit() == "log($t)"


def test_log_with_other_base_emits_ratio_of_ln():
    # SCAD's log() is base 10 only.
    assert scmath.log(t(), base=2).emit() == "ln($t) / ln(2)"
    assert scmath.log(8, base=t()).emit() == "ln(8) / ln($t)"


def test_min_max_emit_scad_call_in_either_form():
    assert scmath.min(t(), 0.5).emit() == "min($t, 0.5)"
    assert scmath.max([t(), 0.2, 1]).emit() == "max($t, 0.2, 1)"


def test_sum_with_symbolic_values():
    assert scmath.sum([t(), 1]).emit() == "$t + 1"
    assert scmath.sum([t()], start=1).emit() == "1 + $t"


def test_norm_with_symbolic_component():
    assert scmath.norm([t(), 1]).emit() == "sqrt($t * $t + 1)"


def test_cross_with_symbolic_component():
    x, y, z = scmath.cross([t(), 0, 0], [0, 1, 0])
    assert z.emit() == "$t * 1 - 0"


def test_symbolic_result_composes_into_transform():
    out = emit_str(cube(1).translate([scmath.sin(t() * 360) * 20, 0, 0]))
    assert "translate([sin($t * 360) * 20, 0, 0])" in out


def test_python_math_on_symbolic_points_to_scadwright_math():
    import math
    with pytest.raises(TypeError, match="scadwright.math"):
        math.sin(t())
