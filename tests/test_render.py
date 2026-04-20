from pathlib import Path

from scadwright import emit_str, render
from scadwright.primitives import cube
def test_render_writes_file(tmp_path: Path):
    model = cube([1, 2, 3])
    out = tmp_path / "out.scad"
    result = render(model, out)
    assert result == out
    contents = out.read_text()
    assert contents == emit_str(model)


def test_render_debug_includes_source(tmp_path: Path):
    model = cube(1)
    out = tmp_path / "out.scad"
    render(model, out, debug=True)
    text = out.read_text()
    assert "// " in text
    assert "test_render.py" in text
