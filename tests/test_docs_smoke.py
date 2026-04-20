"""Docs-maintenance smoke tests (MajorReview2 Group 9).

CLAUDE.md commits `README.md`, `docs/cheatsheet.md`, and
`docs/coming_from_openscad.md` to stay in sync with the public API. These
tests enforce it: extract ```python fenced blocks and exec them.

Some blocks in coming_from_openscad.md are intentionally illustrative and
reference user-provided names (`my_part`, `Widget`, `plate`). Those get an
allowlist-based NameError pass. Everything else must run cleanly.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


_FENCE = re.compile(r"^```python\n(.*?)^```", re.MULTILINE | re.DOTALL)


def _python_blocks(path: Path) -> list[tuple[int, str]]:
    """Return [(start_line, code), ...] for every ```python fenced block."""
    text = path.read_text()
    blocks = []
    for match in _FENCE.finditer(text):
        start_line = text[: match.start()].count("\n") + 2  # first line of code
        blocks.append((start_line, match.group(1)))
    return blocks


_PRELUDE = """\
from scadwright import (
    Component, Param, bbox, tree_hash, render, resolution,
    current_variant, variant, register_variants, Matrix,
    positive, non_negative, minimum, maximum, in_range, one_of,
)
from scadwright.primitives import (
    cube, sphere, cylinder, polyhedron, square, circle, polygon,
    text, surface, scad_import,
)
from scadwright.boolops import union, difference, intersection, hull, minkowski
from scadwright.extrusions import linear_extrude, rotate_extrude
from scadwright.transforms import transform
from scadwright.composition_helpers import (
    linear_copy, rotate_copy, mirror_copy, multi_hull, sequential_hull,
)
from scadwright.errors import ValidationError, BuildError
from scadwright.asserts import assert_fits_in
from scadwright import math as scmath
import math
import random
"""


def _fresh_namespace() -> dict:
    """A namespace pre-seeded with the prelude imports."""
    ns: dict = {"__name__": "_docs_smoke"}
    exec(_PRELUDE, ns)
    return ns


# Names that appear in illustrative coming_from_openscad snippets and are
# deliberately undefined in the doc context (placeholders for user code).
_ILLUSTRATIVE_NAMES = frozenset({
    # Shape/part placeholders
    "my_complicated_thing", "my_part", "my_shape", "complex_part",
    "body", "bracket", "plate", "peg", "widget", "Widget", "W", "part",
    "supports", "_supports", "shape", "hole",
    # Generic variable placeholders (used in snippet contexts)
    "a", "b", "c", "x", "y", "z", "n",
    "self",  # method-body fragments
    # Values / inputs illustrated but not defined
    "d", "large", "size", "min_v", "max_v", "count",
    # User-named helper functions in illustrative snippets
    "compute_expensive_points", "hex_grid_points",
})


# --- 9a: cheatsheet imports block ---


def test_cheatsheet_imports_block_is_valid():
    blocks = _python_blocks(DOCS / "cheatsheet.md")
    assert blocks, "cheatsheet.md has no python code blocks"
    start_line, code = blocks[0]
    ns: dict = {"__name__": "_cheatsheet_imports"}
    try:
        exec(code, ns)
    except Exception as exc:
        pytest.fail(
            f"cheatsheet.md imports block (line {start_line}) failed: "
            f"{type(exc).__name__}: {exc}"
        )


# --- 9b: README quick-example runs ---


def _find_section_block(path: Path, heading: str) -> tuple[int, str]:
    """Return the first python fenced block appearing after a markdown heading."""
    text = path.read_text()
    idx = text.find(heading)
    if idx < 0:
        pytest.fail(f"heading {heading!r} not found in {path.name}")
    after = text[idx:]
    match = _FENCE.search(after)
    if not match:
        pytest.fail(f"no python block after {heading!r} in {path.name}")
    start_line = text[: idx + match.start()].count("\n") + 2
    return start_line, match.group(1)


def test_readme_quick_example_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    start_line, code = _find_section_block(ROOT / "README.md", "## Quick example")
    ns: dict = {"__name__": "_readme_example"}
    try:
        exec(code, ns)
    except Exception as exc:
        pytest.fail(
            f"README Quick example (line {start_line}) failed: "
            f"{type(exc).__name__}: {exc}"
        )
    assert (tmp_path / "widget.scad").is_file(), (
        "README example should have written widget.scad to the current directory"
    )


# --- 9c: coming_from_openscad examples ---


def test_coming_from_openscad_blocks_run():
    path = DOCS / "coming_from_openscad.md"
    blocks = _python_blocks(path)
    assert blocks, "coming_from_openscad.md has no python code blocks"

    failures: list[tuple[int, str, str]] = []
    skipped: list[tuple[int, str]] = []

    for start_line, code in blocks:
        ns = _fresh_namespace()
        try:
            exec(code, ns)
        except NameError as exc:
            # Extract the unresolved name from the message.
            m = re.search(r"name '([^']+)' is not defined", str(exc))
            name = m.group(1) if m else "<unknown>"
            if name in _ILLUSTRATIVE_NAMES:
                skipped.append((start_line, name))
            else:
                failures.append((start_line, "NameError", f"{name!r} (not in allowlist)"))
        except Exception as exc:
            failures.append((start_line, type(exc).__name__, str(exc)))

    if failures:
        lines = [
            f"  line {ln}: {exc_type}: {detail}"
            for ln, exc_type, detail in failures
        ]
        pytest.fail(
            f"{len(failures)} block(s) in coming_from_openscad.md failed:\n"
            + "\n".join(lines)
        )
    # Sanity: if *every* block was skipped, the test is useless.
    assert len(skipped) < len(blocks), (
        f"all {len(blocks)} blocks were skipped as illustrative — tighten the allowlist"
    )
