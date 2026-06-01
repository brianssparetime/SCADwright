"""Tests for the graph build()-body attribute-read extractor.

Covers ``self.x.y`` reads where ``x`` is a Param, dedupe across
multiple reads, primitive-typed Param target=None, classes without
build(), nested patterns (calls / conditionals / comprehensions),
deeper chains stopping at the first hop, and bare ``self.x``
reads not being recorded.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.graph.extract import (
    AttributeRead,
    build_params_by_class,
    extract_build_attribute_reads,
)
from scadwright.project_index.registry import build_class_registry
from scadwright.project_index.walk import walk_project


def _setup(tmp_path: Path, class_name: str):
    files = walk_project(tmp_path)
    registry = build_class_registry(files, tmp_path)
    files_by_path = {f.path: f for f in files}
    cls = next(c for c in registry.classes.values() if c.name == class_name)
    params_by_class = build_params_by_class(registry, files_by_path, tmp_path)
    return cls, params_by_class


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _build_reads(tmp_path: Path, class_name: str) -> tuple[AttributeRead, ...]:
    cls, params_by_class = _setup(tmp_path, class_name)
    return extract_build_attribute_reads(cls, params_by_class)


# =============================================================================
# self.x.y on a Param-typed base
# =============================================================================


def test_self_attr_attr_read_on_spec_typed_param(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "from scadwright.primitives import cube\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        "    def build(self):\n"
        "        return cube([self.spec.outer_d, 5, 5])\n"
    ))
    [r] = _build_reads(tmp_path, "Cam")
    assert r.base_name == "spec"
    assert r.attr == "outer_d"
    assert r.target is not None
    assert r.target.name == "CamSpec"


def test_multiple_self_attr_reads_on_same_param(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        "    def build(self):\n"
        "        x = self.spec.outer_d\n"
        "        y = self.spec.height\n"
        "        return None\n"
    ))
    reads = _build_reads(tmp_path, "Cam")
    attrs = sorted(r.attr for r in reads)
    assert attrs == ["height", "outer_d"]


def test_repeated_self_attr_read_deduplicated(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        "    def build(self):\n"
        "        return self.spec.outer_d + self.spec.outer_d\n"
    ))
    reads = _build_reads(tmp_path, "Cam")
    assert len(reads) == 1


# =============================================================================
# Bare self.x doesn't get recorded
# =============================================================================


def test_bare_self_attr_not_recorded(tmp_path: Path) -> None:
    # ``self.width`` alone is an own-Param read, not a cross-Component
    # edge. The extractor should ignore it.
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "from scadwright.primitives import cube\n"
        "class Bracket(Component):\n"
        "    width = Param(float)\n"
        "    def build(self):\n"
        "        return cube([self.width, 5, 5])\n"
    ))
    assert _build_reads(tmp_path, "Bracket") == ()


# =============================================================================
# Chains resolve as far as declared Param types reach
# =============================================================================


def test_deep_chain_stops_at_non_param_hop(tmp_path: Path) -> None:
    # ``self.spec.inner.attr`` records ``inner`` off CamSpec, then
    # stops: ``inner`` isn't a declared Param of CamSpec, so its type
    # is unknown and ``attr`` can't be attributed to a class.
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        "    def build(self):\n"
        "        return self.spec.inner.attr\n"
    ))
    reads = _build_reads(tmp_path, "Cam")
    assert len(reads) == 1
    assert reads[0].attr == "inner"


# =============================================================================
# Primitive Param: target=None
# =============================================================================


def test_self_attr_read_on_primitive_param_not_recorded(tmp_path: Path) -> None:
    # ``self.width.real`` where width is a primitive Param doesn't
    # resolve to a project class, so it isn't a cross-class read.
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "class Bracket(Component):\n"
        "    width = Param(float)\n"
        "    def build(self):\n"
        "        return self.width.real\n"
    ))
    assert _build_reads(tmp_path, "Bracket") == ()


# =============================================================================
# self.x.y inside nested AST shapes
# =============================================================================


def test_self_attr_read_inside_call(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "from scadwright.primitives import cube\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        "    def build(self):\n"
        "        return cube([self.spec.outer_d, 5, 5])\n"
    ))
    [r] = _build_reads(tmp_path, "Cam")
    assert r.attr == "outer_d"


def test_self_attr_read_inside_conditional(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        "    def build(self):\n"
        "        if self.spec.has_taper:\n"
        "            return self.spec.outer_d\n"
        "        return None\n"
    ))
    reads = _build_reads(tmp_path, "Cam")
    attrs = sorted(r.attr for r in reads)
    assert attrs == ["has_taper", "outer_d"]


def test_self_attr_read_inside_comprehension(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        "    def build(self):\n"
        "        return [x * self.spec.scale for x in range(3)]\n"
    ))
    [r] = _build_reads(tmp_path, "Cam")
    assert r.attr == "scale"


# =============================================================================
# Edge / failure cases
# =============================================================================


def test_class_without_build_method(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class S(Spec):\n"
        "    pass\n"
        "class Bracket(Component):\n"
        "    spec = Param(S)\n"
    ))
    assert _build_reads(tmp_path, "Bracket") == ()


def test_class_without_params(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component\n"
        "class Bracket(Component):\n"
        "    def build(self):\n"
        "        return None\n"
    ))
    assert _build_reads(tmp_path, "Bracket") == ()


def test_self_attr_on_non_param_skipped(tmp_path: Path) -> None:
    # ``self.cache.size`` where ``cache`` isn't a Param — drop.
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "class Bracket(Component):\n"
        "    width = Param(float)\n"
        "    def build(self):\n"
        "        self.cache = {}\n"
        "        return self.cache.size\n"
    ))
    assert _build_reads(tmp_path, "Bracket") == ()


def test_async_build_method_walked(tmp_path: Path) -> None:
    # Async build is unusual but the walker handles it.
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class S(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(S)\n"
        "    async def build(self):\n"
        "        return self.spec.outer_d\n"
    ))
    [r] = _build_reads(tmp_path, "Cam")
    assert r.attr == "outer_d"


# =============================================================================
# Helper-method scope (self.x.y outside the build method)
# =============================================================================


def test_self_attr_attr_read_inside_helper_method(tmp_path: Path) -> None:
    """``self.spec.outer_d`` inside a helper method (not ``build``)
    should still surface as an AttributeRead — the extractor scopes
    to any method on the class.
    """
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        "    def build(self):\n"
        "        return self._cap()\n"
        "    def _cap(self):\n"
        "        return self.spec.outer_d\n"
    ))
    [r] = _build_reads(tmp_path, "Cam")
    assert r.base_name == "spec"
    assert r.attr == "outer_d"
    assert r.target is not None
    assert r.target.name == "CamSpec"


def test_self_attr_attr_read_inside_property(tmp_path: Path) -> None:
    """``self.spec.outer_d`` inside a property body — should surface."""
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        "    @property\n"
        "    def thk(self):\n"
        "        return self.spec.outer_d\n"
        "    def build(self):\n"
        "        return None\n"
    ))
    [r] = _build_reads(tmp_path, "Cam")
    assert r.attr == "outer_d"


# =============================================================================
# Multi-hop chains: self.a.b.attr resolves through declared Param types
# =============================================================================


def test_two_hop_self_chain_resolves_to_deepest_class(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class Inner(Spec):\n"
        "    pass\n"
        "class Mid(Spec):\n"
        "    inner = Param(Inner)\n"
        "class Outer(Component):\n"
        "    mid = Param(Mid)\n"
        "    def build(self):\n"
        "        return self.mid.inner.depth\n"
    ))
    reads = _build_reads(tmp_path, "Outer")
    by = {(r.attr): r.target.name for r in reads}
    # self.mid.inner -> reads `inner` off Mid; self.mid.inner.depth ->
    # reads `depth` off Inner.
    assert by["inner"] == "Mid"
    assert by["depth"] == "Inner"


