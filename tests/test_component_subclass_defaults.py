"""Subclass class-attr overrides of inherited Params — the Pattern-18
authoring style from docs/organizing_a_project.md."""

import pytest

from scadwright import Component, Param
from scadwright.errors import ValidationError
from scadwright.primitives import cube


class _Box(Component):
    size = Param(tuple)
    wall_thk = Param(float, positive=True)

    def build(self):
        return cube(self.size)


class _MyBox(_Box):
    size = (10, 20, 30)
    wall_thk = 2.5


def test_subclass_class_attr_fills_in_param_default():
    b = _MyBox()
    assert b.size == (10, 20, 30)
    assert b.wall_thk == 2.5


def test_subclass_default_still_overridable_at_instantiation():
    b = _MyBox(size=(1, 2, 3))
    assert b.size == (1, 2, 3)
    # Unoverridden param still uses the subclass default.
    assert b.wall_thk == 2.5


def test_subclass_default_runs_validators():
    """A class-attr override must still pass the inherited Param's
    validators, just like a passed kwarg would."""

    class _Bad(_Box):
        size = (1, 2, 3)
        wall_thk = -1.0                                    # positive=True → raise

    with pytest.raises(ValidationError, match="positive"):
        _Bad()


def test_unrelated_class_attr_does_not_become_a_param():
    """Class attrs that don't match any inherited Param name are left alone."""

    class _Mine(_Box):
        size = (1, 1, 1)
        wall_thk = 1.0
        helper = 42                                        # no matching Param

    m = _Mine()
    assert m.helper == 42                                  # still a plain class attr
    assert "helper" not in type(m).__params__


def test_deeper_inheritance_chain():
    """Three levels: abstract → project-default → variant override."""

    class _ProjectBox(_Box):
        size = (100, 50, 25)
        wall_thk = 3.0

    class _BigVariant(_ProjectBox):
        size = (200, 100, 50)
        # wall_thk inherited from _ProjectBox

    big = _BigVariant()
    assert big.size == (200, 100, 50)
    assert big.wall_thk == 3.0


def test_subclass_with_redeclared_param_still_works():
    """If a subclass REDECLARES a Param (not just overrides with a value),
    the new Param replaces the old one."""

    class _Stricter(_Box):
        size = (1, 1, 1)
        wall_thk = Param(float, positive=True, default=5.0)   # explicit Param

    s = _Stricter()
    assert s.wall_thk == 5.0
