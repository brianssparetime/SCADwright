"""CLI tests for `scadwright morph`. The unit tests don't invoke OpenSCAD;
they exercise argument parsing, morph-name lookup, the .scad output path,
and error paths. Full integration with OpenSCAD is gated on the
SCADWRIGHT_TEST_OPENSCAD env var.
"""

from __future__ import annotations

import os
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

import pytest

from scadwright.animation._apng import _PNG_SIGNATURE


_DESIGN_SCRIPT = """\
from scadwright import Component, Param, morph, positive
from scadwright.boolops import union
from scadwright.design import Design, variant
from scadwright.primitives import cube


class _Box(Component):
    size: float = Param(default=10.0, validators=(positive,))

    def build(self):
        return cube(self.size)


class WidgetDesign(Design):
    box = _Box()

    @variant()
    def low(self):
        return self.box

    @variant(default=True)
    def high(self):
        return self.box.up(30)

    swing = morph(start='low', end='high')
"""


@pytest.fixture
def design_script(tmp_path):
    script = tmp_path / "widget.py"
    script.write_text(_DESIGN_SCRIPT)
    return script


def _run_cli(args: list[str]) -> tuple[int, str, str]:
    """Run scadwright CLI in a subprocess; return (exit, stdout, stderr)."""
    result = subprocess.run(
        [".venv/bin/scadwright"] + args,
        capture_output=True,
        text=True,
        cwd="/Users/bchoward/Projects/SCADwright",
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# .scad output (no OpenSCAD needed)
# ---------------------------------------------------------------------------


def test_morph_cli_writes_scad(design_script):
    out = design_script.parent / "out.scad"
    exit_code, _, stderr = _run_cli(["morph", str(design_script), "swing", str(out)])
    assert exit_code == 0, f"stderr: {stderr}"
    assert out.exists()
    text = out.read_text()
    assert "$t" in text


def test_morph_cli_unknown_morph_name_errors(design_script, tmp_path):
    exit_code, _, stderr = _run_cli([
        "morph", str(design_script), "nonexistent", str(tmp_path / "x.scad"),
    ])
    assert exit_code == 1
    assert "no morph named" in stderr
    assert "swing" in stderr  # lists available


def test_morph_cli_mp4_extension_gives_targeted_guidance(design_script, tmp_path):
    """`.mp4` gets specific guidance about ffmpeg and the two workarounds
    (APNG or PNG sequence + external ffmpeg)."""
    exit_code, _, stderr = _run_cli([
        "morph", str(design_script), "swing", str(tmp_path / "x.mp4"),
    ])
    assert exit_code == 1
    assert "ffmpeg" in stderr.lower()
    assert ".apng" in stderr
    assert "PNG sequence" in stderr or "png sequence" in stderr.lower()


def test_morph_cli_webm_extension_also_gets_video_guidance(design_script, tmp_path):
    exit_code, _, stderr = _run_cli([
        "morph", str(design_script), "swing", str(tmp_path / "x.webm"),
    ])
    assert exit_code == 1
    assert "ffmpeg" in stderr.lower()
    assert ".apng" in stderr


def test_morph_cli_gif_extension_recommends_apng(design_script, tmp_path):
    """`.gif` gets gif-specific guidance: APNG is preferred, but a PNG-
    sequence + ImageMagick workaround is mentioned for legacy needs."""
    exit_code, _, stderr = _run_cli([
        "morph", str(design_script), "swing", str(tmp_path / "x.gif"),
    ])
    assert exit_code == 1
    assert "APNG" in stderr or "apng" in stderr.lower()
    assert "gif" in stderr.lower()


def test_morph_cli_truly_unknown_extension_gives_generic_error(design_script, tmp_path):
    """An extension that isn't a known format at all (e.g. `.bogus`) still
    falls through to the generic 'unknown extension' message."""
    exit_code, _, stderr = _run_cli([
        "morph", str(design_script), "swing", str(tmp_path / "x.bogus"),
    ])
    assert exit_code == 1
    assert "unknown output extension" in stderr
    assert ".apng" in stderr  # lists supported


def test_morph_cli_invalid_imgsize_errors(design_script, tmp_path):
    exit_code, _, stderr = _run_cli([
        "morph", str(design_script), "swing", str(tmp_path / "x.scad"),
        "--imgsize", "bogus",
    ])
    assert exit_code == 1
    assert "imgsize" in stderr.lower()


def test_morph_cli_invalid_frames_errors(design_script, tmp_path):
    exit_code, _, stderr = _run_cli([
        "morph", str(design_script), "swing", str(tmp_path / "x.scad"),
        "--frames", "0",
    ])
    assert exit_code == 1
    assert "frames" in stderr.lower()


def test_morph_cli_no_design_in_script(tmp_path):
    script = tmp_path / "empty.py"
    script.write_text("# nothing here\n")
    exit_code, _, stderr = _run_cli([
        "morph", str(script), "anything", str(tmp_path / "x.scad"),
    ])
    assert exit_code == 1
    assert "no Design" in stderr or "no morph" in stderr


# ---------------------------------------------------------------------------
# Argument parsing helpers
# ---------------------------------------------------------------------------


def test_parse_imgsize_with_x():
    from scadwright.cli import _parse_imgsize
    assert _parse_imgsize("1920x1080") == (1920, 1080)


def test_parse_imgsize_with_comma():
    from scadwright.cli import _parse_imgsize
    assert _parse_imgsize("800,600") == (800, 600)


def test_parse_imgsize_invalid_raises():
    from scadwright.cli import _parse_imgsize
    from scadwright.errors import SCADwrightError
    with pytest.raises(SCADwrightError, match="imgsize"):
        _parse_imgsize("bogus")


def test_parse_imgsize_negative_raises():
    from scadwright.cli import _parse_imgsize
    from scadwright.errors import SCADwrightError
    with pytest.raises(SCADwrightError, match="positive"):
        _parse_imgsize("-100x100")


# ---------------------------------------------------------------------------
# Integration: full pipeline (needs OpenSCAD)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("SCADWRIGHT_TEST_OPENSCAD"),
    reason="requires SCADWRIGHT_TEST_OPENSCAD=1 and OpenSCAD on PATH",
)
def test_morph_cli_writes_apng_end_to_end(design_script):
    out = design_script.parent / "out.apng"
    exit_code, _, stderr = _run_cli([
        "morph", str(design_script), "swing", str(out),
        "--frames", "5",
        "--imgsize", "120x90",
    ])
    assert exit_code == 0, f"stderr: {stderr}"
    assert out.exists()
    # Re-parse: should have 5 fcTL chunks.
    from scadwright.animation._apng import _parse_png  # noqa
    data = out.read_bytes()
    assert data[: len(_PNG_SIGNATURE)] == _PNG_SIGNATURE
    # Count fcTL chunks.
    pos = len(_PNG_SIGNATURE)
    n_fctl = 0
    while pos < len(data):
        length, ctype = struct.unpack(">I4s", data[pos : pos + 8])
        pos += 8 + length + 4
        if ctype == b"fcTL":
            n_fctl += 1
        if ctype == b"IEND":
            break
    assert n_fctl == 5


@pytest.mark.skipif(
    not os.environ.get("SCADWRIGHT_TEST_OPENSCAD"),
    reason="requires SCADWRIGHT_TEST_OPENSCAD=1 and OpenSCAD on PATH",
)
def test_morph_cli_writes_png_sequence_end_to_end(design_script):
    out = design_script.parent / "frame.png"
    exit_code, _, stderr = _run_cli([
        "morph", str(design_script), "swing", str(out),
        "--frames", "3",
        "--imgsize", "120x90",
    ])
    assert exit_code == 0, f"stderr: {stderr}"
    frames = sorted(design_script.parent.glob("frame_*.png"))
    assert len(frames) == 3
