"""Pin the rule: booleans are never accepted where a number is expected.

Python makes `bool` a subclass of `int`, so without explicit guards
`cube(True)` would silently become `cube([1, 1, 1])`. That's almost
always a bug. The library rejects this across every number-taking entry
point.
"""

import pytest

from scadwright import Component, Param
from scadwright.errors import ValidationError
from scadwright.primitives import circle, cube, cylinder, sphere, square


@pytest.mark.parametrize(
    "call",
    [
        lambda: cube(True),
        lambda: cube([True, 2, 3]),
        lambda: sphere(r=True),
        lambda: cylinder(h=True, r=1),
        lambda: circle(r=True),
        lambda: square(True),
        lambda: cube(1).translate([True, 0, 0]),
        lambda: cube(1).scale([True, 1, 1]),
    ],
    ids=[
        "cube-size-scalar",
        "cube-size-vector",
        "sphere-r",
        "cylinder-h",
        "circle-r",
        "square-size",
        "translate-vector",
        "scale-vector",
    ],
)
def test_bool_rejected_where_number_expected(call):
    with pytest.raises(ValidationError):
        call()


def test_param_numeric_type_rejects_bool():
    class _FloatParam(Component):
        x = Param(float)
        def build(self): return cube(1)

    class _IntParam(Component):
        x = Param(int)
        def build(self): return cube(1)

    with pytest.raises(ValidationError, match="bool"):
        _FloatParam(x=True)
    with pytest.raises(ValidationError, match="bool"):
        _IntParam(x=False)


def test_param_bool_type_accepts_bool():
    """Explicit bool Params still work — the rule only forbids bool where a
    numeric type is declared."""
    class _C(Component):
        flag = Param(bool, default=False)
        def build(self): return cube(1)

    assert _C(flag=True).flag is True
    assert _C(flag=False).flag is False
