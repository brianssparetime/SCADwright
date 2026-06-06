"""Tests for the JSON project-map renderer.

JSON mirrors the ASCII vocabulary and grouping, but full (every read
field listed) and single-source forward (no reverse keys). These build
small projects end-to-end and assert on the parsed payload.
"""

from __future__ import annotations

import json
from pathlib import Path

from scadwright.graph.build import build_graph
from scadwright.graph.render_json import render_json


def _write(root: Path, name: str, src: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(src)


def _payload(root: Path) -> dict:
    return json.loads(render_json(build_graph(root)))


def test_top_level_keys_always_present(tmp_path: Path) -> None:
    p = _payload(tmp_path)
    assert set(p) >= {"project", "designs", "components", "specs",
                      "transforms"}
    assert p["components"] == {}
    assert p["specs"] == {}


def test_component_uses_spec_full_fields(tmp_path: Path) -> None:
    _write(tmp_path, "main.py",
           "from scadwright import Component, Spec, Param\n"
           "class CellSpec(Spec):\n"
           "    equations = 'cells = 4'\n"
           "class Holder(Component):\n"
           "    spec = Param(CellSpec)\n"
           "    equations = 'wall = spec.cells * 2'\n")
    p = _payload(tmp_path)
    holder = p["components"]["Holder"]
    assert holder["uses_spec"] == [
        {"spec": "CellSpec", "via_param": "spec", "reads": ["cells"]}
    ]
    # Specs are single-source: no reverse read_by stored.
    assert "read_by" not in p["specs"]["CellSpec"]


def test_components_are_forward_single_source(tmp_path: Path) -> None:
    _write(tmp_path, "main.py",
           "from scadwright import Component\n"
           "class Base(Component):\n"
           "    pass\n"
           "class Concrete(Base):\n"
           "    pass\n")
    p = _payload(tmp_path)
    assert p["components"]["Concrete"]["based_on"] == ["Base"]
    # The reverse (specialized_by) is derivable, not stored.
    assert "specialized_by" not in p["components"]["Base"]


def test_design_variants_and_morph_stages(tmp_path: Path) -> None:
    _write(tmp_path, "main.py",
           "from scadwright import Component, morph\n"
           "from scadwright.design import Design, variant\n"
           "class Part(Component):\n"
           "    pass\n"
           "class M(Design):\n"
           "    part = Part()\n"
           "    @variant(default=True)\n"
           "    def a(self):\n"
           "        return self.part\n"
           "    @variant()\n"
           "    def b(self):\n"
           "        return self.part\n"
           "    anim = morph(stages=['a', 'b'])\n")
    p = _payload(tmp_path)
    design = p["designs"]["M"]
    assert design["variants"]["a"] == {"default": True, "builds": ["Part"]}
    assert design["variants"]["b"] == {"builds": ["Part"]}
    assert design["morphs"]["anim"] == {
        "builds": ["Part"], "stages": ["a", "b"],
    }
    # built_by is reverse, not stored on the component.
    assert "built_by" not in p["components"]["Part"]


def test_transform_section(tmp_path: Path) -> None:
    _write(tmp_path, "main.py",
           "from scadwright.transforms import transform\n"
           "from scadwright import Component\n"
           "@transform('foo')\n"
           "def foo(node):\n"
           "    return node\n"
           "class C(Component):\n"
           "    def build(self):\n"
           "        return (None).foo()\n")
    p = _payload(tmp_path)
    assert "foo" in p["transforms"]
    assert p["components"]["C"]["uses_transform"] == ["foo"]


def test_round_trips_as_valid_json(tmp_path: Path) -> None:
    _write(tmp_path, "main.py",
           "from scadwright import Component\n"
           "class A(Component):\n"
           "    pass\n")
    text = render_json(build_graph(tmp_path))
    assert text.endswith("\n")
    json.loads(text)  # no exception
