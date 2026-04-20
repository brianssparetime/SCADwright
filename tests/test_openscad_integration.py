"""OpenSCAD round-trip validation. Opt-in via SCADWRIGHT_TEST_OPENSCAD=1 or -m integration."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).parent / "golden"


def _find_openscad() -> str | None:
    """Return path to openscad binary, or None if unavailable."""
    cmd = shutil.which("openscad")
    if cmd:
        return cmd
    # macOS .app fallback.
    mac_path = "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"
    if Path(mac_path).exists():
        return mac_path
    return None


@pytest.mark.integration
@pytest.mark.parametrize(
    "scad_path",
    sorted(GOLDEN_DIR.glob("*.scad")),
    ids=lambda p: p.stem,
)
def test_openscad_parses(scad_path: Path, tmp_path: Path):
    binary = _find_openscad()
    if binary is None:
        pytest.skip("openscad not on PATH")

    # --info parses without rendering geometry; faster than -o.
    result = subprocess.run(
        [binary, "--info", str(scad_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )

    # OpenSCAD's --info prints to stderr by design (version info, library paths,
    # font-config noise). We only flag SCAD-level errors/warnings, which use
    # uppercase "ERROR:" / "WARNING:" prefixes.
    err_lines = [
        line for line in result.stderr.splitlines()
        if line.startswith("ERROR:") or line.startswith("WARNING:")
    ]
    assert result.returncode == 0, (
        f"openscad failed for {scad_path.name}: rc={result.returncode}\n"
        f"stderr:\n{result.stderr}"
    )
    assert not err_lines, f"openscad warnings/errors for {scad_path.name}:\n" + "\n".join(err_lines)
