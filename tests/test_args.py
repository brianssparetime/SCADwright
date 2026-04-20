import pytest

from scadwright import arg
from scadwright.errors import SCADwrightError
from scadwright.api import args as _args


@pytest.fixture(autouse=True)
def reset_args():
    _args._reset_for_testing()
    yield
    _args._reset_for_testing()


def test_argv_override():
    """Passing --width=N from argv overrides the declared default."""
    _args.set_argv(["--width=42"])
    assert arg("width", default=10, type=float) == 42.0


def test_multiple_args():
    _args.set_argv(["--width=5", "--height=8"])
    assert arg("width", default=1, type=float) == 5.0
    assert arg("height", default=1, type=float) == 8.0


def test_unknown_argv_ignored():
    """parse_known_args — unknown args don't blow up."""
    _args.set_argv(["--width=5", "--unrelated=foo"])
    assert arg("width", default=1, type=float) == 5.0


def test_reregistration_with_same_params_ok():
    _args.set_argv([])
    v1 = arg("width", default=10, type=float)
    v2 = arg("width", default=10, type=float)
    assert v1 == v2 == 10.0


def test_reregistration_with_different_params_raises():
    _args.set_argv([])
    arg("width", default=10, type=float)
    with pytest.raises(SCADwrightError, match="different parameters"):
        arg("width", default=99, type=float)


def test_bad_value_raises():
    _args.set_argv(["--count=notanumber"])
    with pytest.raises(SCADwrightError):
        arg("count", default=1, type=int)
