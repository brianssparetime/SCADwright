"""r/d disambiguation on sphere/circle/cylinder.

Covers the d → r conversion rule (r = d/2) and the mutual-exclusion
errors. Attribute roundtrips (e.g. `sphere(r=5).r == 5.0`) are trivially
covered by Param; not re-tested here.
"""

import pytest

from scadwright.errors import ValidationError
from scadwright.primitives import circle, cylinder, sphere


@pytest.mark.parametrize(
    "factory, d_kwarg, expected_r",
    [
        (sphere, {"d": 10}, 5.0),
        (circle, {"d": 10}, 5.0),
    ],
)
def test_d_converts_to_half(factory, d_kwarg, expected_r):
    assert factory(**d_kwarg).r == expected_r


@pytest.mark.parametrize(
    "kwargs, expected_r1, expected_r2",
    [
        ({"r": 3}, 3.0, 3.0),
        ({"d": 6}, 3.0, 3.0),
        ({"r1": 5, "r2": 2}, 5.0, 2.0),
        ({"d1": 10, "d2": 4}, 5.0, 2.0),
        ({"r1": 5, "d2": 4}, 5.0, 2.0),                    # mixing r1/d2 is fine
    ],
)
def test_cylinder_radius_forms(kwargs, expected_r1, expected_r2):
    c = cylinder(h=10, **kwargs)
    assert c.r1 == expected_r1 and c.r2 == expected_r2


@pytest.mark.parametrize(
    "factory, kwargs, match",
    [
        (sphere, {"r": 5, "d": 10}, "not both"),
        (circle, {"r": 5, "d": 10}, "not both"),
        (cylinder, {"h": 10, "r": 3, "d": 6}, "cylinder r.*cylinder d.*not both"),
        (cylinder, {"h": 10, "r1": 3, "d1": 6}, "cylinder r1.*cylinder d1.*not both"),
        (cylinder, {"h": 10, "r2": 3, "d2": 6}, "cylinder r2.*cylinder d2.*not both"),
    ],
)
def test_rejects_both_r_and_d(factory, kwargs, match):
    with pytest.raises(ValidationError, match=match):
        factory(**kwargs)


def test_r_d_error_captures_source_location():
    try:
        cylinder(h=10, r=3, d=6)
    except ValidationError as e:
        assert e.source_location is not None
        assert "test_radius_diameter.py" in (e.source_location.file or "")
