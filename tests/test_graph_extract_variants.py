"""Tests for the variant + Design class-attribute extractors.

Covers @variant decorator detection, class-level Component
instantiation discovery on Designs, and per-variant build-target
walking.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.graph.extract import (
    VariantInfo,
    extract_class_attr_components,
    extract_variants,
)
from scadwright.graph.registry import build_class_registry
from scadwright.graph.walk import walk_project


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


def _attrs(tmp_path: Path, class_name: str) -> dict[str, str]:
    cls, file_info, registry = _setup(tmp_path, class_name)
    raw = extract_class_attr_components(
        cls, file_info, registry, tmp_path,
    )
    return {name: target.name for name, target in raw.items()}


def _variants(tmp_path: Path, class_name: str) -> tuple[VariantInfo, ...]:
    cls, file_info, registry = _setup(tmp_path, class_name)
    return extract_variants(cls, file_info, registry, tmp_path)


# =============================================================================
# Design class-level Component attribute extraction
# =============================================================================


def test_class_attr_component_instance(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "from scadwright.design import Design\n"
        "class Holder(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    holder = Holder()\n"
    ))
    assert _attrs(tmp_path, "Box") == {"holder": "Holder"}


def test_class_attr_skips_non_components(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component, Spec\n"
        "from scadwright.design import Design\n"
        "class S(Spec):\n"
        "    pass\n"
        "class C(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    spec = S()\n"
        "    comp = C()\n"
        "    flag = True\n"
        "    n = int(5)\n"
    ))
    # Only the Component instantiation surfaces. The Spec
    # instantiation is skipped (we don't model 'design holds a
    # Spec instance' as a Component dependency); ``True`` and
    # ``int(5)`` aren't even Calls / aren't project classes.
    assert _attrs(tmp_path, "Box") == {"comp": "C"}


def test_class_attr_annotated_form(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "from scadwright.design import Design\n"
        "class C(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    comp: C = C()\n"
    ))
    assert _attrs(tmp_path, "Box") == {"comp": "C"}


def test_class_attr_empty_design(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright.design import Design\n"
        "class Box(Design):\n"
        "    pass\n"
    ))
    assert _attrs(tmp_path, "Box") == {}


# =============================================================================
# @variant decorator detection
# =============================================================================


def test_variant_method_with_decorator(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import variant, Component\n"
        "from scadwright.design import Design\n"
        "class C(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    comp = C()\n"
        "    @variant(default=True)\n"
        "    def show(self):\n"
        "        return self.comp\n"
    ))
    [v] = _variants(tmp_path, "Box")
    assert v.method_name == "show"
    assert v.default is True


def test_variant_default_keyword_optional(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import variant, Component\n"
        "from scadwright.design import Design\n"
        "class C(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    comp = C()\n"
        "    @variant(fn=64)\n"
        "    def show(self):\n"
        "        return self.comp\n"
    ))
    [v] = _variants(tmp_path, "Box")
    assert v.default is False


def test_undecorated_methods_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import variant, Component\n"
        "from scadwright.design import Design\n"
        "class C(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    comp = C()\n"
        "    @variant()\n"
        "    def show(self):\n"
        "        return self.comp\n"
        "    def helper(self):\n"
        "        return None\n"
    ))
    names = [v.method_name for v in _variants(tmp_path, "Box")]
    assert names == ["show"]


def test_non_variant_decorator_ignored(tmp_path: Path) -> None:
    # A method decorated with something else — say @staticmethod or
    # an unrelated decorator — must not surface as a variant.
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "from scadwright.design import Design\n"
        "class C(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    comp = C()\n"
        "    @staticmethod\n"
        "    def helper():\n"
        "        return None\n"
    ))
    assert _variants(tmp_path, "Box") == ()


def test_variant_imported_from_scadwright_design(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "from scadwright.design import Design, variant\n"
        "class C(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    comp = C()\n"
        "    @variant()\n"
        "    def show(self):\n"
        "        return self.comp\n"
    ))
    [v] = _variants(tmp_path, "Box")
    assert v.method_name == "show"


def test_variant_attribute_style_decorator(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "import scadwright\n"
        "from scadwright import Component\n"
        "from scadwright.design import Design\n"
        "class C(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    comp = C()\n"
        "    @scadwright.variant()\n"
        "    def show(self):\n"
        "        return self.comp\n"
    ))
    [v] = _variants(tmp_path, "Box")
    assert v.method_name == "show"


# =============================================================================
# Variant build target resolution
# =============================================================================


def test_variant_builds_via_self_class_attr(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import variant, Component\n"
        "from scadwright.design import Design\n"
        "class Holder(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    holder = Holder()\n"
        "    @variant()\n"
        "    def show(self):\n"
        "        return self.holder\n"
    ))
    [v] = _variants(tmp_path, "Box")
    [target] = v.builds
    assert target.name == "Holder"


def test_variant_builds_via_direct_call(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import variant, Component\n"
        "from scadwright.design import Design\n"
        "class Inner(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    @variant()\n"
        "    def show(self):\n"
        "        return Inner()\n"
    ))
    [v] = _variants(tmp_path, "Box")
    [target] = v.builds
    assert target.name == "Inner"


def test_variant_multiple_targets_via_union(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import variant, Component\n"
        "from scadwright.design import Design\n"
        "from scadwright.boolops import union\n"
        "class A(Component):\n"
        "    pass\n"
        "class B(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    a = A()\n"
        "    b = B()\n"
        "    @variant()\n"
        "    def show(self):\n"
        "        return union(self.a, self.b)\n"
    ))
    [v] = _variants(tmp_path, "Box")
    names = [t.name for t in v.builds]
    assert names == ["A", "B"]


def test_variant_targets_deduplicated(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import variant, Component\n"
        "from scadwright.design import Design\n"
        "from scadwright.boolops import union\n"
        "class A(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    a = A()\n"
        "    @variant()\n"
        "    def show(self):\n"
        "        return union(self.a, A())\n"
    ))
    [v] = _variants(tmp_path, "Box")
    assert len(v.builds) == 1
    assert v.builds[0].name == "A"


def test_variant_self_attr_unrelated_to_components(tmp_path: Path) -> None:
    # ``self.x`` where ``x`` isn't a Design class-level Component
    # produces no target — common for scratch local-variable use.
    _write(tmp_path, "main.py", (
        "from scadwright import variant, Component\n"
        "from scadwright.design import Design\n"
        "class C(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    comp = C()\n"
        "    @variant()\n"
        "    def show(self):\n"
        "        return self.comp.something()\n"
    ))
    [v] = _variants(tmp_path, "Box")
    [target] = v.builds
    assert target.name == "C"


def test_extract_variants_only_on_designs(tmp_path: Path) -> None:
    # Components and Specs aren't expected to host @variant methods;
    # the extractor returns ``()`` for those categories regardless.
    _write(tmp_path, "main.py", (
        "from scadwright import Component\n"
        "class C(Component):\n"
        "    pass\n"
    ))
    assert _variants(tmp_path, "C") == ()


def test_variants_preserve_source_order(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", (
        "from scadwright import variant, Component\n"
        "from scadwright.design import Design\n"
        "class C(Component):\n"
        "    pass\n"
        "class Box(Design):\n"
        "    c = C()\n"
        "    @variant()\n"
        "    def alpha(self): return self.c\n"
        "    @variant()\n"
        "    def beta(self): return self.c\n"
        "    @variant()\n"
        "    def gamma(self): return self.c\n"
    ))
    names = [v.method_name for v in _variants(tmp_path, "Box")]
    assert names == ["alpha", "beta", "gamma"]


def test_variant_info_immutable() -> None:
    v = VariantInfo(method_name="x", default=False, builds=())
    try:
        v.method_name = "y"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("VariantInfo should be frozen")
