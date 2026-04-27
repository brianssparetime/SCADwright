"""Tests for the cardinality helpers in the equations DSL.

`exactly_one`, `at_least_one`, `at_most_one`, and `all_or_none` live in the
curated predicate namespace. Each takes any number of arguments and checks
them against `is not None`. They pair naturally with the `?` sigil.
"""

from __future__ import annotations

import pytest

from scadwright import Component, Param
from scadwright.component.equations import (
    _exactly_one,
    _at_least_one,
    _at_most_one,
    _all_or_none,
)
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# =============================================================================
# Pure-function behavior
# =============================================================================


def test_exactly_one_counts_non_none():
    assert _exactly_one(1, None) is True
    assert _exactly_one(None, 2) is True
    assert _exactly_one(None, None) is False
    assert _exactly_one(1, 2) is False
    assert _exactly_one(1, 2, 3) is False
    assert _exactly_one(1, None, None) is True


def test_exactly_one_zero_args_is_false():
    assert _exactly_one() is False


def test_exactly_one_treats_zero_as_set():
    # Semantics: "set" means "is not None". 0, False, "" all count as set.
    assert _exactly_one(0, None) is True
    assert _exactly_one(False, None) is True
    assert _exactly_one("", None) is True


def test_at_least_one_counts_non_none():
    assert _at_least_one(1, None) is True
    assert _at_least_one(None, None) is False
    assert _at_least_one(1, 2) is True
    assert _at_least_one() is False


def test_at_most_one_counts_non_none():
    assert _at_most_one(1, None) is True
    assert _at_most_one(None, None) is True
    assert _at_most_one(1, 2) is False
    assert _at_most_one(1, 2, 3) is False
    assert _at_most_one() is True


def test_all_or_none_is_symmetric():
    assert _all_or_none(None, None) is True
    assert _all_or_none(1, 2) is True
    assert _all_or_none(1, 2, 3) is True
    assert _all_or_none(1, None) is False
    assert _all_or_none(None, 2, 3) is False
    assert _all_or_none() is True


# =============================================================================
# End-to-end: helpers inside a real Component
# =============================================================================


class _XorBox(Component):
    size = Param(tuple)
    equations = [
        "?fillet > 0",
        "?chamfer > 0",
        "exactly_one(?fillet, ?chamfer)",
    ]

    def build(self):
        x, y, z = self.size
        return cube([x, y, z])


def test_exactly_one_accepts_one_set():
    _XorBox(size=(10, 10, 10), fillet=2)
    _XorBox(size=(10, 10, 10), chamfer=2)


def test_exactly_one_rejects_neither_set():
    with pytest.raises(ValidationError, match=r"exactly_one\(fillet, chamfer\)"):
        _XorBox(size=(10, 10, 10))


def test_exactly_one_rejects_both_set():
    with pytest.raises(ValidationError, match=r"exactly_one\(fillet, chamfer\)"):
        _XorBox(size=(10, 10, 10), fillet=2, chamfer=3)


class _AtLeastOneBox(Component):
    size = Param(tuple)
    equations = [
        "?fillet > 0",
        "?chamfer > 0",
        "at_least_one(?fillet, ?chamfer)",
    ]

    def build(self):
        x, y, z = self.size
        return cube([x, y, z])


def test_at_least_one_rejects_neither_set():
    with pytest.raises(ValidationError, match=r"at_least_one\(fillet, chamfer\)"):
        _AtLeastOneBox(size=(10, 10, 10))


def test_at_least_one_accepts_both_set():
    _AtLeastOneBox(size=(10, 10, 10), fillet=2, chamfer=3)


class _AllOrNoneBox(Component):
    size = Param(tuple)
    equations = [
        "?fillet > 0",
        "?chamfer > 0",
        "all_or_none(?fillet, ?chamfer)",
    ]

    def build(self):
        x, y, z = self.size
        return cube([x, y, z])


def test_all_or_none_accepts_both_set():
    _AllOrNoneBox(size=(10, 10, 10), fillet=2, chamfer=3)


def test_all_or_none_accepts_neither_set():
    _AllOrNoneBox(size=(10, 10, 10))


def test_all_or_none_rejects_mixed():
    with pytest.raises(ValidationError, match=r"all_or_none\(fillet, chamfer\)"):
        _AllOrNoneBox(size=(10, 10, 10), fillet=2)


# =============================================================================
# Error enrichment
# =============================================================================


def test_enrichment_shows_each_argument_value():
    try:
        _XorBox(size=(10, 10, 10), fillet=2, chamfer=3)
    except ValidationError as exc:
        msg = str(exc)
        assert "fillet=2.0" in msg
        assert "chamfer=3.0" in msg
    else:
        pytest.fail("expected ValidationError")


def test_enrichment_shows_none_for_unset():
    try:
        _XorBox(size=(10, 10, 10))
    except ValidationError as exc:
        msg = str(exc)
        assert "fillet=None" in msg
        assert "chamfer=None" in msg
    else:
        pytest.fail("expected ValidationError")
