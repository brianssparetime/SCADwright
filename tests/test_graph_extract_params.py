"""Tests for the graph Param extractor.

Covers textual extraction (name, type, default, doc, extras),
resolved-type lookup against the project class registry
(primitive types yielding None, project-local types resolving to
ResolvedClass), AnnAssign form, classes with no Params, and
Params whose type names an external/unresolvable class.
"""

from __future__ import annotations

from pathlib import Path

from scadwright.graph.extract import ParamRef, extract_params
from scadwright.project_index.registry import build_class_registry
from scadwright.project_index.walk import walk_project


def _project(tmp_path: Path):
    files = walk_project(tmp_path)
    registry = build_class_registry(files, tmp_path)
    return files, registry


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _params_of(tmp_path: Path, class_name: str) -> tuple[ParamRef, ...]:
    files, registry = _project(tmp_path)
    cls = next(
        c for c in registry.classes.values() if c.name == class_name
    )
    file_info = next(f for f in files if f.path == cls.file_path)
    return extract_params(cls, file_info, registry, tmp_path)


# =============================================================================
# Textual fields
# =============================================================================


def test_extract_param_with_primitive_type(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "class Bracket(Component):\n"
        "    width = Param(float)\n"
    ))
    [p] = _params_of(tmp_path, "Bracket")
    assert p.name == "width"
    assert p.type_text == "float"
    assert p.default_text is None
    assert p.doc_text is None
    assert p.extras == ()
    assert p.type_resolves_to is None


def test_extract_param_with_default(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "class Bracket(Component):\n"
        "    width = Param(float, default=5)\n"
    ))
    [p] = _params_of(tmp_path, "Bracket")
    assert p.default_text == "5"


def test_extract_param_with_doc(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "class Bracket(Component):\n"
        '    width = Param(float, doc="The widget width")\n'
    ))
    [p] = _params_of(tmp_path, "Bracket")
    assert p.doc_text == "The widget width"


def test_extract_param_with_extras(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "class Bracket(Component):\n"
        "    width = Param(float, positive=True, range=(0, 10))\n"
    ))
    [p] = _params_of(tmp_path, "Bracket")
    extras = dict(p.extras)
    assert extras == {"positive": "True", "range": "(0, 10)"}


def test_extract_param_no_positional_no_type(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "class Bracket(Component):\n"
        "    width = Param(default=5)\n"
    ))
    [p] = _params_of(tmp_path, "Bracket")
    assert p.type_text is None
    assert p.type_resolves_to is None


# =============================================================================
# Type resolution
# =============================================================================


def test_param_type_resolves_to_same_file_spec(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Spec, Param\n"
        "class BatterySpec(Spec):\n"
        "    pass\n"
        "class Holder(Component):\n"
        "    spec = Param(BatterySpec)\n"
    ))
    [p] = _params_of(tmp_path, "Holder")
    assert p.type_text == "BatterySpec"
    assert p.type_resolves_to is not None
    assert p.type_resolves_to.name == "BatterySpec"
    assert p.type_resolves_to.category == "spec"


def test_param_type_resolves_cross_file(tmp_path: Path) -> None:
    _write(tmp_path, "specs.py", (
        "from scadwright import Spec\n"
        "class BatterySpec(Spec):\n"
        "    pass\n"
    ))
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "from specs import BatterySpec\n"
        "class Holder(Component):\n"
        "    spec = Param(BatterySpec)\n"
    ))
    [p] = _params_of(tmp_path, "Holder")
    assert p.type_resolves_to is not None
    assert p.type_resolves_to.name == "BatterySpec"
    assert p.type_resolves_to.module_path == "specs"


def test_param_type_resolves_to_component(tmp_path: Path) -> None:
    # Param can also reference another Component (e.g., a subassembly
    # instance). The graph still wants the resolved class.
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "class Inner(Component):\n"
        "    pass\n"
        "class Outer(Component):\n"
        "    inner = Param(Inner)\n"
    ))
    [p] = _params_of(tmp_path, "Outer")
    assert p.type_resolves_to is not None
    assert p.type_resolves_to.name == "Inner"
    assert p.type_resolves_to.category == "component"


def test_param_type_unresolvable_yields_none(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "from collections import OrderedDict\n"
        "class Bracket(Component):\n"
        "    data = Param(OrderedDict)\n"
    ))
    [p] = _params_of(tmp_path, "Bracket")
    assert p.type_text == "OrderedDict"
    assert p.type_resolves_to is None


def test_param_type_dotted_resolves(tmp_path: Path) -> None:
    _write(tmp_path, "specs.py", (
        "from scadwright import Spec\n"
        "class BatterySpec(Spec):\n"
        "    pass\n"
    ))
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "import specs\n"
        "class Holder(Component):\n"
        "    spec = Param(specs.BatterySpec)\n"
    ))
    [p] = _params_of(tmp_path, "Holder")
    assert p.type_text == "specs.BatterySpec"
    assert p.type_resolves_to is not None
    assert p.type_resolves_to.name == "BatterySpec"


# =============================================================================
# Form variations
# =============================================================================


def test_extract_param_ann_assign_form(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "class Bracket(Component):\n"
        "    width: float = Param(float, default=5)\n"
    ))
    [p] = _params_of(tmp_path, "Bracket")
    assert p.name == "width"
    assert p.type_text == "float"
    assert p.default_text == "5"


def test_extract_multiple_params_in_source_order(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "class Bracket(Component):\n"
        "    width = Param(float)\n"
        "    height = Param(float)\n"
        "    depth = Param(float)\n"
    ))
    params = _params_of(tmp_path, "Bracket")
    assert [p.name for p in params] == ["width", "height", "depth"]


def test_extract_no_params(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component\n"
        "class Empty(Component):\n"
        "    pass\n"
    ))
    params = _params_of(tmp_path, "Empty")
    assert params == ()


def test_non_param_assignments_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "widget.py", (
        "from scadwright import Component, Param\n"
        "class Bracket(Component):\n"
        "    width = Param(float)\n"
        "    debug = True\n"
        "    name = 'thing'\n"
    ))
    params = _params_of(tmp_path, "Bracket")
    assert [p.name for p in params] == ["width"]
