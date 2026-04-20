"""Param validator shorthand kwargs: `positive=True`, `non_negative=True`,
`min=`, `max=`, `range=`, `one_of=`.

Each shorthand expands to a built-in validator. We verify the expansion
is wired correctly (accepts one valid value, rejects one invalid) rather
than re-testing the validator library behaviorally across every edge case."""

import pytest

from scadwright import Component
from scadwright.component.params import Param
from scadwright.errors import ValidationError
from scadwright.primitives import cube


def _component_with_param(**param_kwargs):
    """Build a one-param Component with the given Param config."""

    class _C(Component):
        x = Param(float, **param_kwargs) if param_kwargs.get("type", float) is float else Param(int, **param_kwargs)

        def build(self):
            return cube(1)

    return _C


@pytest.mark.parametrize(
    "param_kwargs, ok_value, bad_value, error_match",
    [
        ({"positive": True},           5,    0,    "must be positive"),
        ({"positive": True},           5,    -1,   "must be positive"),
        ({"non_negative": True},       0,    -1,   "non-negative"),
        ({"range": (0.0, 1.0)},        0.5,  2.0,  r"in \[0.0, 1.0\]"),
    ],
    ids=["positive-rejects-zero", "positive-rejects-negative", "non-negative-rejects-negative", "range"],
)
def test_float_shorthand(param_kwargs, ok_value, bad_value, error_match):
    class _C(Component):
        x = Param(float, **param_kwargs)
        def build(self): return cube(1)

    _C(x=ok_value)
    with pytest.raises(ValidationError, match=error_match):
        _C(x=bad_value)


def test_int_min_max_shorthand():
    class _Bounded(Component):
        x = Param(int, min=5, max=10)
        def build(self): return cube(1)

    _Bounded(x=7)
    with pytest.raises(ValidationError, match=">= 5"):
        _Bounded(x=4)
    with pytest.raises(ValidationError, match="<= 10"):
        _Bounded(x=11)


def test_one_of_shorthand():
    class _OneOf(Component):
        mode = Param(str, one_of=("a", "b", "c"))
        def build(self): return cube(1)

    _OneOf(mode="a")
    with pytest.raises(ValidationError, match="must be one of"):
        _OneOf(mode="z")


def test_shorthand_stacks_with_validators_list():
    """Shorthand kwargs must compose with explicit `validators=[...]`, not
    replace them."""
    def _no_42(v):
        if v == 42:
            raise ValidationError("no 42")

    class _Combined(Component):
        x = Param(float, positive=True, validators=[_no_42])
        def build(self): return cube(1)

    _Combined(x=5)
    with pytest.raises(ValidationError, match="positive"):
        _Combined(x=-1)
    with pytest.raises(ValidationError, match="no 42"):
        _Combined(x=42)
