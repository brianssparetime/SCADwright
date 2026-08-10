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


# --- Winding, which only the preview renderer can see ---
#
# OpenCSG resolves booleans from front and back facing, so a backwards
# mesh is culled: it renders as nothing inside an intersection() and as
# a normal solid on its own. CGAL ignores winding, so no exact render,
# STL export, or text comparison detects this. Rendering a preview
# frame and checking that something is in it is the only way.


def _preview_is_blank(scad: Path, png: Path, binary: str) -> bool:
    """Render a preview frame and report whether anything drew.

    Compares against a frame of the same size containing nothing. An
    empty OpenCSG frame is a flat background, so it compresses to a
    markedly smaller PNG than one with a solid in it.
    """
    subprocess.run(
        [binary, "-o", str(png), "--imgsize=300,240",
         "--camera=0,0,0,55,0,25,90", str(scad)],
        capture_output=True, timeout=120,
    )
    blank = png.with_name("blank.png")
    empty_scad = scad.with_name("empty.scad")
    empty_scad.write_text("// nothing\n")
    subprocess.run(
        [binary, "-o", str(blank), "--imgsize=300,240",
         "--camera=0,0,0,55,0,25,90", str(empty_scad)],
        capture_output=True, timeout=120,
    )
    return png.stat().st_size <= blank.stat().st_size * 1.05


@pytest.mark.integration
def test_polyhedron_shape_survives_a_boolean_in_preview(tmp_path: Path):
    binary = _find_openscad()
    if binary is None:
        pytest.skip("openscad not on PATH")

    from scadwright import render
    from scadwright.boolops import intersection
    from scadwright.primitives import cube
    from scadwright.shapes import Prism

    scad = tmp_path / "winding.scad"
    render(intersection(cube([30, 30, 30], center="xy"), Prism(r=10, sides=6, h=5)), scad)

    assert not _preview_is_blank(scad, tmp_path / "winding.png", binary), (
        "the prism vanished from OpenCSG preview inside an intersection, "
        "which means its faces are wound the wrong way round"
    )


@pytest.mark.integration
def test_a_backwards_mesh_really_does_vanish(tmp_path: Path):
    # Pins the premise the test above rests on. If OpenSCAD ever stopped
    # culling backwards meshes, that test would pass for the wrong
    # reason and quietly stop guarding anything.
    binary = _find_openscad()
    if binary is None:
        pytest.skip("openscad not on PATH")

    from scadwright import render
    from scadwright.ast.primitives import Polyhedron
    from scadwright.boolops import intersection
    from scadwright.primitives import cube

    pts = [(10, 10, 0), (10, -10, 0), (-10, -10, 0), (-10, 10, 0), (0, 0, 10)]
    backwards = [(4, 1, 0), (4, 2, 1), (4, 3, 2), (4, 0, 3), (3, 0, 1), (3, 1, 2)]
    # Built directly: the factory would turn these round, which is the point.
    raw = Polyhedron(points=tuple(pts), faces=tuple(backwards))

    scad = tmp_path / "backwards.scad"
    render(intersection(cube([30, 30, 30], center="xy"), raw), scad)

    assert _preview_is_blank(scad, tmp_path / "backwards.png", binary), (
        "expected a backwards mesh to be culled by OpenCSG; if it no "
        "longer is, the winding regression test above proves nothing"
    )
