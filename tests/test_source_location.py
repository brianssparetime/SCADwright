from scadwright.primitives import cube
from scadwright.ast import base as _base


def test_cube_captures_source_location():
    c = cube(10)  # this line's number is captured
    expected_line = 6  # keep in sync if moving the call above
    assert c.source_location is not None
    assert c.source_location.file.endswith("test_source_location.py")
    assert c.source_location.line == expected_line


def test_translate_captures_call_site():
    c = cube(10)
    t = c.translate([0, 0, 5])
    assert t.source_location is not None
    assert t.source_location.file.endswith("test_source_location.py")
    # The wrapper's source_location points at the .translate() call line, not cube's.
    assert t.source_location.line != c.source_location.line


def test_capture_toggle():
    _base.capture_source_locations = False
    try:
        c = cube(10)
        assert c.source_location is None
    finally:
        _base.capture_source_locations = True


def test_source_location_str_formatting():
    c = cube(10)
    s = str(c.source_location)
    assert "test_source_location.py" in s
    assert ":" in s
