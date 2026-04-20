import pytest

from scadwright.errors import BuildError, EmitError, SCADwrightError, ValidationError
from scadwright.ast.base import SourceLocation


def test_all_errors_inherit_scadwright_error():
    assert issubclass(ValidationError, SCADwrightError)
    assert issubclass(BuildError, SCADwrightError)
    assert issubclass(EmitError, SCADwrightError)


def test_scadwright_error_catches_all():
    for cls in (ValidationError, BuildError, EmitError):
        with pytest.raises(SCADwrightError):
            raise cls("boom")


def test_source_location_attribute():
    loc = SourceLocation(file="foo.py", line=10)
    err = ValidationError("bad radius", source_location=loc)
    assert err.source_location is loc
    assert "foo.py:10" in str(err)
    assert "bad radius" in str(err)


def test_source_location_optional():
    err = ValidationError("generic failure")
    assert err.source_location is None
    assert str(err) == "generic failure"


def test_errors_do_not_inherit_valueerror():
    """Decision: SCADwrightError is a clean hierarchy under Exception."""
    assert not issubclass(SCADwrightError, ValueError)
