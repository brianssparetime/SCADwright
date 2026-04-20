"""Tests for variant typo detection (Group 7c)."""

import warnings

import pytest

from scadwright import Variant, current_variant, register_variants, variant
from scadwright.api.variant import _reset_for_testing


@pytest.fixture(autouse=True)
def _clean_state():
    """Fresh known-variants / warned-set per test."""
    _reset_for_testing()
    yield
    _reset_for_testing()


def test_comparison_to_known_variant_does_not_warn():
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        with variant("print"):
            assert current_variant() == "print"


def test_comparison_to_unknown_variant_warns():
    with variant("print"):
        with pytest.warns(UserWarning, match="was never activated"):
            _ = current_variant() == "pint"


def test_warning_suggests_close_match():
    with variant("print"):
        with pytest.warns(UserWarning, match="Did you mean 'print'"):
            _ = current_variant() == "pint"


def test_register_variants_prevents_warning():
    register_variants("print", "display", "debug")
    # No active variant, but compared name is registered — no warn.
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        assert not (current_variant() == "print")
        assert not (current_variant() == "display")


def test_unknown_compared_outside_any_variant_still_warns():
    with pytest.warns(UserWarning, match="was never activated"):
        _ = current_variant() == "anything"


def test_warning_is_issued_once_per_unknown_name():
    with variant("print"):
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            _ = current_variant() == "pint"
            _ = current_variant() == "pint"   # second comparison: no new warning
            _ = current_variant() == "pint"   # third either
        relevant = [w for w in recorded if issubclass(w.category, UserWarning)]
        assert len(relevant) == 1


def test_different_unknown_names_warn_separately():
    with variant("print"):
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            _ = current_variant() == "pint"
            _ = current_variant() == "prnt"
        relevant = [w for w in recorded if issubclass(w.category, UserWarning)]
        assert len(relevant) == 2


def test_bool_of_variant():
    assert not current_variant()
    with variant("x"):
        assert current_variant()


def test_name_property():
    assert current_variant().name is None
    with variant("print"):
        assert current_variant().name == "print"


def test_variant_equality_with_None():
    # Outside any variant, equals None.
    assert current_variant() == None  # noqa: E711
    # Inside, does not.
    with variant("x"):
        assert not (current_variant() == None)  # noqa: E711


def test_variant_hashable():
    v = current_variant()
    assert hash(v) == hash(None)
    with variant("x"):
        assert hash(current_variant()) == hash("x")


def test_register_variants_rejects_bad_input():
    with pytest.raises(ValueError):
        register_variants("")
    with pytest.raises(ValueError):
        register_variants(42)


def test_variant_str_coerces_usefully():
    assert str(current_variant()) == ""
    with variant("print"):
        assert str(current_variant()) == "print"
