"""Tests for the graph walker.

Covers single-file and directory inputs, the import-binding
extraction across the various Python import shapes, ClassDef
capture (top-level + nested), parse-error tolerance, and the
directory-skip rules.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scadwright.project_index.walk import (
    ClassDefInfo,
    FileInfo,
    ImportInfo,
    walk_project,
)


# =============================================================================
# Single-file input
# =============================================================================


def test_walk_single_python_file(tmp_path: Path) -> None:
    f = tmp_path / "widget.py"
    f.write_text("class A:\n    pass\n")
    files = walk_project(f)
    assert len(files) == 1
    assert files[0].path == f
    assert files[0].parse_error is None
    assert len(files[0].classes) == 1
    assert files[0].classes[0].name == "A"


def test_walk_non_python_single_file_returns_empty(tmp_path: Path) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("nothing")
    assert walk_project(f) == []


def test_walk_nonexistent_path_returns_empty(tmp_path: Path) -> None:
    assert walk_project(tmp_path / "does-not-exist") == []


# =============================================================================
# Directory recursion + skip rules
# =============================================================================


def test_walk_directory_finds_every_py_file(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("class A: pass\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("class B: pass\n")
    files = walk_project(tmp_path)
    names = sorted(f.path.name for f in files)
    assert names == ["a.py", "b.py"]


def test_walk_skips_pycache(tmp_path: Path) -> None:
    (tmp_path / "real.py").write_text("class A: pass\n")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "ignored.py").write_text("class Ignored: pass\n")
    files = walk_project(tmp_path)
    assert [f.path.name for f in files] == ["real.py"]


def test_walk_skips_node_modules(tmp_path: Path) -> None:
    (tmp_path / "real.py").write_text("class A: pass\n")
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "vendored.py").write_text("class Vendor: pass\n")
    files = walk_project(tmp_path)
    assert [f.path.name for f in files] == ["real.py"]


def test_walk_skips_hidden_dirs(tmp_path: Path) -> None:
    (tmp_path / "real.py").write_text("class A: pass\n")
    for hidden in (".venv", ".git", ".idea", ".tox"):
        d = tmp_path / hidden
        d.mkdir()
        (d / "junk.py").write_text("class Junk: pass\n")
    files = walk_project(tmp_path)
    assert [f.path.name for f in files] == ["real.py"]


def test_walk_results_are_sorted(tmp_path: Path) -> None:
    for name in ("zeta.py", "alpha.py", "mu.py"):
        (tmp_path / name).write_text("class X: pass\n")
    files = walk_project(tmp_path)
    assert [f.path.name for f in files] == ["alpha.py", "mu.py", "zeta.py"]


# =============================================================================
# Imports
# =============================================================================


def _imports_of(source: str, tmp_path: Path) -> tuple[ImportInfo, ...]:
    f = tmp_path / "t.py"
    f.write_text(source)
    return walk_project(f)[0].imports


def test_import_module_form(tmp_path: Path) -> None:
    [imp] = _imports_of("import scadwright\n", tmp_path)
    assert imp.local_name == "scadwright"
    assert imp.source_module == "scadwright"
    assert imp.source_attr is None
    assert imp.is_relative is False


def test_import_with_alias(tmp_path: Path) -> None:
    [imp] = _imports_of("import scadwright as sc\n", tmp_path)
    assert imp.local_name == "sc"
    assert imp.source_module == "scadwright"
    assert imp.source_attr is None


def test_import_dotted_module_uses_top_segment_for_local_name(
    tmp_path: Path,
) -> None:
    # ``import scadwright.shapes`` binds ``scadwright`` in the
    # namespace; the dotted name is the source.
    [imp] = _imports_of("import scadwright.shapes\n", tmp_path)
    assert imp.local_name == "scadwright"
    assert imp.source_module == "scadwright.shapes"


def test_from_import_simple(tmp_path: Path) -> None:
    [imp] = _imports_of(
        "from scadwright import Component\n", tmp_path,
    )
    assert imp.local_name == "Component"
    assert imp.source_module == "scadwright"
    assert imp.source_attr == "Component"
    assert imp.is_relative is False


def test_from_import_with_alias(tmp_path: Path) -> None:
    [imp] = _imports_of(
        "from scadwright import Component as Comp\n", tmp_path,
    )
    assert imp.local_name == "Comp"
    assert imp.source_attr == "Component"


def test_from_import_multiple_names(tmp_path: Path) -> None:
    imports = _imports_of(
        "from scadwright import Component, Param, Spec\n", tmp_path,
    )
    assert {i.local_name for i in imports} == {"Component", "Param", "Spec"}


def test_relative_from_import(tmp_path: Path) -> None:
    [imp] = _imports_of("from . import helpers\n", tmp_path)
    assert imp.local_name == "helpers"
    assert imp.is_relative is True
    assert imp.relative_level == 1


def test_double_relative_from_import(tmp_path: Path) -> None:
    [imp] = _imports_of("from .. import shared\n", tmp_path)
    assert imp.relative_level == 2


def test_function_local_imports_not_captured(tmp_path: Path) -> None:
    src = (
        "def f():\n"
        "    import scadwright\n"
        "class A: pass\n"
    )
    [info] = walk_project(_write(tmp_path, "t.py", src))
    assert info.imports == ()


def test_class_body_imports_not_captured(tmp_path: Path) -> None:
    src = (
        "class A:\n"
        "    import scadwright\n"
    )
    [info] = walk_project(_write(tmp_path, "t.py", src))
    assert info.imports == ()


def test_imports_inside_try_at_module_scope_captured(tmp_path: Path) -> None:
    # Common fallback shape — make sure conditional imports at module
    # scope still register their bindings.
    src = (
        "try:\n"
        "    from scadwright import Component\n"
        "except ImportError:\n"
        "    Component = None\n"
    )
    [info] = walk_project(_write(tmp_path, "t.py", src))
    names = {i.local_name for i in info.imports}
    assert "Component" in names


def test_imports_inside_if_typechecking_captured(tmp_path: Path) -> None:
    src = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from scadwright import Component\n"
    )
    [info] = walk_project(_write(tmp_path, "t.py", src))
    names = {i.local_name for i in info.imports}
    assert "Component" in names
    assert "TYPE_CHECKING" in names


def test_imports_inside_with_block_captured(tmp_path: Path) -> None:
    # Less common but valid: ``with`` blocks at module scope.
    src = (
        "import contextlib\n"
        "with contextlib.suppress(ImportError):\n"
        "    from scadwright import Component\n"
    )
    [info] = walk_project(_write(tmp_path, "t.py", src))
    names = {i.local_name for i in info.imports}
    assert "Component" in names


# =============================================================================
# Classes
# =============================================================================


def test_class_with_no_bases(tmp_path: Path) -> None:
    f = _write(tmp_path, "t.py", "class A:\n    pass\n")
    [info] = walk_project(f)
    [cls] = info.classes
    assert cls.name == "A"
    assert cls.bases == ()


def test_class_with_one_base(tmp_path: Path) -> None:
    f = _write(tmp_path, "t.py", "class A(B):\n    pass\n")
    [info] = walk_project(f)
    [cls] = info.classes
    assert cls.bases == ("B",)


def test_class_with_multiple_bases(tmp_path: Path) -> None:
    f = _write(tmp_path, "t.py", "class A(B, C, D):\n    pass\n")
    [info] = walk_project(f)
    [cls] = info.classes
    assert cls.bases == ("B", "C", "D")


def test_class_with_attribute_base(tmp_path: Path) -> None:
    f = _write(tmp_path, "t.py", "class A(sc.Component):\n    pass\n")
    [info] = walk_project(f)
    [cls] = info.classes
    assert cls.bases == ("sc.Component",)


def test_nested_classes_captured(tmp_path: Path) -> None:
    src = (
        "class Outer:\n"
        "    class Inner:\n"
        "        pass\n"
    )
    f = _write(tmp_path, "t.py", src)
    [info] = walk_project(f)
    names = {c.name for c in info.classes}
    assert names == {"Outer", "Inner"}


def test_class_position_info(tmp_path: Path) -> None:
    src = "class A:\n    pass\n"
    f = _write(tmp_path, "t.py", src)
    [info] = walk_project(f)
    [cls] = info.classes
    assert cls.line == 0
    assert cls.col == 0
    # End covers the body.
    assert cls.end_line >= cls.line


def test_class_ast_node_preserved(tmp_path: Path) -> None:
    import ast
    src = "class A:\n    pass\n"
    f = _write(tmp_path, "t.py", src)
    [info] = walk_project(f)
    [cls] = info.classes
    assert isinstance(cls.ast_node, ast.ClassDef)
    assert cls.ast_node.name == "A"


# =============================================================================
# Parse-error tolerance
# =============================================================================


def test_parse_error_returns_file_info_with_message(tmp_path: Path) -> None:
    f = _write(tmp_path, "t.py", "class A:\n    def\n")  # syntax error
    [info] = walk_project(f)
    assert info.parse_error is not None
    assert info.classes == ()
    assert info.imports == ()


def test_parse_error_in_one_file_doesnt_drop_others(tmp_path: Path) -> None:
    _write(tmp_path, "ok.py", "class Ok: pass\n")
    _write(tmp_path, "bad.py", "class Bad:\n    def\n")
    files = walk_project(tmp_path)
    by_name = {f.path.name: f for f in files}
    assert by_name["ok.py"].parse_error is None
    assert by_name["bad.py"].parse_error is not None
    assert by_name["ok.py"].classes[0].name == "Ok"


# =============================================================================
# Helpers
# =============================================================================


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


def test_file_info_is_immutable(tmp_path: Path) -> None:
    f = _write(tmp_path, "t.py", "class A: pass\n")
    [info] = walk_project(f)
    assert isinstance(info, FileInfo)
    with pytest.raises(Exception):
        info.path = tmp_path / "other.py"  # type: ignore[misc]
