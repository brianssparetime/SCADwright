"""Tests for emit-time scad_use and scad_include kwargs."""

from pathlib import Path

from scadwright import emit_str, render
from scadwright.primitives import cube


def _non_comment_lines(s: str) -> list[str]:
    """Strip the generated-file banner (leading // comments + the blank
    line that separates it from the body) so tests can anchor on real
    content."""
    lines = s.splitlines()
    started = False
    out = []
    for ln in lines:
        if not started:
            if ln.startswith("//") or ln == "":
                continue
            started = True
        out.append(ln)
    return out


def test_scad_use_prepends_use_line():
    out = emit_str(cube(5), scad_use=["utils.scad"])
    lines = _non_comment_lines(out)
    assert lines[0] == "use <utils.scad>"
    assert "cube" in out


def test_scad_include_prepends_include_line():
    out = emit_str(cube(5), scad_include=["base.scad"])
    lines = _non_comment_lines(out)
    assert lines[0] == "include <base.scad>"
    assert "cube" in out


def test_use_before_include_and_preserve_order():
    out = emit_str(
        cube(5),
        scad_use=["u1.scad", "u2.scad"],
        scad_include=["i1.scad", "i2.scad"],
    )
    lines = _non_comment_lines(out)
    assert lines[0] == "use <u1.scad>"
    assert lines[1] == "use <u2.scad>"
    assert lines[2] == "include <i1.scad>"
    assert lines[3] == "include <i2.scad>"


def test_empty_lists_emit_no_preamble():
    out = emit_str(cube(5), scad_use=[], scad_include=[])
    lines = _non_comment_lines(out)
    assert not lines[0].startswith("use")
    assert not lines[0].startswith("include")


def test_none_emits_no_preamble():
    out = emit_str(cube(5))
    lines = _non_comment_lines(out)
    assert not lines[0].startswith("use")
    assert not lines[0].startswith("include")


def test_render_forwards_scad_use(tmp_path: Path):
    out_path = tmp_path / "m.scad"
    render(cube(5), out_path, scad_use=["lib.scad"])
    contents = out_path.read_text()
    assert "use <lib.scad>" in contents


def test_render_forwards_scad_include(tmp_path: Path):
    out_path = tmp_path / "m.scad"
    render(cube(5), out_path, scad_include=["common.scad"])
    contents = out_path.read_text()
    assert "include <common.scad>" in contents
