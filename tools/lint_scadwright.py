"""Style-guide linter for SCADwright code.

Walks Python files under the given paths (default: ``examples/`` and
``src/scadwright/shapes/``) and flags patterns that ``docs/style-guide.md``
says to avoid. The fast path is pure AST -- no imports, no execution.
A separate ``--full`` mode also imports each Component class and
surfaces any class-define-time ``ValidationError`` as a lint violation,
so equations errors become visible in the editor save loop without
running tests.

Usage:
    python tools/lint_scadwright.py                    # AST-only fast path
    python tools/lint_scadwright.py --full             # + import-time checks
    python tools/lint_scadwright.py examples/ src/     # custom paths

Exit code 0 on clean, 1 on violations, 2 on internal errors.

Rules currently enforced (see docs/style-guide.md for rationale):

- ``no-module-eps``: a top-level ``EPS = ...`` assignment. Prefer
  ``.through(parent)`` for cutters or ``.attach(fuse=True)`` for joints;
  when an epsilon is genuinely unavoidable (non-axis-aligned cutters),
  scope it locally inside the function that needs it.

- ``no-param-basic-type``: a ``Param(<basic-type>)`` call where
  ``<basic-type>`` is one of ``float``, ``int``, ``bool``, ``str``,
  ``tuple``, ``list``, ``dict`` — every type in the equations DSL's
  inline-tag allowlist. Use the inline ``:type`` tag in equations
  instead. ``Param()`` is reserved for custom types (namedtuples, spec
  classes, anything outside the allowlist).

- ``translate-single-axis``: ``.translate([x, 0, 0])`` or any permutation
  with two zero literals. Use the directional helper
  (``.right/.left/.up/.down/.forward/.back``) instead.

- ``no-component-setup``: ``def setup(self):`` defined on a class whose
  bases include ``Component``. Every normal case belongs in the
  ``equations`` list — scalar relationships as equalities, computed
  values as derivations (single ``=``), validation as predicates. The
  framework-level hook still exists as an internal escape, but example
  and shape-library code must stay declarative.

- ``component-classdef-error`` (``--full`` only): a ``ValidationError``
  raised when the file is imported. Surfaces equations-DSL errors
  (type tags, ``==`` placement, override patterns, etc.) at lint time
  rather than at construction or test time. Other import-time failures
  (ImportError, registry collisions, etc.) are ignored — those are
  out of scope for the lint and surface during normal test runs.

The linter does not understand comments, so if you need to violate a
rule deliberately, refactor rather than suppress.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


# =============================================================================
# Violation dataclass
# =============================================================================


@dataclass
class Violation:
    path: Path
    line: int
    col: int
    rule: str
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line}:{self.col + 1}: [{self.rule}] {self.message}"


# =============================================================================
# Helpers
# =============================================================================


def _is_zero_literal(node: ast.expr) -> bool:
    """True for `0`, `0.0`, `-0`, `-0.0` as literal constants."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value == 0
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return _is_zero_literal(node.operand)
    return False


# =============================================================================
# Rules
# =============================================================================


def check_module_level_eps(path: Path, tree: ast.Module) -> list[Violation]:
    """Flag `EPS = ...` at module scope."""
    violations: list[Violation] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "EPS":
                violations.append(
                    Violation(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        rule="no-module-eps",
                        message=(
                            "module-level EPS constant. Use .through(parent) "
                            "for cutters or .attach(fuse=True) for joints; "
                            "if manual epsilon is genuinely needed, scope it "
                            "locally inside the function."
                        ),
                    )
                )
    return violations


# Types in the equations DSL's inline-tag allowlist (mirrors
# ``_INLINE_TYPE_ALLOWLIST`` in ``scadwright.component.equations``) plus
# ``float`` — every basic type that an inline ``:type`` tag (or implicit
# ``Param(float)`` auto-declaration) covers.
_BASIC_PARAM_TYPES = frozenset({
    "float", "int", "bool", "str", "tuple", "list", "dict",
})


