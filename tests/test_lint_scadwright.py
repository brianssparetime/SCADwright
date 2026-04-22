"""Tests for the style-guide linter."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import lint_scadwright as lint  # noqa: E402


def _violations(source: str, check):
    tree = ast.parse(source)
    return check(Path("<test>"), tree)


# =============================================================================
# no-module-eps
# =============================================================================


def test_module_eps_flagged():
    v = _violations("EPS = 0.01\n", lint.check_module_level_eps)
    assert len(v) == 1
    assert v[0].rule == "no-module-eps"


def test_local_eps_not_flagged():
    src = """
def build(self):
    EPS = 0.01
    return EPS
"""
    assert _violations(src, lint.check_module_level_eps) == []


def test_other_module_constant_not_flagged():
    v = _violations("FOO = 0.01\n", lint.check_module_level_eps)
    assert v == []


# =============================================================================
# no-param-float
# =============================================================================


def test_bare_param_float_flagged():
    src = """
class C:
    x = Param(float)
"""
    v = _violations(src, lint.check_param_float)
    assert len(v) == 1
    assert v[0].rule == "no-param-float"


def test_param_float_with_default_none_allowed():
    src = """
class C:
    x = Param(float, default=None)
"""
    assert _violations(src, lint.check_param_float) == []


def test_param_float_with_numeric_default_allowed():
    # Engineering defaults (e.g., pressure_angle=20.0) are allowed per the
    # current style-guide reading; opt-out is the `default=None` case that
    # the linter knows about. Any `default=` present is considered
    # intentional and not flagged.
    src = """
class C:
    angle = Param(float, default=20.0)
"""
    assert _violations(src, lint.check_param_float) == []


def test_param_int_not_flagged():
    src = """
class C:
    count = Param(int, positive=True)
"""
    assert _violations(src, lint.check_param_float) == []


def test_param_of_namedtuple_not_flagged():
    src = """
class C:
    spec = Param(BatterySpec)
"""
    assert _violations(src, lint.check_param_float) == []


# =============================================================================
# translate-single-axis
# =============================================================================


def test_translate_x_flagged():
    v = _violations("part.translate([5, 0, 0])\n", lint.check_translate_single_axis)
    assert len(v) == 1
    assert "right/left" in v[0].message


def test_translate_y_flagged():
    v = _violations("part.translate([0, 5, 0])\n", lint.check_translate_single_axis)
    assert len(v) == 1
    assert "back/forward" in v[0].message


def test_translate_z_flagged():
    v = _violations("part.translate([0, 0, 5])\n", lint.check_translate_single_axis)
    assert len(v) == 1
    assert "up/down" in v[0].message


def test_translate_expression_on_single_axis_flagged():
    v = _violations(
        "part.translate([0, (i - 1) * pitch, 0])\n",
        lint.check_translate_single_axis,
    )
    assert len(v) == 1


def test_translate_multi_axis_not_flagged():
    src = """
part.translate([x, y, 0])
part.translate([1, 2, 3])
"""
    assert _violations(src, lint.check_translate_single_axis) == []


def test_translate_negative_zero_flagged():
    v = _violations("part.translate([-0.0, y, 0])\n", lint.check_translate_single_axis)
    assert len(v) == 1


def test_translate_with_tuple_arg_flagged():
    v = _violations("part.translate((0, y, 0))\n", lint.check_translate_single_axis)
    assert len(v) == 1


# =============================================================================
# Integration: the repo should lint clean.
# =============================================================================


def test_repo_lints_clean():
    """Regression guard: the checked-in code has no linter violations.

    If this fails, either (a) fix the new violation, or (b) if the rule
    itself is wrong for a legitimate case, discuss before loosening it.
    """
    file_count, violations = lint.run(lint.DEFAULT_PATHS)
    assert violations == [], (
        "Style-guide linter caught "
        f"{len(violations)} violation(s) in {file_count} file(s):\n"
        + "\n".join(v.format() for v in violations)
    )
