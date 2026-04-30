"""Tests for `Param.group(...)` — multi-param batch declaration."""

import pytest

from scadwright import Component, Param
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# --- Basic behavior ---


class _Basic(Component):
    Param.group("a b c d", float, positive=True)

    def build(self):
        return cube(1)


def test_each_grouped_name_is_an_independent_param():
    """Params in a group must be distinct descriptors, not aliases of
    one — otherwise assigning to one would leak into the others."""
    params = [_Basic.__params__[n] for n in ("a", "b", "c", "d")]
    assert len(set(id(p) for p in params)) == 4


def test_values_validate_independently():
    _Basic(a=1, b=2, c=3, d=4)
    with pytest.raises(ValidationError, match="positive"):
        _Basic(a=-1, b=2, c=3, d=4)


# --- Separator flexibility ---


@pytest.mark.parametrize(
    "spec",
    ["a b c", "a,b,c", "a, b c", "a,b, c", "  a   b   c  "],
    ids=["spaces", "commas", "mixed", "mixed-trailing", "extra-whitespace"],
)
def test_group_accepts_space_or_comma_separators(spec):
    class _Sep(Component):
        Param.group(spec, float, positive=True)
        def build(self): return cube(1)

    assert set(_Sep.__params__.keys()) == {"a", "b", "c"}


# --- Per-param override (redeclaration after group) ---


class _WithOverride(Component):
    Param.group("a b c", float, positive=True)
    c = Param(float, positive=True, default=5.0)  # override: c gets a default

    def build(self):
        return cube(1)


def test_per_param_override_replaces_group_entry():
    assert _WithOverride.__params__["c"].default == 5.0
    assert _WithOverride.__params__["a"].default  # is _MISSING
    # Instantiation: a and b required; c picks up the default.
    inst = _WithOverride(a=1, b=2)
    assert inst.c == 5.0


# --- Kwarg composition ---


class _BoundedInts(Component):
    Param.group("x y z", int, min=0, max=10)

    def build(self):
        return cube(1)


def test_shorthand_min_max_applied_to_all():
    _BoundedInts(x=5, y=0, z=10)
    with pytest.raises(ValidationError, match=">= 0"):
        _BoundedInts(x=-1, y=0, z=0)
    with pytest.raises(ValidationError, match="<= 10"):
        _BoundedInts(x=0, y=0, z=11)


class _OneOfGroup(Component):
    Param.group("a b", str, one_of=("x", "y"))
    def build(self): return cube(1)


def test_one_of_shorthand_applied_to_all():
    _OneOfGroup(a="x", b="y")
    with pytest.raises(ValidationError, match="must be one of"):
        _OneOfGroup(a="z", b="y")


class _WithSharedDefault(Component):
    Param.group("a b c", float, positive=True, default=1.0)

    def build(self):
        return cube(1)


def test_shared_default_applied_to_all():
    inst = _WithSharedDefault()
    assert inst.a == 1.0 and inst.b == 1.0 and inst.c == 1.0


class _WithExtraValidators(Component):
    def _ensure_even(v):
        if v % 2:
            raise ValidationError("must be even")
    Param.group("a b", int, validators=[_ensure_even])

    def build(self):
        return cube(1)


def test_validators_list_applied_to_all():
    _WithExtraValidators(a=2, b=4)
    with pytest.raises(ValidationError, match="must be even"):
        _WithExtraValidators(a=3, b=4)


# --- Error cases ---


def test_duplicate_name_in_group_raises():
    with pytest.raises(ValidationError, match="duplicate"):
        class _Dup(Component):
            Param.group("a b a", float)
            def build(self): return cube(1)


def test_empty_names_raises():
    with pytest.raises(ValidationError, match="non-empty"):
        class _Empty(Component):
            Param.group("", float)
            def build(self): return cube(1)


def test_name_collision_with_existing_declaration_raises():
    with pytest.raises(ValidationError, match="already defined"):
        class _Collide(Component):
            a = Param(float)
            Param.group("a b c", float)
            def build(self): return cube(1)


def test_called_outside_class_body_raises():
    with pytest.raises(ValidationError, match="class body"):
        Param.group("a b c", float)


# --- Integration with equations ---


class _WithEquations(Component):
    Param.group("h id od thk", float, positive=True)
    equations = ["od = id + 2*thk"]

    def build(self):
        return cube(self.h)


def test_group_plus_equations_solves_correctly():
    t = _WithEquations(h=10, id=8, thk=1)
    assert t.od == pytest.approx(10.0)
    t2 = _WithEquations(h=10, od=10, thk=1)
    assert t2.id == pytest.approx(8.0)


def test_group_plus_equations_respects_freeze():
    t = _WithEquations(h=10, id=8, od=10)
    with pytest.raises(ValidationError, match="frozen"):
        t.thk = 5
