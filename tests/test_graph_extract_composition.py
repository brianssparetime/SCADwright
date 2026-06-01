"""Tests for the build()-body composition extractor.

Covers ``OtherComponent(...)`` instantiation detection inside
``build``: same-file and cross-file resolution, dedupe of
repeated instantiations, calls inside conditionals/loops,
attribute-style callees, primitive factory calls dropped, classes
with no build, Spec callees not surfaced.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.graph.extract import (
    CompositionRef,
    extract_build_instantiations,
)
from scadwright.project_index.registry import build_class_registry
from scadwright.project_index.walk import walk_project


def _setup(tmp_path: Path, class_name: str):
    files = walk_project(tmp_path)
    registry = build_class_registry(files, tmp_path)
    cls = next(c for c in registry.classes.values() if c.name == class_name)
    file_info = next(f for f in files if f.path == cls.file_path)
    return cls, file_info, registry


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _refs(tmp_path: Path, class_name: str) -> tuple[CompositionRef, ...]:
    cls, file_info, registry = _setup(tmp_path, class_name)
    return extract_build_instantiations(cls, file_info, registry, tmp_path)


# =============================================================================
# Project Component instantiation
# =============================================================================


def test_instantiation_of_same_file_component(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class Inner(Component):\n"
        "    pass\n"
        "class Outer(Component):\n"
        "    def build(self):\n"
        "        return Inner()\n"
    ))
    [r] = _refs(tmp_path, "Outer")
    assert r.target.name == "Inner"


def test_instantiation_of_cross_file_component(tmp_path: Path) -> None:
    _write(tmp_path, "inner.py", (
        "from scadwright import Component\n"
        "class Inner(Component):\n"
        "    pass\n"
    ))
    _write(tmp_path, "outer.py", (
        "from scadwright import Component\n"
        "from inner import Inner\n"
        "class Outer(Component):\n"
        "    def build(self):\n"
        "        return Inner(width=5)\n"
    ))
    [r] = _refs(tmp_path, "Outer")
    assert r.target.name == "Inner"
    assert r.target.module_path == "inner"


def test_repeated_instantiation_deduplicated(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class Inner(Component):\n"
        "    pass\n"
        "class Outer(Component):\n"
        "    def build(self):\n"
        "        a = Inner()\n"
        "        b = Inner(width=5)\n"
        "        return [a, b]\n"
    ))
    refs = _refs(tmp_path, "Outer")
    assert len(refs) == 1


def test_instantiation_inside_conditional(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class A(Component):\n"
        "    pass\n"
        "class B(Component):\n"
        "    pass\n"
        "class C(Component):\n"
        "    def build(self):\n"
        "        if some_flag:\n"
        "            return A()\n"
        "        return B()\n"
    ))
    targets = sorted(r.target.name for r in _refs(tmp_path, "C"))
    assert targets == ["A", "B"]


def test_instantiation_inside_loop(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class Cell(Component):\n"
        "    pass\n"
        "class Pack(Component):\n"
        "    def build(self):\n"
        "        return [Cell() for _ in range(8)]\n"
    ))
    [r] = _refs(tmp_path, "Pack")
    assert r.target.name == "Cell"


def test_instantiation_nested_in_boolop_call(tmp_path: Path) -> None:
    # Component instances passed as args to ``union(...)`` /
    # ``difference(...)`` etc. — ast.walk recurses through the
    # Call args and surfaces the inner Component instantiations.
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "from scadwright.boolops import union\n"
        "class A(Component):\n"
        "    pass\n"
        "class B(Component):\n"
        "    pass\n"
        "class Outer(Component):\n"
        "    def build(self):\n"
        "        return union(A(), B())\n"
    ))
    targets = sorted(r.target.name for r in _refs(tmp_path, "Outer"))
    assert targets == ["A", "B"]


def test_instantiation_in_aliased_import(tmp_path: Path) -> None:
    _write(tmp_path, "inner.py", (
        "from scadwright import Component\n"
        "class Inner(Component):\n"
        "    pass\n"
    ))
    _write(tmp_path, "outer.py", (
        "from scadwright import Component\n"
        "from inner import Inner as IN\n"
        "class Outer(Component):\n"
        "    def build(self):\n"
        "        return IN()\n"
    ))
    [r] = _refs(tmp_path, "Outer")
    assert r.target.name == "Inner"


# =============================================================================
# Filtering
# =============================================================================


def test_curated_factory_calls_dropped(tmp_path: Path) -> None:
    # ``cube``, ``cylinder``, etc. aren't project Components; the
    # registry doesn't know them, so they don't surface as edges.
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "from scadwright.primitives import cube, cylinder\n"
        "from scadwright.boolops import union\n"
        "class A(Component):\n"
        "    def build(self):\n"
        "        return union(cube([1,1,1]), cylinder(r=1, h=1))\n"
    ))
    assert _refs(tmp_path, "A") == ()


def test_spec_callee_not_surfaced(tmp_path: Path) -> None:
    # Specs CAN be instantiated (`SomeSpec(printer="X")`), but a
    # build() body invoking one is unusual and we don't model that
    # as a "contains" edge. ``contains`` is component-to-component.
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Spec\n"
        "class S(Spec):\n"
        "    pass\n"
        "class A(Component):\n"
        "    def build(self):\n"
        "        s = S()\n"
        "        return None\n"
    ))
    assert _refs(tmp_path, "A") == ()


def test_unresolvable_callee_dropped(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class A(Component):\n"
        "    def build(self):\n"
        "        return MysteryThing()\n"
    ))
    assert _refs(tmp_path, "A") == ()


def test_class_without_build_method(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class A(Component):\n"
        "    pass\n"
    ))
    assert _refs(tmp_path, "A") == ()


# =============================================================================
# Class-attribute Component instantiation
# =============================================================================


def test_class_attribute_instantiation_surfaces(tmp_path: Path) -> None:
    # ``inner = Inner()`` at class scope — design doc explicitly
    # lists this alongside build()-body instantiation as a source
    # of contains edges.
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class Inner(Component):\n"
        "    pass\n"
        "class Outer(Component):\n"
        "    inner = Inner()\n"
        "    def build(self):\n"
        "        return self.inner\n"
    ))
    [r] = _refs(tmp_path, "Outer")
    assert r.target.name == "Inner"


def test_class_attribute_and_build_dedupe_to_one(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class Inner(Component):\n"
        "    pass\n"
        "class Outer(Component):\n"
        "    inner = Inner()\n"
        "    def build(self):\n"
        "        return Inner()\n"
    ))
    refs = _refs(tmp_path, "Outer")
    assert len(refs) == 1
    assert refs[0].target.name == "Inner"


def test_class_attribute_only_components_surface(tmp_path: Path) -> None:
    # ``s = SomeSpec()`` and ``flag = True`` at class scope must not
    # surface — class-attribute composition is Component-only.
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Spec\n"
        "class S(Spec):\n"
        "    pass\n"
        "class Outer(Component):\n"
        "    s = S()\n"
        "    flag = True\n"
        "    n = int(5)\n"
    ))
    assert _refs(tmp_path, "Outer") == ()


# =============================================================================
# Attribute-style callees
# =============================================================================


def test_attribute_style_callee(tmp_path: Path) -> None:
    _write(tmp_path, "inner.py", (
        "from scadwright import Component\n"
        "class Inner(Component):\n"
        "    pass\n"
    ))
    _write(tmp_path, "outer.py", (
        "from scadwright import Component\n"
        "import inner\n"
        "class Outer(Component):\n"
        "    def build(self):\n"
        "        return inner.Inner()\n"
    ))
    [r] = _refs(tmp_path, "Outer")
    assert r.target.name == "Inner"


# =============================================================================
# Self.something() calls (not contains — they're calls on an
# already-supplied Param, not instantiation)
# =============================================================================


def test_self_attribute_call_not_a_contains(tmp_path: Path) -> None:
    # ``self.spec.method()`` doesn't instantiate a Component, just
    # invokes a method. Not a contains edge.
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Param, Spec\n"
        "class S(Spec):\n"
        "    pass\n"
        "class A(Component):\n"
        "    spec = Param(S)\n"
        "    def build(self):\n"
        "        return self.spec.something()\n"
    ))
    assert _refs(tmp_path, "A") == ()


# =============================================================================
# Helper-method scope (Component instantiation outside build())
# =============================================================================


def test_instantiation_in_helper_method_surfaces(tmp_path: Path) -> None:
    """Component instantiation in a helper method (not ``build``)
    should still surface as composition.
    """
    _write(tmp_path, "widget.py", (
        "from scadwright import Component\n"
        "class Inner(Component):\n"
        "    pass\n"
        "class Outer(Component):\n"
        "    def build(self):\n"
        "        return self._make()\n"
        "    def _make(self):\n"
        "        return Inner()\n"
    ))
    refs = _refs(tmp_path, "Outer")
    targets = {r.target.name for r in refs}
    assert targets == {"Inner"}
