"""Bearing dummy Components for fit-check and visualization."""

from __future__ import annotations

from collections import namedtuple

from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.errors import ValidationError
from scadwright.shapes.three_d import Tube

BearingSpec = namedtuple("BearingSpec", "id od width")

# Common 6xx series ball bearing dimensions (mm).
BEARING_DATA: dict[str, BearingSpec] = {
    "604":  BearingSpec(id=4,  od=12, width=4),
    "605":  BearingSpec(id=5,  od=14, width=5),
    "606":  BearingSpec(id=6,  od=17, width=6),
    "607":  BearingSpec(id=7,  od=19, width=6),
    "608":  BearingSpec(id=8,  od=22, width=7),
    "609":  BearingSpec(id=9,  od=24, width=7),
    "623":  BearingSpec(id=3,  od=10, width=4),
    "624":  BearingSpec(id=4,  od=13, width=5),
    "625":  BearingSpec(id=5,  od=16, width=5),
    "626":  BearingSpec(id=6,  od=19, width=6),
    "6000": BearingSpec(id=10, od=26, width=8),
    "6001": BearingSpec(id=12, od=28, width=8),
    "6002": BearingSpec(id=15, od=32, width=9),
    "6003": BearingSpec(id=17, od=35, width=10),
    "6004": BearingSpec(id=20, od=42, width=12),
    "6005": BearingSpec(id=25, od=47, width=12),
    "6200": BearingSpec(id=10, od=30, width=9),
    "6201": BearingSpec(id=12, od=32, width=10),
    "6202": BearingSpec(id=15, od=35, width=11),
    "6203": BearingSpec(id=17, od=40, width=12),
    "6204": BearingSpec(id=20, od=47, width=14),
    "6205": BearingSpec(id=25, od=52, width=15),
}


def get_bearing_spec(series: str) -> BearingSpec:
    """Look up a BearingSpec by series number (e.g. ``"608"``)."""
    spec = BEARING_DATA.get(series)
    if spec is None:
        raise ValidationError(
            f"unknown bearing series {series!r}. "
            f"Available: {sorted(BEARING_DATA)}"
        )
    return spec


class Bearing(Component):
    """Ball bearing dummy for fit-check and visualization.

    Specify ``spec=BearingSpec(id=, od=, width=)`` for custom sizes, or
    use ``Bearing.of("608")`` for canned 6xx-series dimensions.
    Centered on the origin, bore along z.

    The caller can read ``id``, ``od``, ``width`` off the instance.
    """

    spec = Param(BearingSpec)
    equations = [
        "id = spec.id",
        "od = spec.od",
        "width = spec.width",
    ]

    @classmethod
    def of(cls, series: str, **kwargs):
        """Build a Bearing from a 6xx-series string (e.g. ``"608"``)."""
        return cls(spec=get_bearing_spec(series), **kwargs)

    def build(self):
        return Tube(h=self.width, od=self.od, id=self.id)