def check_param_basic_type(path: Path, tree: ast.Module) -> list[Violation]:
    """Flag `Param(<basic-type>)`, with or without `default=`.

    Basic-type Params are obsolete: every type in the inline-tag
    allowlist (`bool`, `int`, `str`, `tuple`, `list`, `dict`) plus
    `float` should be declared via the inline `:type` tag inside an
    equation or constraint line. Per `docs/style-guide.md`, even an
    engineering default (`pressure_angle=20.0`) should live as an
    override pattern in the equations block, not as a `default=` on a
    reusable Component's Param.
    """
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match `Param(...)` — accept bare Name or Attribute forms.
        if isinstance(func, ast.Name) and func.id == "Param":
            pass
        elif isinstance(func, ast.Attribute) and func.attr == "Param":
            pass
        else:
            continue
        # First positional arg must be a bare Name in the basic-type set.
        if not node.args:
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Name) and first.id in _BASIC_PARAM_TYPES):
            continue
        type_name = first.id
        violations.append(
            Violation(
                path=path,
                line=node.lineno,
                col=node.col_offset,
                rule="no-param-basic-type",
                message=(
                    f"Param({type_name}) is obsolete. Use the inline "
                    f"`:type` tag in `equations` instead, e.g. "
                    f"`name:{type_name}` on a constraint or equation line. "
                    f"`Param()` is reserved for custom types "
                    f"(namedtuples, spec classes, etc.)."
                ),
            )
        )
    return violations


def check_translate_single_axis(path: Path, tree: ast.Module) -> list[Violation]:
    """Flag `.translate([x, 0, 0])` etc. -- use directional helpers."""
    violations: list[Violation] = []
    helpers = ("right/left", "back/forward", "up/down")

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "translate":
            continue
        if len(node.args) != 1:
            continue
        arg = node.args[0]
        if not isinstance(arg, (ast.List, ast.Tuple)):
            continue
        if len(arg.elts) != 3:
            continue
        zeros = [_is_zero_literal(e) for e in arg.elts]
        if sum(zeros) != 2:
            continue
        non_zero_idx = zeros.index(False)
        violations.append(
            Violation(
                path=path,
                line=node.lineno,
                col=node.col_offset,
                rule="translate-single-axis",
                message=(
                    f"single-axis translate. Use the directional helper "
                    f".{helpers[non_zero_idx]}() instead."
                ),
            )
        )
    return violations


def check_component_setup(path: Path, tree: ast.Module) -> list[Violation]:
    """Flag `def setup(self):` on any class whose bases include Component.

    Detection is name-based (any base class named ``Component`` or ending in
    ``Component``, whether bare-name or attribute access) so the rule fires
    without import resolution. The framework hook still exists for internal
    use; this rule enforces the convention that user-facing code stays
    declarative — derivations and predicates cover every normal case.
    """
    violations: list[Violation] = []

    def _inherits_from_component(cls: ast.ClassDef) -> bool:
        for base in cls.bases:
            # Bare name: `class X(Component):`
            if isinstance(base, ast.Name) and (
                base.id == "Component" or base.id.endswith("Component")
            ):
                return True
            # Attribute: `class X(sc.Component):`, `class X(scadwright.Component):`
            if isinstance(base, ast.Attribute) and (
                base.attr == "Component" or base.attr.endswith("Component")
            ):
                return True
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not _inherits_from_component(node):
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            if item.name != "setup":
                continue
            if not item.args.args:
                continue
            if item.args.args[0].arg != "self":
                continue
            violations.append(
                Violation(
                    path=path,
                    line=item.lineno,
                    col=item.col_offset,
                    rule="no-component-setup",
                    message=(
                        f"`{node.name}.setup()` — move computed values to "
                        f"derivations in `equations` (single `=`) and "
                        f"validation to predicates. The setup() framework "
                        f"hook stays for internal escape only; user-facing "
                        f"Components must be declarative."
                    ),
                )
            )
    return violations


RULES: list[Callable[[Path, ast.Module], list[Violation]]] = [
    check_module_level_eps,
    check_param_basic_type,
    check_translate_single_axis,
    check_component_setup,
]


