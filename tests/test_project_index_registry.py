"""Tests for the graph class registry.

Covers the inheritance-resolution paths: direct scadwright import,
attribute-style aliased import, scadwright re-export modules,
project-local single-file inheritance chains, project-local
cross-file chains via absolute and relative imports, generic
subscript bases, cycle detection, and unresolvable bases.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.project_index.registry import (
    ClassRegistry,
    build_class_registry,
)
from scadwright.project_index.walk import walk_project


def _registry(tmp_path: Path) -> ClassRegistry:
    files = walk_project(tmp_path)
    return build_class_registry(files, tmp_path)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# =============================================================================
# Direct scadwright bases
# =============================================================================


def test_direct_component_via_from_import(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component\n"
        "class Bracket(Component):\n"
        "    pass\n"
    ))
    reg = _registry(tmp_path)
    [(_, cls)] = reg.classes.items()
    assert cls.name == "Bracket"
    assert cls.category == "component"


def test_direct_spec_via_from_import(tmp_path: Path) -> None:
    _write(tmp_path, "specs.py", (
        "from scadwright import Spec\n"
        "class BatterySpec(Spec):\n"
        "    pass\n"
    ))
    [cls] = list(_registry(tmp_path).classes.values())
    assert cls.category == "spec"


def test_direct_design_via_from_import(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright.design import Design\n"
        "class MyDesign(Design):\n"
        "    pass\n"
    ))
    [cls] = list(_registry(tmp_path).classes.values())
    assert cls.category == "design"


def test_attribute_style_aliased_import(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "import scadwright as sc\n"
        "class Bracket(sc.Component):\n"
        "    pass\n"
    ))
    [cls] = list(_registry(tmp_path).classes.values())
    assert cls.category == "component"


def test_attribute_style_unaliased_import(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "import scadwright\n"
        "class Bracket(scadwright.Component):\n"
        "    pass\n"
    ))
    [cls] = list(_registry(tmp_path).classes.values())
    assert cls.category == "component"


def test_reexport_via_submodule(tmp_path: Path) -> None:
    # ``from scadwright.component.base import Component`` — any
    # scadwright-rooted module exposing ``Component`` counts.
    _write(tmp_path, "widget.py", (
        "from scadwright.component.base import Component\n"
        "class Bracket(Component):\n"
        "    pass\n"
    ))
    [cls] = list(_registry(tmp_path).classes.values())
    assert cls.category == "component"


def test_renamed_import_still_resolves(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component as Comp\n"
        "class Bracket(Comp):\n"
        "    pass\n"
    ))
    [cls] = list(_registry(tmp_path).classes.values())
    assert cls.category == "component"


# =============================================================================
# Project-local inheritance chains
# =============================================================================


def test_local_base_in_same_file(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component\n"
        "class _Plate(Component):\n"
        "    pass\n"
        "class Bracket(_Plate):\n"
        "    pass\n"
    ))
    cats = {c.name: c.category for c in _registry(tmp_path).classes.values()}
    assert cats == {"_Plate": "component", "Bracket": "component"}


def test_local_base_across_files_absolute_import(tmp_path: Path) -> None:
    _write(tmp_path, "bases.py", (
        "from scadwright import Component\n"
        "class _Plate(Component):\n"
        "    pass\n"
    ))
    _write(tmp_path, "widget.py", (
        "from bases import _Plate\n"
        "class Bracket(_Plate):\n"
        "    pass\n"
    ))
    cats = {c.name: c.category for c in _registry(tmp_path).classes.values()}
    assert cats == {"_Plate": "component", "Bracket": "component"}


def test_local_base_across_files_relative_import(tmp_path: Path) -> None:
    pkg = tmp_path / "proj"
    _write(pkg, "__init__.py", "")
    _write(pkg, "bases.py", (
        "from scadwright import Component\n"
        "class _Plate(Component):\n"
        "    pass\n"
    ))
    _write(pkg, "widget.py", (
        "from .bases import _Plate\n"
        "class Bracket(_Plate):\n"
        "    pass\n"
    ))
    files = walk_project(tmp_path)
    reg = build_class_registry(files, tmp_path)
    cats = {c.name: c.category for c in reg.classes.values()}
    assert cats.get("_Plate") == "component"
    assert cats.get("Bracket") == "component"


def test_local_base_from_dot_import_submodule(tmp_path: Path) -> None:
    # ``from . import bases`` binds ``bases`` as a module reference
    # (since ``bases`` is a submodule of the package). Subsequent
    # ``bases._Plate`` is module-attribute access.
    pkg = tmp_path / "proj"
    _write(pkg, "__init__.py", "")
    _write(pkg, "bases.py", (
        "from scadwright import Component\n"
        "class _Plate(Component):\n"
        "    pass\n"
    ))
    _write(pkg, "widget.py", (
        "from . import bases\n"
        "class Bracket(bases._Plate):\n"
        "    pass\n"
    ))
    files = walk_project(tmp_path)
    reg = build_class_registry(files, tmp_path)
    cats = {c.name: c.category for c in reg.classes.values()}
    assert cats.get("Bracket") == "component"


def test_local_base_from_absolute_import_submodule(tmp_path: Path) -> None:
    # Same shape with an absolute import.
    pkg = tmp_path / "proj"
    _write(pkg, "__init__.py", "")
    _write(pkg, "bases.py", (
        "from scadwright import Component\n"
        "class _Plate(Component):\n"
        "    pass\n"
    ))
    _write(pkg, "widget.py", (
        "from proj import bases\n"
        "class Bracket(bases._Plate):\n"
        "    pass\n"
    ))
    files = walk_project(tmp_path)
    reg = build_class_registry(files, tmp_path)
    cats = {c.name: c.category for c in reg.classes.values()}
    assert cats.get("Bracket") == "component"


def test_three_level_inheritance_chain(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component\n"
        "class _Plate(Component):\n"
        "    pass\n"
        "class _Bracket(_Plate):\n"
        "    pass\n"
        "class Specific(_Bracket):\n"
        "    pass\n"
    ))
    cats = {c.name: c.category for c in _registry(tmp_path).classes.values()}
    assert cats == {
        "_Plate": "component",
        "_Bracket": "component",
        "Specific": "component",
    }


# =============================================================================
# Subscript / generic bases
# =============================================================================


def test_generic_subscript_base_resolves_via_value(tmp_path: Path) -> None:
    # ``class Foo(Tube[int]):`` — descend into the subscripted value.
    _write(tmp_path, "widget.py", (
        "from scadwright import Component\n"
        "class Tube(Component):\n"
        "    pass\n"
        "class Foo(Tube[int]):\n"
        "    pass\n"
    ))
    cats = {c.name: c.category for c in _registry(tmp_path).classes.values()}
    assert cats["Foo"] == "component"


def test_typing_generic_base_does_not_categorize(tmp_path: Path) -> None:
    # ``class Foo(Generic[T]):`` — Generic isn't a scadwright base.
    _write(tmp_path, "widget.py", (
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Foo(Generic[T]):\n"
        "    pass\n"
    ))
    [cls] = list(_registry(tmp_path).classes.values())
    assert cls.category == "unknown"


# =============================================================================
# Cycle detection
# =============================================================================


def test_inheritance_cycle_resolves_to_unknown(tmp_path: Path) -> None:
    # A → B → A. Python would actually fail at runtime, but if a
    # static walker hits this it shouldn't loop.
    _write(tmp_path, "widget.py", (
        "class A(B):\n"
        "    pass\n"
        "class B(A):\n"
        "    pass\n"
    ))
    cats = {c.name: c.category for c in _registry(tmp_path).classes.values()}
    assert cats == {"A": "unknown", "B": "unknown"}


# =============================================================================
# Unresolvable bases
# =============================================================================


def test_class_with_no_bases_is_unknown(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", "class Plain:\n    pass\n")
    [cls] = list(_registry(tmp_path).classes.values())
    assert cls.category == "unknown"


def test_third_party_base_is_unknown(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from collections import OrderedDict\n"
        "class Custom(OrderedDict):\n"
        "    pass\n"
    ))
    [cls] = list(_registry(tmp_path).classes.values())
    assert cls.category == "unknown"


def test_unimported_name_base_is_unknown(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "class Custom(SomeMissingThing):\n"
        "    pass\n"
    ))
    [cls] = list(_registry(tmp_path).classes.values())
    assert cls.category == "unknown"


# =============================================================================
# Project-internal re-exports of scadwright base classes
# =============================================================================


def test_reexport_of_scadwright_component(tmp_path: Path) -> None:
    # ``mylib/__init__.py`` re-exports scadwright's Component under
    # an alias; a class elsewhere inherits from the alias. The
    # category resolver must follow the re-export chain back to
    # the scadwright base, otherwise the class silently drops.
    _write(tmp_path, "mylib/__init__.py", (
        "from scadwright import Component as Plate\n"
    ))
    _write(tmp_path, "main.py", (
        "from mylib import Plate\n"
        "class Bracket(Plate):\n"
        "    pass\n"
    ))
    cats = {c.name: c.category for c in _registry(tmp_path).classes.values()}
    assert cats["Bracket"] == "component"


def test_reexport_under_original_name(tmp_path: Path) -> None:
    _write(tmp_path, "mylib/__init__.py", (
        "from scadwright import Component\n"
    ))
    _write(tmp_path, "main.py", (
        "from mylib import Component\n"
        "class Bracket(Component):\n"
        "    pass\n"
    ))
    cats = {c.name: c.category for c in _registry(tmp_path).classes.values()}
    assert cats["Bracket"] == "component"


def test_reexport_of_spec(tmp_path: Path) -> None:
    _write(tmp_path, "mylib/__init__.py", (
        "from scadwright import Spec as Cal\n"
    ))
    _write(tmp_path, "main.py", (
        "from mylib import Cal\n"
        "class BatterySpec(Cal):\n"
        "    pass\n"
    ))
    cats = {c.name: c.category for c in _registry(tmp_path).classes.values()}
    assert cats["BatterySpec"] == "spec"


def test_reexport_chain_two_hops(tmp_path: Path) -> None:
    # mid → top → scadwright. Two project hops before reaching
    # the scadwright base.
    _write(tmp_path, "top/__init__.py", (
        "from scadwright import Component as TopBase\n"
    ))
    _write(tmp_path, "mid/__init__.py", (
        "from top import TopBase as MidBase\n"
    ))
    _write(tmp_path, "main.py", (
        "from mid import MidBase\n"
        "class Bracket(MidBase):\n"
        "    pass\n"
    ))
    cats = {c.name: c.category for c in _registry(tmp_path).classes.values()}
    assert cats["Bracket"] == "component"


def test_reexport_cycle_resolves_to_unknown(tmp_path: Path) -> None:
    # Pathological: two modules re-export from each other with the
    # same name — no actual scadwright base in the chain.
    # The cycle guard must bail rather than recurse forever.
    _write(tmp_path, "a.py", (
        "from b import X\n"
        "Y = X\n"
    ))
    _write(tmp_path, "b.py", (
        "from a import Y as X\n"
    ))
    _write(tmp_path, "main.py", (
        "from a import X\n"
        "class C(X):\n"
        "    pass\n"
    ))
    cats = {c.name: c.category for c in _registry(tmp_path).classes.values()}
    assert cats["C"] == "unknown"  # cycle bails cleanly


# =============================================================================
# Module-path computation
# =============================================================================


def test_module_path_for_root_file(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", "class A: pass\n")
    [cls] = list(_registry(tmp_path).classes.values())
    assert cls.module_path == "main"


def test_module_path_for_nested_file(tmp_path: Path) -> None:
    _write(tmp_path, "sub/foo.py", "class A: pass\n")
    [cls] = list(_registry(tmp_path).classes.values())
    assert cls.module_path == "sub.foo"


def test_module_path_for_init(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "class A: pass\n")
    [cls] = list(_registry(tmp_path).classes.values())
    assert cls.module_path == "pkg"


# =============================================================================
# by_module index
# =============================================================================


def test_by_module_index_keyed_by_dotted_path(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component\n"
        "class A(Component):\n"
        "    pass\n"
    ))
    reg = _registry(tmp_path)
    assert "widget" in reg.by_module
    assert "A" in reg.by_module["widget"]
    assert reg.by_module["widget"]["A"].category == "component"


# =============================================================================
# Multiple categories in one project
# =============================================================================


def test_mixed_components_specs_designs(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Spec\n"
        "from scadwright.design import Design\n"
        "class S(Spec):\n"
        "    pass\n"
        "class C(Component):\n"
        "    pass\n"
        "class D(Design):\n"
        "    pass\n"
    ))
    reg = _registry(tmp_path)
    cats = {c.name: c.category for c in reg.classes.values()}
    assert cats == {"S": "spec", "C": "component", "D": "design"}


# =============================================================================
# Parse errors don't break the build
# =============================================================================


def test_parse_error_in_one_file_doesnt_drop_others(tmp_path: Path) -> None:
    _write(tmp_path, "ok.py", (
        "from scadwright import Component\n"
        "class A(Component):\n"
        "    pass\n"
    ))
    _write(tmp_path, "bad.py", "class A:\n    def\n")  # syntax error
    reg = _registry(tmp_path)
    cats = {c.name: c.category for c in reg.classes.values()}
    assert cats.get("A") == "component"  # the OK file wins
