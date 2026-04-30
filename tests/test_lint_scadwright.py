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
# no-component-setup
# =============================================================================


def test_setup_on_component_flagged():
    src = (
        "class Foo(Component):\n"
        "    def setup(self):\n"
        "        pass\n"
    )
    v = _violations(src, lint.check_component_setup)
    assert len(v) == 1
    assert v[0].rule == "no-component-setup"


def test_setup_on_qualified_component_base_flagged():
    src = (
        "class Foo(sc.Component):\n"
        "    def setup(self):\n"
        "        pass\n"
    )
    v = _violations(src, lint.check_component_setup)
    assert len(v) == 1


def test_setup_on_subclass_of_component_subclass_flagged():
    """A class inheriting from a library Component (ending in `Component`
    or any direct subclass by naming convention) is treated the same."""
    src = (
        "class BigShape(BaseComponent):\n"
        "    def setup(self):\n"
        "        pass\n"
    )
    v = _violations(src, lint.check_component_setup)
    assert len(v) == 1


def test_setup_on_non_component_class_not_flagged():
    src = (
        "class Helper:\n"
        "    def setup(self):\n"
        "        pass\n"
    )
    v = _violations(src, lint.check_component_setup)
    assert v == []


def test_component_without_setup_not_flagged():
    src = (
        "class Foo(Component):\n"
        "    equations = ['x > 0']\n"
        "    def build(self):\n"
        "        return cube(1)\n"
    )
    v = _violations(src, lint.check_component_setup)
    assert v == []


def test_component_with_non_self_setup_not_flagged():
    """A classmethod/staticmethod named setup shouldn't trip the rule —
    the signature check requires `self` as the first arg."""
    src = (
        "class Foo(Component):\n"
        "    @staticmethod\n"
        "    def setup():\n"
        "        pass\n"
    )
    v = _violations(src, lint.check_component_setup)
    assert v == []


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


# =============================================================================
# --full mode: import-time class-define-time errors
# =============================================================================


def test_file_defines_component_subclass_detection():
    src = """
class C(Component):
    pass
"""
    tree = ast.parse(src)
    assert lint._file_defines_component_subclass(tree) is True

    src2 = "x = 5\n"
    assert lint._file_defines_component_subclass(ast.parse(src2)) is False


def test_full_mode_catches_classdef_validation_error(tmp_path):
    p = tmp_path / "broken.py"
    p.write_text(
        "from scadwright import Component\n"
        "from scadwright.primitives import cube\n"
        "class Bad(Component):\n"
        "    equations = ['count == 1']\n"
        "    def build(self): return cube(1)\n"
    )
    violations = lint.lint_file(p, full=True)
    assert any(v.rule == "component-classdef-error" for v in violations)
    msg = next(
        v.message for v in violations if v.rule == "component-classdef-error"
    )
    assert "Bad.equations[0]" in msg
    assert "==" in msg


def test_full_mode_ignores_import_error(tmp_path):
    """--full surfaces only ValidationError. ImportError or other
    runtime failures during module load are out of scope — they're
    caught by normal pytest runs."""
    p = tmp_path / "imp_broken.py"
    p.write_text(
        "from scadwright import Component\n"
        "import nonexistent_module_xyz\n"
        "class Stub(Component):\n"
        "    def build(self): pass\n"
    )
    violations = lint.lint_file(p, full=True)
    rules = {v.rule for v in violations}
    assert "import-error" not in rules
    assert "component-classdef-error" not in rules


def test_full_mode_clean_on_valid_file(tmp_path):
    p = tmp_path / "ok.py"
    p.write_text(
        "from scadwright import Component\n"
        "from scadwright.primitives import cube\n"
        "class Tube(Component):\n"
        "    equations = ['od = id + 2*thk', 'h, id, od, thk > 0']\n"
        "    def build(self): return cube(self.h)\n"
    )
    violations = lint.lint_file(p, full=True)
    classdef = [v for v in violations if v.rule == "component-classdef-error"]
    assert classdef == []


def test_default_mode_skips_classdef_check(tmp_path):
    """Without --full, a file with a Component classdef error should not
    surface the import-time check."""
    p = tmp_path / "broken.py"
    p.write_text(
        "from scadwright import Component\n"
        "from scadwright.primitives import cube\n"
        "class Bad(Component):\n"
        "    equations = ['count == 1']\n"
        "    def build(self): return cube(1)\n"
    )
    violations = lint.lint_file(p, full=False)
    assert all(v.rule != "component-classdef-error" for v in violations)


def test_full_mode_skips_files_without_components(tmp_path):
    """Cheap pre-filter: a file with no Component subclass shouldn't
    trigger the import path."""
    p = tmp_path / "no_components.py"
    p.write_text("x = 5\ndef helper(): return 42\n")
    # If the import path were taken, we'd get a successful no-op. The
    # cheap check is that no import-error or classdef-error fires.
    violations = lint.lint_file(p, full=True)
    rules = {v.rule for v in violations}
    assert "component-classdef-error" not in rules


def test_full_mode_clean_on_repo():
    """Regression guard: --full mode on the default paths is also clean."""
    _, violations = lint.run(lint.DEFAULT_PATHS, full=True)
    assert violations == [], (
        "Lint --full caught "
        f"{len(violations)} violation(s):\n"
        + "\n".join(v.format() for v in violations)
    )
