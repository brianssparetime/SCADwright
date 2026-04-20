"""Param validation errors carry the user's source location (Group 9b).

Prior to this, only factory-call errors (cube/sphere/etc.) surfaced a
source_location. Param errors did not, making Component misuse harder to
debug. Now both carry the user's call site.
"""

import inspect

import pytest

from scadwright import Component, Param
from scadwright.component.params import positive
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# --- Auto-init path ---


class _AutoInit(Component):
    w = Param(float, positive=True)

    def build(self):
        return cube(self.w)


def test_auto_init_error_has_source_location_at_caller():
    line = inspect.currentframe().f_lineno
    try:
        _AutoInit(w=-5)  # line + 2
    except ValidationError as exc:
        assert exc.source_location is not None
        assert exc.source_location.line == line + 2
        assert "test_param_source_location.py" in exc.source_location.file
    else:
        pytest.fail("expected ValidationError")


# --- Post-construction write path ---


class _Writable(Component):
    w = Param(float, positive=True, default=1.0)

    def build(self):
        return cube(self.w)


def test_post_construction_write_error_points_at_assignment_line():
    c = _Writable()
    line = inspect.currentframe().f_lineno
    try:
        c.w = -5  # line + 2
    except ValidationError as exc:
        assert exc.source_location is not None
        assert exc.source_location.line == line + 2
    else:
        pytest.fail("expected ValidationError")


# --- List-form validators produce located errors too ---


class _ListForm(Component):
    w = Param(float, validators=[positive])

    def build(self):
        return cube(self.w)


def test_list_form_validator_error_has_source_location():
    line = inspect.currentframe().f_lineno
    try:
        _ListForm(w=-5)  # line + 2
    except ValidationError as exc:
        assert exc.source_location is not None
        assert exc.source_location.line == line + 2
    else:
        pytest.fail("expected ValidationError")


# --- Coercion failures also carry location ---


class _IntParam(Component):
    n = Param(int)

    def build(self):
        return cube(1)


def test_coercion_failure_has_source_location():
    line = inspect.currentframe().f_lineno
    try:
        _IntParam(n="not-a-number")  # line + 2
    except ValidationError as exc:
        assert exc.source_location is not None
        assert exc.source_location.line == line + 2
    else:
        pytest.fail("expected ValidationError")


def test_bool_as_number_rejection_has_source_location():
    class _C(Component):
        x = Param(float)
        def build(self): return cube(1)

    line = inspect.currentframe().f_lineno
    try:
        _C(x=True)  # line + 2
    except ValidationError as exc:
        assert exc.source_location is not None
        assert exc.source_location.line == line + 2
    else:
        pytest.fail("expected ValidationError")


# --- The formatted message includes the location ---


def test_error_message_includes_location_string():
    try:
        _AutoInit(w=-5)
    except ValidationError as exc:
        assert "at " in str(exc)
        assert ".py" in str(exc)