# =============================================================================
# Full-mode rule: import-time class-define-time errors
# =============================================================================
#
# Loads each file that defines Component subclasses and surfaces any
# ValidationError raised during class definition. This catches every
# parser-level correctness check (==-placement, type-allowlist, bool-in-
# arithmetic, non-float-as-solver-target, override-RHS-evaluable, self-
# reference, mutual-inconsistency) in one pass. Single source of truth —
# the framework's existing checks run; the lint just collects failures.


def _file_defines_component_subclass(tree: ast.Module) -> bool:
    """Cheap pre-filter: does the AST contain a class whose bases name
    `Component`? Avoids importing files that have nothing to check."""
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            if isinstance(base, ast.Name) and (
                base.id == "Component" or base.id.endswith("Component")
            ):
                return True
            if isinstance(base, ast.Attribute) and (
                base.attr == "Component" or base.attr.endswith("Component")
            ):
                return True
    return False


def check_component_classdef_errors(path: Path) -> list[Violation]:
    """Import the file and surface ValidationErrors raised at class-def time.

    Returns a single Violation per file at most — the first
    ValidationError stops module loading, and that's typically the only
    error the user can act on until it's fixed.

    Only ``ValidationError`` is surfaced. Other import-time failures
    (ImportError, registry collisions when a Component file is loaded
    twice with global side effects, etc.) are ignored — those are
    caught by pytest at normal test time and aren't the equations-DSL
    correctness errors this mode targets.
    """
    import importlib.util

    # Stable module name so re-running the lint doesn't accumulate
    # duplicates in sys.modules.
    mod_name = f"_scadwright_lint_{path.stem}_{abs(hash(str(path.resolve())))}"
    try:
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            return []
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException as exc:
            from scadwright.errors import ValidationError as _ValErr
            if not isinstance(exc, _ValErr):
                # Non-ValidationError failures are out of scope.
                return []
            line = 0
            if hasattr(exc, "source_location") and exc.source_location is not None:
                loc = exc.source_location
                if getattr(loc, "line", None):
                    line = loc.line
            return [
                Violation(
                    path=path,
                    line=line,
                    col=0,
                    rule="component-classdef-error",
                    message=str(exc).replace("\n", " | "),
                )
            ]
    finally:
        sys.modules.pop(mod_name, None)
    return []


# =============================================================================
# File discovery + driver
# =============================================================================


DEFAULT_PATHS = ("examples", "src/scadwright/shapes")


def lint_file(path: Path, *, full: bool = False) -> list[Violation]:
    try:
        source = path.read_text()
    except (OSError, UnicodeDecodeError) as exc:
        return [
            Violation(
                path=path, line=0, col=0, rule="read-error", message=str(exc)
            )
        ]
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [
            Violation(
                path=path,
                line=exc.lineno or 0,
                col=(exc.offset or 1) - 1,
                rule="parse-error",
                message=exc.msg,
            )
        ]
    violations: list[Violation] = []
    for rule in RULES:
        violations.extend(rule(path, tree))
    if full and _file_defines_component_subclass(tree):
        violations.extend(check_component_classdef_errors(path))
    return violations


def collect_files(paths: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        root = Path(p)
        if root.is_file() and root.suffix == ".py":
            files.append(root)
        elif root.is_dir():
            files.extend(sorted(root.rglob("*.py")))
    return files


def run(paths: Iterable[str], *, full: bool = False) -> tuple[int, list[Violation]]:
    """Lint the given paths. Returns (file_count, violations)."""
    files = collect_files(paths)
    violations: list[Violation] = []
    for f in files:
        violations.extend(lint_file(f, full=full))
    return len(files), violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Style-guide linter for SCADwright code.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help=f"files or directories to lint (default: {' '.join(DEFAULT_PATHS)})",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help=(
            "also import each file containing a Component subclass and "
            "surface ValidationErrors raised at class definition time as "
            "lint violations. Slower (imports the framework + sympy)."
        ),
    )
    args = parser.parse_args(argv)
    paths = args.paths or list(DEFAULT_PATHS)

    file_count, violations = run(paths, full=args.full)
    if not violations:
        print(f"clean: {file_count} file(s) checked.")
        return 0

    for v in violations:
        print(v.format())
    print(f"\n{len(violations)} violation(s) in {file_count} file(s) checked.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
