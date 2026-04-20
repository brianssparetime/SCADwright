"""Tests for the stack-walk source-location capture (MajorReview Group 6d).

The key property: internal scadwright frames are transparent to source location
capture, so wrappers don't break the captured call site.
"""

import inspect

from scadwright import Component
from scadwright.primitives import cube
from scadwright.ast.base import SourceLocation, _is_internal_frame


def _user_cube_wrapper(size):
    """User-code wrapper around cube. Its own source_location should
    point at the `cube(...)` call here, because that's user code too."""
    return cube(size)


def test_cube_source_location_is_user_call_site():
    line = inspect.currentframe().f_lineno
    c = cube(10)  # line + 1
    assert c.source_location is not None
    assert c.source_location.line == line + 1


def test_cube_wrapped_in_user_helper_points_into_helper():
    # The user wrote `cube(size)` inside their helper — that IS the call site.
    c = _user_cube_wrapper(5)
    assert c.source_location is not None
    # The location is the line of `return cube(size)` inside the helper.
    assert "test_source_location_walk.py" in c.source_location.file
    assert c.source_location.func == "_user_cube_wrapper"


def test_internal_frame_predicate():
    # Internal: any scadwright module lives inside the package root.
    from scadwright import ast as _ast_pkg

    assert _is_internal_frame(_ast_pkg.__file__)
    # External: this test file is not.
    assert not _is_internal_frame(__file__)


def test_from_caller_takes_no_arguments():
    # The method walks past scadwright internals automatically; no skip counting.
    def capture_here():
        return SourceLocation.from_caller()

    loc_here = capture_here()
    assert loc_here is not None
    # Should land on the user-test frame (the calling function).
    assert "test_source_location_walk.py" in loc_here.file


class _ManualComponent(Component):
    def __init__(self, w):
        super().__init__()
        self.w = w

    def build(self):
        return cube(self.w)


def test_manual_component_super_init_walks_past_init_frame():
    line = inspect.currentframe().f_lineno
    c = _ManualComponent(3)  # line + 1
    assert c.source_location is not None
    assert c.source_location.line == line + 1


class _Mid(_ManualComponent):
    def __init__(self, w):
        super().__init__(w)


class _Deep(_Mid):
    def __init__(self, w):
        super().__init__(w)


def test_multi_level_super_chain_walks_past_all_inits():
    line = inspect.currentframe().f_lineno
    c = _Deep(7)  # line + 1
    assert c.source_location is not None
    # Even through 3 levels of __init__ -> super().__init__(), the captured
    # location is the outermost user instantiation line.
    assert c.source_location.line == line + 1
