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
