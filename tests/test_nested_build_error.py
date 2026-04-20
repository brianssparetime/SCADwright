"""Tests for nested-component error context (MajorReview Group 3g)."""

import pytest

from scadwright import Component
from scadwright.primitives import cube
from scadwright.component.params import Param
from scadwright.errors import BuildError, ValidationError


class _Broken(Component):
    def build(self):
        raise RuntimeError("intentional failure")


class _Middle(Component):
    def build(self):
        return _Broken()._get_built_tree()


class _Outer(Component):
    def build(self):
        return _Middle()._get_built_tree()


def test_build_error_notes_include_parent_component():
    with pytest.raises(BuildError) as excinfo:
        _Outer()._get_built_tree()
    notes = getattr(excinfo.value, "__notes__", [])
    # At least Middle and Outer should have added notes while bubbling.
    assert any("_Middle" in n for n in notes)
    assert any("_Outer" in n for n in notes)


def test_build_error_notes_include_source_location():
    with pytest.raises(BuildError) as excinfo:
        _Outer()._get_built_tree()
    notes = getattr(excinfo.value, "__notes__", [])
    # Each note names a file location of the parent Component's instantiation.
    assert any("test_nested_build_error.py" in n for n in notes)


def test_validation_error_from_nested_also_carries_notes():
    class _BadInner(Component):
        def build(self):
            # Deliberately trigger a scadwright ValidationError inside build.
            return cube(-5)

    class _BadOuter(Component):
        def build(self):
            return _BadInner()._get_built_tree()

    with pytest.raises(ValidationError) as excinfo:
        _BadOuter()._get_built_tree()
    notes = getattr(excinfo.value, "__notes__", [])
    assert any("_BadInner" in n for n in notes)
    assert any("_BadOuter" in n for n in notes)
