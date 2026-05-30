"""Tests for the class-attribute reads extractor.

Covers direct ``ClassName.attr`` reads at class scope and inside
methods, dedupe across multiple reads, exclusion of ``self`` and
Param names so the dedicated extractors aren't double-counted,
non-project bases dropping silently, and the deeper-chain stop
behavior.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.graph.extract import (
    AttributeRead,
    extract_class_attribute_reads,
)
from scadwright.project_index.registry import build_class_registry
from scadwright.project_index.walk import walk_project


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _reads_for(
    tmp_path: Path, class_name: str, exclude=frozenset({"self"}),
) -> tuple[AttributeRead, ...]:
    files = walk_project(tmp_path)
    registry = build_class_registry(files, tmp_path)
    cls = next(c for c in registry.classes.values() if c.name == class_name)
    file_info = next(f for f in files if f.path == cls.file_path)
    return extract_class_attribute_reads(
        cls.ast_node, file_info, registry, tmp_path, exclude,
    )


# =============================================================================
# Class-scope direct reads
# =============================================================================


def test_spec_class_attribute_read_at_class_scope(tmp_path: Path) -> None:
    _write(tmp_path, "design.py", (
        "from scadwright import Component, Spec\n"
        "class Bayonet(Spec):\n"
        "    equations = '''\n"
        "        cam_barrel_od = 60.5\n"
        "    '''\n"
        "class Housing(Component):\n"
        "    outer_d = Bayonet.cam_barrel_od\n"
        "    def build(self):\n"
        "        return None\n"
    ))
    [r] = _reads_for(tmp_path, "Housing")
    assert r.base_name == "Bayonet"
    assert r.attr == "cam_barrel_od"
    assert r.target is not None
    assert r.target.name == "Bayonet"


def test_multiple_attrs_on_same_target_dedupe(tmp_path: Path) -> None:
    _write(tmp_path, "design.py", (
        "from scadwright import Component, Spec\n"
        "class Bayonet(Spec):\n"
        "    equations = '''\n"
        "        a = 1\n"
        "        b = 2\n"
        "    '''\n"
        "class Housing(Component):\n"
        "    one = Bayonet.a\n"
        "    two = Bayonet.b\n"
        "    one_dup = Bayonet.a\n"
        "    def build(self):\n"
        "        return None\n"
    ))
    reads = _reads_for(tmp_path, "Housing")
    attrs = sorted(r.attr for r in reads)
    assert attrs == ["a", "b"]
    for r in reads:
        assert r.target is not None
        assert r.target.name == "Bayonet"


def test_read_inside_method_body(tmp_path: Path) -> None:
    _write(tmp_path, "design.py", (
        "from scadwright import Component, Spec\n"
        "class Bayonet(Spec):\n"
        "    equations = '''\n"
        "        d = 5\n"
        "    '''\n"
        "class Housing(Component):\n"
        "    def build(self):\n"
        "        return Bayonet.d\n"
    ))
    [r] = _reads_for(tmp_path, "Housing")
    assert r.base_name == "Bayonet"
    assert r.attr == "d"


def test_read_inside_expression(tmp_path: Path) -> None:
    _write(tmp_path, "design.py", (
        "from scadwright import Component, Spec\n"
        "class Bayonet(Spec):\n"
        "    equations = '''\n"
        "        d = 5\n"
        "    '''\n"
        "class Housing(Component):\n"
        "    def build(self):\n"
        "        return (Bayonet.d * 2) + 1\n"
    ))
    [r] = _reads_for(tmp_path, "Housing")
    assert r.attr == "d"


# =============================================================================
# Cross-file resolution
# =============================================================================


def test_imported_spec_class_attribute_read(tmp_path: Path) -> None:
    _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class Bayonet(Spec):\n"
        "    equations = '''\n"
        "        cam_barrel_od = 60.5\n"
        "    '''\n"
    ))
    _write(tmp_path, "housing.py", (
        "from scadwright import Component\n"
        "from spec import Bayonet\n"
        "class Housing(Component):\n"
        "    outer_d = Bayonet.cam_barrel_od\n"
        "    def build(self):\n"
        "        return None\n"
    ))
    [r] = _reads_for(tmp_path, "Housing")
    assert r.target is not None
    assert r.target.name == "Bayonet"
    assert r.target.file_path.name == "spec.py"


def test_aliased_import(tmp_path: Path) -> None:
    _write(tmp_path, "spec.py", (
        "from scadwright import Spec\n"
        "class Bayonet(Spec):\n"
        "    equations = '''\n"
        "        d = 1\n"
        "    '''\n"
    ))
    _write(tmp_path, "housing.py", (
        "from scadwright import Component\n"
        "from spec import Bayonet as B\n"
        "class Housing(Component):\n"
        "    d = B.d\n"
        "    def build(self):\n"
        "        return None\n"
    ))
    [r] = _reads_for(tmp_path, "Housing")
    assert r.base_name == "B"
    assert r.target is not None
    assert r.target.name == "Bayonet"


# =============================================================================
# Exclusions
# =============================================================================


def test_self_reads_excluded_by_default(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component\n"
        "class Widget(Component):\n"
        "    equations = '''\n"
        "        w = 10\n"
        "    '''\n"
        "    def build(self):\n"
        "        return self.w\n"
    ))
    reads = _reads_for(tmp_path, "Widget")
    assert reads == ()


def test_param_names_can_be_excluded(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Widget(Component):\n"
        "    spec = Param(CamSpec)\n"
        "    def build(self):\n"
        "        return spec.outer_d\n"
    ))
    reads = _reads_for(
        tmp_path, "Widget", exclude=frozenset({"self", "spec"}),
    )
    assert reads == ()


# =============================================================================
# Non-project bases drop silently
# =============================================================================


def test_third_party_base_drops(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component\n"
        "import math\n"
        "class Widget(Component):\n"
        "    PI = math.pi\n"
        "    def build(self):\n"
        "        return None\n"
    ))
    reads = _reads_for(tmp_path, "Widget")
    assert reads == ()


def test_unresolved_name_drops(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component\n"
        "class Widget(Component):\n"
        "    def build(self):\n"
        "        return ghost.value\n"
    ))
    reads = _reads_for(tmp_path, "Widget")
    assert reads == ()


# =============================================================================
# Deeper chains stop at the first hop
# =============================================================================


def test_deeper_chain_records_first_hop_only(tmp_path: Path) -> None:
    _write(tmp_path, "design.py", (
        "from scadwright import Component, Spec\n"
        "class Bayonet(Spec):\n"
        "    equations = '''\n"
        "        d = 5\n"
        "    '''\n"
        "class Housing(Component):\n"
        "    def build(self):\n"
        "        return Bayonet.d.bit_length()\n"
    ))
    [r] = _reads_for(tmp_path, "Housing")
    assert r.attr == "d"
    # No second edge for `bit_length` — the inner attribute is the
    # only Name-rooted shape.


# =============================================================================
# Component / Design / Transform targets resolve uniformly
# =============================================================================


def test_component_class_attribute_read(tmp_path: Path) -> None:
    _write(tmp_path, "design.py", (
        "from scadwright import Component\n"
        "class Plate(Component):\n"
        "    equations = '''\n"
        "        thk = 3\n"
        "    '''\n"
        "    def build(self):\n"
        "        return None\n"
        "class Other(Component):\n"
        "    default_thk = Plate.thk\n"
        "    def build(self):\n"
        "        return None\n"
    ))
    [r] = _reads_for(tmp_path, "Other")
    assert r.target is not None
    assert r.target.name == "Plate"
    assert r.target.category == "component"
