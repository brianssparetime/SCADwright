"""Subclass class-attr overrides of inherited Params — the Pattern-18
authoring style from docs/organizing_a_project.md."""

import pytest

from scadwright import Component, Param, Spec
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


# =============================================================================
# Class-valued overrides: only a fixed Spec class is a usable value bag
# =============================================================================
#
# A class attribute that shadows an inherited Param supplies that
# parameter's value. The value is read for its attributes, so it must be
# a value, not a class — unless the class is a fixed Spec, whose resolved
# values live on the class itself. The other class shapes are rejected at
# the binding site rather than left to surface later as a descriptor read
# or a resolver error far from the cause.


class _Bayonet(Spec):
    equations = """
        bore = 60.0
        bore_r = bore / 2
    """


class _SizedBayonet(Spec):
    equations = """
        ?bore > 0
        bore_r = bore / 2
    """


class _Holder(Component):
    spec = Param()
    equations = """
        wall = spec.bore_r + 1
    """

    def build(self):
        return cube([self.wall, 1, 1])


def test_fixed_spec_class_binds_as_value_bag():
    """A fixed Spec's resolved values live on the class, so binding the
    bare class is valid and the equations read straight off it."""

    class _ConcreteHolder(_Holder):
        spec = _Bayonet

    h = _ConcreteHolder()
    assert h.wall == 31.0                                  # 60/2 + 1


def test_spec_instance_binds_as_value_bag():
    """A Spec instance is a value source whatever its parameters."""

    class _ConcreteHolder(_Holder):
        spec = _SizedBayonet(bore=40.0)

    h = _ConcreteHolder()
    assert h.wall == 21.0                                  # 40/2 + 1


def test_component_class_binding_is_rejected_at_definition():
    """Binding a Component class yields a descriptor when read; reject it
    at the binding, pointing at the instance and typed-Param forms."""

    class _Part(Component):
        equations = """
            w > 0
        """

        def build(self):
            return cube([self.w, 1, 1])

    with pytest.raises(ValidationError) as exc:
        class _Bad(_Holder):
            spec = _Part                                   # a Component class

    msg = str(exc.value)
    assert "_Bad.spec" in msg
    assert "_Part(...)" in msg                             # instance form
    assert "Param(_Part)" in msg                           # typed-Param form


def test_parameterized_spec_class_binding_is_rejected_at_definition():
    """A parameterized Spec's values are only on an instance, so binding
    the bare class is rejected with an instantiate hint."""

    with pytest.raises(ValidationError) as exc:
        class _Bad(_Holder):
            spec = _SizedBayonet                           # parameterized Spec class

    msg = str(exc.value)
    assert "_Bad.spec" in msg
    assert "_SizedBayonet(...)" in msg


def test_scalar_and_instance_overrides_still_pass():
    """The validation only fires on class-valued overrides; scalars and
    instances are untouched."""

    class _ScalarHolder(_Holder):
        spec = _Bayonet                                    # fixed Spec class: fine

    assert _ScalarHolder().wall == 31.0
