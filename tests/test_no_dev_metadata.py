"""Source comments must not contain autobiographical dev-plan metadata.

The CLAUDE.md "No autobiographical dev-plan notes in source" convention
forbids leftover "Phase N", "slice N", and similar historical-roadmap
framing in code. This test enforces it.
"""

import re
from pathlib import Path

import pytest


SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "scadwright"


# Patterns that signal autobiographical dev-plan content.
# NOT matched: "Step 1"/"Step 2" (local algorithm labels, explicitly allowed).
_FORBIDDEN = [
    re.compile(r"\bPhase\s+\d", re.IGNORECASE),
    re.compile(r"\bslice\s+\d", re.IGNORECASE),
    re.compile(r"\blands\s+(?:in|alongside)\s+(?:Phase|slice|step)", re.IGNORECASE),
    re.compile(r"\bplanned\s+for\s+(?:Phase|slice|step)\s+\d", re.IGNORECASE),
]


def test_no_phase_or_slice_references_in_source():
    offenders: list[tuple[Path, int, str]] = []
    for path in SRC_ROOT.rglob("*.py"):
        # Skip __pycache__ and compiled files.
        if any(part == "__pycache__" for part in path.parts):
            continue
        lines = path.read_text().splitlines()
        for lineno, line in enumerate(lines, 1):
            for pattern in _FORBIDDEN:
                if pattern.search(line):
                    offenders.append((path, lineno, line.rstrip()))
                    break
    if offenders:
        lines = [
            f"  {p.relative_to(SRC_ROOT.parent.parent)}:{ln}: {snip}"
            for p, ln, snip in offenders
        ]
        pytest.fail(
            "Found dev-plan metadata in source (forbidden by CLAUDE.md):\n"
            + "\n".join(lines)
        )
