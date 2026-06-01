from scadwright.errors import ValidationError
from scadwright.ast.base import SourceLocation


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
