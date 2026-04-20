"""Animation: $t SymbolicExpr in transforms and primitive sizes,
viewpoint() context manager, cond() ternary."""

import pytest

from scadwright import emit_str
from scadwright.animation import (
    SymbolicExpr, t, cond, viewpoint, current_viewpoint, Viewpoint,
)
from scadwright.primitives import cube, sphere, cylinder


# ---------- SymbolicExpr arithmetic + emission ----------


def test_t_emits_as_dollar_t():
    assert t().emit() == "$t"


def test_arithmetic_builds_scad_expressions():
    assert (t() * 360).emit() == "$t * 360"
    assert (t() + 1).emit() == "$t + 1"
    assert (t() - 0.5).emit() == "$t - 0.5"
    assert (t() / 2).emit() == "$t / 2"
    assert (-t()).emit() == "-$t"
    assert (1 - t()).emit() == "1 - $t"
    assert (2 * t() + 1).emit() == "2 * $t + 1"


def test_precedence_parenthesizes_when_needed():
    # mul binds tighter than add, so (t+1)*2 needs parens
    assert ((t() + 1) * 2).emit() == "($t + 1) * 2"
    # but t*2+1 doesn't need parens around t*2
    assert (t() * 2 + 1).emit() == "$t * 2 + 1"


def test_pow_emits_as_pow_func():
    assert (t() ** 2).emit() == "pow($t, 2)"


# ---------- Phase 1: transforms accept SymbolicExpr ----------


def test_translate_accepts_symbolic_in_vector():
    out = emit_str(cube(5).translate([t() * 50, 0, 0]))
    assert "translate([$t * 50, 0, 0])" in out


def test_translate_kwargs_accept_symbolic():
    out = emit_str(cube(1).translate(z=t() * 10))
    assert "translate([0, 0, $t * 10])" in out


def test_rotate_euler_accepts_symbolic():
    out = emit_str(cube(5).rotate([0, 0, t() * 360]))
    assert "rotate([0, 0, $t * 360])" in out


def test_rotate_axis_angle_accepts_symbolic_angle():
    out = emit_str(cube(5).rotate(a=t() * 90, v=[0, 0, 1]))
    assert "a=$t * 90" in out


def test_scale_accepts_symbolic():
    out = emit_str(cube(5).scale([1 + t(), 1, 1]))
    assert "scale([1 + $t, 1, 1])" in out


def test_mirror_accepts_symbolic():
    out = emit_str(cube(5).mirror([t(), 0, 1]))
    assert "mirror([$t, 0, 1])" in out


# ---------- Phase 2: primitive sizes accept SymbolicExpr ----------


def test_cube_accepts_symbolic_size():
    out = emit_str(cube([t() * 10 + 5, 5, 5]))
    assert "cube([$t * 10 + 5, 5, 5]" in out


def test_sphere_accepts_symbolic_radius():
    out = emit_str(sphere(r=t() * 20 + 1, fn=24))
    assert "sphere(r=$t * 20 + 1" in out


def test_cylinder_accepts_symbolic_height():
    out = emit_str(cylinder(h=t() * 30, r=5, fn=16))
    assert "cylinder(h=$t * 30" in out


def test_cylinder_accepts_symbolic_diameter():
    out = emit_str(cylinder(h=10, d=t() * 4 + 2, fn=16))
    # d=X gets resolved to r=X/2 internally
    assert "($t * 4 + 2) / 2" in out or "$t * 4 + 2" in out


# ---------- cond() ternary ----------


def test_cond_emits_ternary():
    expr = cond(t() < 0.5, 1.0, 2.0)
    assert expr.emit() == "$t < 0.5 ? 1 : 2"


def test_cond_with_complex_branches():
    # Ping-pong: 0..0.5 → 0..1, 0.5..1 → 1..0
    expr = cond(t() < 0.5, 2 * t(), 2 - 2 * t())
    assert expr.emit() == "$t < 0.5 ? 2 * $t : 2 - 2 * $t"


def test_using_symbolicexpr_as_python_bool_raises():
    """Comparison ops return deferred expressions, not bools. Misuse should
    be loud."""
    with pytest.raises(TypeError, match="not a Python bool"):
        if t() < 0.5:  # noqa: this is intentional
            pass


# ---------- Viewpoint ----------


def test_viewpoint_writes_dollar_vp_assignments():
    with viewpoint(rotation=[60, 0, 30], distance=200):
        out = emit_str(cube(1))
    assert "$vpr = [60, 0, 30];" in out
    assert "$vpd = 200;" in out


def test_viewpoint_omits_unset_fields():
    with viewpoint(distance=150):
        out = emit_str(cube(1))
    assert "$vpd = 150;" in out
    assert "$vpr" not in out
    assert "$vpt" not in out
    assert "$vpf" not in out


def test_viewpoint_accepts_symbolic_for_turntable():
    with viewpoint(rotation=[60, 0, t() * 360], distance=200):
        out = emit_str(cube(1))
    assert "$vpr = [60, 0, $t * 360];" in out


def test_viewpoint_outside_block_emits_no_assignments():
    out = emit_str(cube(1))
    assert "$vp" not in out


def test_nested_viewpoints_merge():
    with viewpoint(rotation=[10, 20, 30], distance=100):
        with viewpoint(distance=200):
            assert current_viewpoint() == Viewpoint(
                rotation=[10, 20, 30], target=None, distance=200, fov=None,
            )


# ---------- Negative validation still works on real numbers ----------


def test_cube_still_rejects_negative_real_size():
    from scadwright.errors import ValidationError
    with pytest.raises(ValidationError, match="non-negative"):
        cube([-5, 1, 1])


def test_sphere_still_rejects_negative_real_radius():
    from scadwright.errors import ValidationError
    with pytest.raises(ValidationError, match="positive"):
        sphere(r=-1)
