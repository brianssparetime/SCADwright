"""Tests for the ASCII project-map renderer.

The renderer turns a built :class:`Graph` into a grouped, plain-text
project map. These build small synthetic projects end-to-end and
assert on the rendered text, since the rendering is what the user
reads.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.graph.build import build_graph
from scadwright.graph.render_ascii import render_ascii


def _write(root: Path, name: str, src: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(src)


def test_header_and_counts(tmp_path: Path) -> None:
    _write(tmp_path, "main.py",
           "from scadwright import Component\n"
           "class A(Component):\n"
           "    pass\n")
    out = render_ascii(build_graph(tmp_path))
    assert out.startswith("scadwright project:")
    assert "1 component." in out


def test_empty_project(tmp_path: Path) -> None:
    out = render_ascii(build_graph(tmp_path))
    assert "(empty project)" in out
    # Empty sections are omitted entirely.
    assert "Components" not in out


def test_component_uses_spec_and_spec_read_by_map(tmp_path: Path) -> None:
    _write(tmp_path, "main.py",
           "from scadwright import Component, Spec, Param\n"
           "class CellSpec(Spec):\n"
           "    equations = 'cells = 4'\n"
           "class Holder(Component):\n"
           "    spec = Param(CellSpec)\n"
           "    equations = 'wall = spec.cells * 2'\n")
    out = render_ascii(build_graph(tmp_path))
    # Component names the spec; fields live on the spec, not the part.
    assert "uses Spec  CellSpec" in out
    assert "wall" not in out  # the component doesn't list read fields
    assert "read by Component" in out
    assert "cells  Holder" in out
    # Locations are bracketed.
    assert "[main.py:" in out


def test_inheritance_folded_and_reverse_shown(tmp_path: Path) -> None:
    _write(tmp_path, "main.py",
           "from scadwright import Component\n"
           "class Base(Component):\n"
           "    pass\n"
           "class Concrete(Base):\n"
           "    pass\n")
    out = render_ascii(build_graph(tmp_path))
    assert "Concrete (a Base) [" in out
    assert "specialized by Component  Concrete" in out


def test_design_variant_default_and_built_by(tmp_path: Path) -> None:
    _write(tmp_path, "main.py",
           "from scadwright import Component\n"
           "from scadwright.design import Design, variant\n"
           "class Part(Component):\n"
           "    pass\n"
           "class Box(Design):\n"
           "    part = Part()\n"
           "    @variant(default=True)\n"
           "    def show(self):\n"
           "        return self.part\n")
    out = render_ascii(build_graph(tmp_path))
    assert "Variant show (default)  builds Component  Part" in out
    assert "built by Design  Box" in out


def test_morph_renders_with_numbered_stages(tmp_path: Path) -> None:
    _write(tmp_path, "main.py",
           "from scadwright import Component, morph\n"
           "from scadwright.design import Design, variant\n"
           "class Part(Component):\n"
           "    pass\n"
           "class M(Design):\n"
           "    part = Part()\n"
           "    @variant()\n"
           "    def a(self):\n"
           "        return self.part\n"
           "    @variant()\n"
           "    def b(self):\n"
           "        return self.part\n"
           "    anim = morph(stages=['a', 'b'])\n")
    out = render_ascii(build_graph(tmp_path))
    assert "Morph anim" in out
    assert "builds Component  Part" in out
    assert "uses Variant as stage" in out
    assert "1. a" in out
    assert "2. b" in out


def test_long_list_breaks_vertical(tmp_path: Path) -> None:
    _write(tmp_path, "main.py",
           "from scadwright import Component\n"
           "from scadwright.boolops import union\n"
           "from scadwright.design import Design, variant\n"
           + "".join(
               f"class P{i}(Component):\n    pass\n" for i in range(1, 5)
           )
           + "class D(Design):\n"
           "    p1 = P1()\n    p2 = P2()\n    p3 = P3()\n    p4 = P4()\n"
           "    @variant(default=True)\n"
           "    def show(self):\n"
           "        return union(self.p1, self.p2, self.p3, self.p4)\n")
    out = render_ascii(build_graph(tmp_path))
    # Four build targets exceed the inline threshold, so they wrap.
    assert "builds Component\n" in out
    assert "      P1\n" in out
    assert "      P4\n" in out


def test_untraceable_variant_labeled_no_parts_traced(tmp_path: Path) -> None:
    _write(tmp_path, "main.py",
           "from scadwright.primitives import cube\n"
           "from scadwright.design import Design, variant\n"
           "class D(Design):\n"
           "    @variant(default=True)\n"
           "    def show(self):\n"
           "        return cube([1, 1, 1])\n")
    out = render_ascii(build_graph(tmp_path))
    assert "no parts traced" in out


def test_colliding_labels_qualified_by_module(tmp_path: Path) -> None:
    _write(tmp_path, "a.py",
           "from scadwright import Component\n"
           "class Part(Component):\n"
           "    pass\n")
    _write(tmp_path, "b.py",
           "from scadwright import Component\n"
           "class Part(Component):\n"
           "    pass\n")
    out = render_ascii(build_graph(tmp_path))
    assert "a.Part [" in out
    assert "b.Part [" in out


def test_warnings_section_present_when_warnings(tmp_path: Path) -> None:
    # A Component class bound to an inherited Param raises at runtime;
    # the builder surfaces it as a warning.
    _write(tmp_path, "main.py",
           "from scadwright import Component, Param\n"
           "class Inner(Component):\n"
           "    pass\n"
           "class Base(Component):\n"
           "    thing = Param()\n"
           "class Concrete(Base):\n"
           "    thing = Inner\n")
    out = render_ascii(build_graph(tmp_path))
    assert "Warnings" in out
