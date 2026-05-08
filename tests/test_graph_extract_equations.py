"""Tests for the graph equations attribute-read extractor.

Covers reads on Param-typed bases that resolve to project classes
(Spec and Component), reads on primitive-typed Params, dedupe of
repeated reads, parses-error tolerance, equations-less classes,
and the constraint and adjustment walking paths.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.graph.extract import (
    AttributeRead,
    extract_equations_attribute_reads,
    extract_params,
)
from scadwright.graph.registry import build_class_registry
from scadwright.graph.walk import walk_project


def _setup(tmp_path: Path, class_name: str):
    files = walk_project(tmp_path)
    registry = build_class_registry(files, tmp_path)
    cls = next(c for c in registry.classes.values() if c.name == class_name)
    file_info = next(f for f in files if f.path == cls.file_path)
    params = extract_params(cls, file_info, registry, tmp_path)
    return cls, file_info, params


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _reads(tmp_path: Path, class_name: str) -> tuple[AttributeRead, ...]:
    cls, file_info, params = _setup(tmp_path, class_name)
    return extract_equations_attribute_reads(cls, file_info, params)


# =============================================================================
# Param-typed base resolves to a Spec
# =============================================================================


def test_attribute_read_on_spec_typed_param(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class BatterySpec(Spec):\n"
        "    pass\n"
        "class Holder(Component):\n"
        "    spec = Param(BatterySpec)\n"
        '    equations = "x = spec.outer_d"\n'
    ))
    [r] = _reads(tmp_path, "Holder")
    assert r.base_name == "spec"
    assert r.attr == "outer_d"
    assert r.target is not None
    assert r.target.name == "BatterySpec"
    assert r.target.category == "spec"


def test_attribute_read_on_component_typed_param(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "class Inner(Component):\n"
        "    pass\n"
        "class Outer(Component):\n"
        "    inner = Param(Inner)\n"
        '    equations = "x = inner.width"\n'
    ))
    [r] = _reads(tmp_path, "Outer")
    assert r.target is not None
    assert r.target.category == "component"


def test_multiple_attribute_reads_on_same_param(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        '    equations = """\n'
        "    x = spec.outer_d\n"
        "    y = spec.height\n"
        '    """\n'
    ))
    reads = _reads(tmp_path, "Cam")
    attrs = sorted(r.attr for r in reads)
    assert attrs == ["height", "outer_d"]


def test_repeated_read_deduplicated(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        '    equations = """\n'
        "    x = spec.outer_d + spec.outer_d\n"
        "    y = spec.outer_d * 2\n"
        '    """\n'
    ))
    reads = _reads(tmp_path, "Cam")
    # Three textual occurrences of ``spec.outer_d`` collapse to one.
    assert len(reads) == 1
    assert reads[0].attr == "outer_d"


# =============================================================================
# Primitive-typed Param: read kept, target=None
# =============================================================================


def test_attribute_read_on_primitive_param_target_none(tmp_path: Path) -> None:
    # Reads on a float-typed Param are unusual but the extractor
    # surfaces them with target=None for the builder to interpret.
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "class Bracket(Component):\n"
        "    width = Param(float)\n"
        '    equations = "x = width.real"\n'
    ))
    [r] = _reads(tmp_path, "Bracket")
    assert r.base_name == "width"
    assert r.attr == "real"
    assert r.target is None


# =============================================================================
# Filtering
# =============================================================================


def test_attribute_read_on_non_param_base_skipped(tmp_path: Path) -> None:
    # ``other.attr`` where ``other`` isn't a Param is dropped — the
    # LSP's undeclared-attribute warning surfaces those separately.
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "class Bracket(Component):\n"
        "    width = Param(float)\n"
        '    equations = "x = width + other.attr"\n'
    ))
    reads = _reads(tmp_path, "Bracket")
    assert reads == ()


# =============================================================================
# Constraint and adjustment paths
# =============================================================================


def test_attribute_read_in_constraint(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        '    equations = """\n'
        "    spec.outer_d > 0\n"
        '    """\n'
    ))
    [r] = _reads(tmp_path, "Cam")
    assert r.attr == "outer_d"


def test_attribute_read_in_adjustment_rhs(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class CamSpec(Spec):\n"
        "    pass\n"
        "class Cam(Component):\n"
        "    spec = Param(CamSpec)\n"
        "    width = Param(float)\n"
        '    equations = """\n'
        "    width += spec.delta  # adjust\n"
        '    """\n'
    ))
    [r] = _reads(tmp_path, "Cam")
    assert r.base_name == "spec"
    assert r.attr == "delta"


# =============================================================================
# Edge / failure cases
# =============================================================================


def test_class_without_equations(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "class Bracket(Component):\n"
        "    width = Param(float)\n"
    ))
    assert _reads(tmp_path, "Bracket") == ()


def test_class_without_params(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component\n"
        "class Bracket(Component):\n"
        '    equations = "x = 1"\n'
    ))
    assert _reads(tmp_path, "Bracket") == ()


def test_invalid_equations_yields_empty(tmp_path: Path) -> None:
    # ``snh`` is a typo — parse_equations_unified raises. Extractor
    # returns empty rather than propagating.
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class S(Spec):\n"
        "    pass\n"
        "class Bracket(Component):\n"
        "    spec = Param(S)\n"
        '    equations = "x = snh(spec.attr)"\n'
    ))
    assert _reads(tmp_path, "Bracket") == ()


def test_attribute_read_immutable() -> None:
    r = AttributeRead(base_name="b", attr="x", target=None)
    try:
        r.attr = "y"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("AttributeRead should be frozen")
