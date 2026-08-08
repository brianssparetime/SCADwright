from pathlib import Path

import pytest

from scadwright import cli
from scadwright.api import args as _args


@pytest.fixture(autouse=True)
def reset_args():
    _args._reset_for_testing()
    yield
    _args._reset_for_testing()


def test_unknown_args_forwarded_to_script(tmp_path: Path):
    script = tmp_path / "m.py"
    script.write_text(
        "from scadwright import arg\n"
        "from scadwright.primitives import cube\n"
        "width = arg('width', default=10, type=float)\n"
        "MODEL = cube([width, width, width])\n"
    )
    out = tmp_path / "m.scad"
    rc = cli.main(["build", str(script), "-o", str(out), "--width=42"])
    assert rc == 0
    contents = out.read_text()
    assert "cube([42, 42, 42]" in contents


def test_variant_forwarded(tmp_path: Path):
    script = tmp_path / "m.py"
    script.write_text(
        "from scadwright import Component, current_variant\n"
        "from scadwright.primitives import cube, sphere\n"
        "class W(Component):\n"
        "    def __init__(self): super().__init__()\n"
        "    def build(self):\n"
        "        if current_variant() == 'print':\n"
        "            return cube(1)\n"
        "        return sphere(r=1, fn=8)\n"
        "MODEL = W()\n"
    )
    out_print = tmp_path / "print.scad"
    cli.main(["build", str(script), "-o", str(out_print), "--variant=print"])
    assert "cube" in out_print.read_text()

    # Reset args module state between two CLI invocations.
    _args._reset_for_testing()

    out_display = tmp_path / "display.scad"
    cli.main(["build", str(script), "-o", str(out_display)])
    assert "sphere" in out_display.read_text()


def _plain_script(tmp_path: Path) -> Path:
    script = tmp_path / "plain.py"
    script.write_text(
        "from scadwright.primitives import cube\n"
        "MODEL = cube(10)\n"
    )
    return script


def test_unrecognized_option_is_rejected(tmp_path: Path, capsys):
    script = _plain_script(tmp_path)
    out = tmp_path / "m.scad"
    rc = cli.main(["build", str(script), "-o", str(out), "--framse=48"])
    assert rc == 3
    err = capsys.readouterr().err
    assert "--framse=48" in err
    # The user needs to know the build still happened.
    assert out.exists()


def test_unrecognized_option_error_lists_what_is_accepted(tmp_path: Path, capsys):
    script = tmp_path / "m.py"
    script.write_text(
        "from scadwright import arg\n"
        "from scadwright.primitives import cube\n"
        "MODEL = cube(arg('width', default=10, type=float))\n"
    )
    rc = cli.main([
        "build", str(script), "-o", str(tmp_path / "m.scad"), "--widht=25",
    ])
    assert rc == 3
    err = capsys.readouterr().err
    assert "--widht=25" in err
    assert "--variant" in err          # a flag the subcommand takes
    assert "--width" in err            # a flag the script declares


def test_unrecognized_option_keeps_flag_and_value_together(tmp_path: Path, capsys):
    script = _plain_script(tmp_path)
    rc = cli.main([
        "build", str(script), "-o", str(tmp_path / "m.scad"),
        "--nope", "3,4,5",
    ])
    assert rc == 3
    assert "--nope 3,4,5" in capsys.readouterr().err


def test_recognized_options_do_not_trip_the_check(tmp_path: Path):
    script = tmp_path / "m.py"
    script.write_text(
        "from scadwright import arg\n"
        "from scadwright.primitives import cube\n"
        "MODEL = cube(arg('width', default=10, type=float))\n"
    )
    rc = cli.main([
        "build", str(script), "-o", str(tmp_path / "m.scad"),
        "--width=25", "--variant=print", "--vpr=60,0,30",
    ])
    assert rc == 0


def test_unrecognized_option_rejected_without_a_script(tmp_path: Path, capsys):
    # `graph` never hands argv to the script-parameter parser, so the
    # leftover tokens come straight from the CLI parser instead.
    (tmp_path / "m.py").write_text(
        "from scadwright.primitives import cube\n"
        "MODEL = cube(10)\n"
    )
    rc = cli.main(["graph", str(tmp_path), "--bogus=1"])
    assert rc == 3
    assert "--bogus=1" in capsys.readouterr().err


def test_combined_arg_and_variant(tmp_path: Path):
    script = tmp_path / "m.py"
    script.write_text(
        "from scadwright import arg\n"
        "from scadwright.primitives import cube\n"
        "size = arg('size', default=1, type=int)\n"
        "MODEL = cube(size)\n"
    )
    out = tmp_path / "m.scad"
    rc = cli.main([
        "build", str(script), "-o", str(out),
        "--size=20", "--variant=print", "--debug",
    ])
    assert rc == 0
    txt = out.read_text()
    assert "cube([20, 20, 20]" in txt
    assert "// " in txt
