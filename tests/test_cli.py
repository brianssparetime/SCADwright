from pathlib import Path

import pytest

from scadwright import cli
from scadwright.api import args as _args


@pytest.fixture(autouse=True)
def reset_args():
    _args._reset_for_testing()
    yield
    _args._reset_for_testing()


def test_build_basic(tmp_path: Path):
    script = tmp_path / "m.py"
    script.write_text(
        "from scadwright.primitives import cube\n"
        "MODEL = cube([1, 2, 3])\n"
    )
    out = tmp_path / "m.scad"
    rc = cli.main(["build", str(script), "-o", str(out)])
    assert rc == 0
    contents = out.read_text()
    assert "cube([1, 2, 3]" in contents


def test_build_default_output_path(tmp_path: Path):
    script = tmp_path / "widget.py"
    script.write_text(
        "from scadwright.primitives import cube\n"
        "MODEL = cube(5)\n"
    )
    rc = cli.main(["build", str(script)])
    assert rc == 0
    assert (tmp_path / "widget.scad").exists()


def test_build_missing_model_errors(tmp_path: Path, capsys):
    script = tmp_path / "noscript.py"
    script.write_text("x = 1\n")
    rc = cli.main(["build", str(script)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "MODEL" in err


def test_build_script_not_found(tmp_path: Path, capsys):
    rc = cli.main(["build", str(tmp_path / "nope.py")])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_build_debug_flag(tmp_path: Path):
    script = tmp_path / "m.py"
    script.write_text(
        "from scadwright.primitives import cube\n"
        "MODEL = cube(1)\n"
    )
    out = tmp_path / "m.scad"
    rc = cli.main(["build", str(script), "-o", str(out), "--debug"])
    assert rc == 0
    text = out.read_text()
    assert "// " in text


def test_build_compact_flag(tmp_path: Path):
    script = tmp_path / "m.py"
    script.write_text(
        "from scadwright.primitives import cube\n"
        "MODEL = cube(1).translate([0, 0, 5])\n"
    )
    out = tmp_path / "m.scad"
    rc = cli.main(["build", str(script), "-o", str(out), "--compact"])
    assert rc == 0
    text = out.read_text()
    assert "\n" not in text


# ---------- preview / render subcommands ----------


def _stub_openscad(tmp_path: Path) -> Path:
    """Create a fake openscad executable that records its argv to a file
    and writes its `-o` output target if given."""
    stub = tmp_path / "fake-openscad"
    log = tmp_path / "openscad.log"
    stub.write_text(
        "#!/bin/sh\n"
        f"echo \"$@\" > {log}\n"
        "while [ $# -gt 0 ]; do\n"
        "  if [ \"$1\" = \"-o\" ]; then\n"
        "    shift\n"
        "    : > \"$1\"\n"
        "  fi\n"
        "  shift\n"
        "done\n"
    )
    stub.chmod(0o755)
    return stub


class _FakePopen:
    """Capture Popen invocations without actually spawning anything. Preview
    detaches its subprocess so we can't observe a real one synchronously."""

    invocations: list[list[str]] = []

    def __init__(self, args, **kwargs):
        type(self).invocations.append(list(args))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_popen(monkeypatch):
    _FakePopen.invocations = []
    monkeypatch.setattr(cli.subprocess, "Popen", _FakePopen)
    return _FakePopen


def test_preview_builds_temp_scad_and_launches_openscad(tmp_path: Path, capsys, fake_popen):
    script = tmp_path / "m.py"
    script.write_text(
        "from scadwright.primitives import cube\n"
        "MODEL = cube(7)\n"
    )
    fake = _stub_openscad(tmp_path)
    rc = cli.main(["preview", str(script), "--openscad", str(fake)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "preview: wrote" in err
    assert len(fake_popen.invocations) == 1
    invoked = fake_popen.invocations[0]
    assert invoked[0] == str(fake)
    scad_path = Path(invoked[1])
    assert scad_path.suffix == ".scad"
    assert scad_path.exists()
    assert "cube([7, 7, 7]" in scad_path.read_text()


def test_preview_temp_path_is_stable_across_runs(tmp_path: Path, fake_popen):
    script = tmp_path / "m.py"
    script.write_text(
        "from scadwright.primitives import cube\n"
        "MODEL = cube(1)\n"
    )
    fake = _stub_openscad(tmp_path)
    cli.main(["preview", str(script), "--openscad", str(fake)])
    cli.main(["preview", str(script), "--openscad", str(fake)])
    paths = [inv[1] for inv in fake_popen.invocations]
    assert paths[0] == paths[1], (
        "preview should reuse the same temp path so OpenSCAD auto-reload sees changes"
    )


def test_preview_variant_changes_temp_path(tmp_path: Path, fake_popen):
    script = tmp_path / "m.py"
    script.write_text(
        "from scadwright.primitives import cube\n"
        "MODEL = cube(1)\n"
    )
    fake = _stub_openscad(tmp_path)
    cli.main(["preview", str(script), "--openscad", str(fake)])
    cli.main(["preview", str(script), "--openscad", str(fake), "--variant", "print"])
    paths = [inv[1] for inv in fake_popen.invocations]
    assert paths[0] != paths[1]


def test_render_invokes_openscad_with_dash_o(tmp_path: Path, capsys):
    script = tmp_path / "m.py"
    script.write_text(
        "from scadwright.primitives import cube\n"
        "MODEL = cube(2)\n"
    )
    fake = _stub_openscad(tmp_path)
    out_stl = tmp_path / "m.stl"
    rc = cli.main(["render", str(script), "-o", str(out_stl), "--openscad", str(fake)])
    assert rc == 0
    log = (tmp_path / "openscad.log").read_text()
    assert "-o" in log
    assert str(out_stl) in log
    assert out_stl.exists()  # stub touched it


def test_render_default_output_is_script_with_stl(tmp_path: Path):
    script = tmp_path / "widget.py"
    script.write_text(
        "from scadwright.primitives import cube\n"
        "MODEL = cube(1)\n"
    )
    fake = _stub_openscad(tmp_path)
    rc = cli.main(["render", str(script), "--openscad", str(fake)])
    assert rc == 0
    expected = tmp_path / "widget.stl"
    assert expected.exists()


def test_preview_missing_openscad_errors_clearly(tmp_path: Path, capsys):
    script = tmp_path / "m.py"
    script.write_text(
        "from scadwright.primitives import cube\n"
        "MODEL = cube(1)\n"
    )
    rc = cli.main(["preview", str(script), "--openscad", "/no/such/openscad-binary"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "openscad" in err.lower()
