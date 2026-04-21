"""Bearing dummy Components for fit-check and visualization."""

from __future__ import annotations

from collections import namedtuple

from scadwright.boolops import difference
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cylinder

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


class Bearing(Component):
    """Ball bearing dummy for fit-check and visualization.

    Specify ``series`` (e.g. ``"608"``) to look up standard dimensions,
    or provide ``id``, ``od``, ``width`` directly for non-standard sizes.

    The bearing is centered on the origin, bore along z.
    """

    series = Param(str, default=None)
    id = Param(float, default=None)
    od = Param(float, default=None)
    width = Param(float, default=None)

    def setup(self):                                    # framework hook: optional
        if self.series is not None:
            spec = BEARING_DATA.get(self.series)
            if spec is None:
                from scadwright.errors import ValidationError
                raise ValidationError(
                    f"Bearing: unknown series {self.series!r}. "
                    f"Available: {sorted(BEARING_DATA)}"
                )
            self.id = spec.id
            self.od = spec.od
            self.width = spec.width
        if self.id is None or self.od is None or self.width is None:
            from scadwright.errors import ValidationError
            raise ValidationError(
                "Bearing: specify series= or all of id=, od=, width="
            )

    def build(self):
        outer = cylinder(h=self.width, d=self.od)
        bore = cylinder(h=self.width, d=self.id).through(outer)
        return difference(outer, bore)
