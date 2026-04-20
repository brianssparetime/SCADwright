import pytest

from scadwright import Component, materialize
from scadwright.errors import BuildError, SCADwrightError, ValidationError
from scadwright.primitives import cube
def test_build_error_wraps_runtime_error():
    class _Boom(Component):
        def __init__(self):
            super().__init__()

        def build(self):
            raise RuntimeError("bad day")

    with pytest.raises(BuildError) as exc_info:
        materialize(_Boom())

    assert "_Boom" in str(exc_info.value)
    assert "bad day" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_build_error_carries_source_location():
    class _Boom(Component):
        def __init__(self):
            super().__init__()

        def build(self):
            raise ValueError("nope")

    import inspect

    line = inspect.currentframe().f_lineno
    instance = _Boom()  # line line+1
    with pytest.raises(BuildError) as exc_info:
        materialize(instance)

    assert exc_info.value.source_location is not None
    assert exc_info.value.source_location.line == line + 1


def test_validation_error_inside_build_not_double_wrapped():
    """ValidationError from a primitive inside build() should pass through."""

    class _BadCube(Component):
        def __init__(self):
            super().__init__()

        def build(self):
            return cube(-5)  # ValidationError

    with pytest.raises(ValidationError):
        materialize(_BadCube())


def test_build_error_is_scadwright_error():
    class _Boom(Component):
        def __init__(self):
            super().__init__()

        def build(self):
            raise RuntimeError("x")

    with pytest.raises(SCADwrightError):
        materialize(_Boom())


def test_build_error_chains_traceback():
    class _Boom(Component):
        def __init__(self):
            super().__init__()

        def build(self):
            x = 1 / 0  # noqa
            return cube(1)

    try:
        materialize(_Boom())
    except BuildError as e:
        assert isinstance(e.__cause__, ZeroDivisionError)
    else:
        raise AssertionError("expected BuildError")
