"""Golden-file tests: each tests/golden/*.py defines MODEL; compared to sibling .scad.

Set SCADWRIGHT_UPDATE_GOLDENS=1 to rewrite expected .scad files.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from scadwright import emit_str
GOLDEN_DIR = Path(__file__).parent / "golden"


def _discover_cases():
    if not GOLDEN_DIR.exists():
        return []
    return sorted(p for p in GOLDEN_DIR.glob("*.py") if not p.name.startswith("_"))


def _load_model(py_path: Path):
    spec = importlib.util.spec_from_file_location(f"golden_{py_path.stem}", py_path)
    assert spec and spec.loader, f"could not load {py_path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "MODEL"), f"{py_path.name} must define MODEL"
    return mod.MODEL


@pytest.mark.parametrize(
    "py_path", _discover_cases(), ids=lambda p: p.stem
)
def test_golden(py_path: Path):
    model = _load_model(py_path)
    actual = emit_str(model)
    scad_path = py_path.with_suffix(".scad")
    if os.environ.get("SCADWRIGHT_UPDATE_GOLDENS"):
        scad_path.write_text(actual)
        pytest.skip(f"updated {scad_path.name}")
    assert scad_path.exists(), f"missing golden {scad_path.name}; run with SCADWRIGHT_UPDATE_GOLDENS=1"
    expected = scad_path.read_text()
    assert actual == expected
