"""Gridfinity base and bin Components.

Gridfinity is a modular storage system with a standardized 42mm grid.
These Components generate bases and bins compatible with the standard.

Geometry is driven by a `GridfinitySpec` namedtuple. Subclass a Component
and override `spec` to produce half-scale, double-wall, or any other
non-standard variant:

    class HalfScaleBase(GridfinityBase):
        spec = GridfinitySpec(grid_unit=21.0, ...)
"""

from __future__ import annotations

from collections import namedtuple

from scadwright.boolops import difference, union
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cube, cylinder


GridfinitySpec = namedtuple(
    "GridfinitySpec",
    "grid_unit base_height magnet_d magnet_h magnet_inset screw_d screw_h "
    "lip_height wall_thk bottom_thk height_unit bin_clearance",
)


STANDARD_GRIDFINITY = GridfinitySpec(
    grid_unit=42.0,
    base_height=5.0,
    magnet_d=6.0,
    magnet_h=2.4,
    magnet_inset=4.0,
    screw_d=3.0,
    screw_h=6.0,
    lip_height=4.4,
    wall_thk=1.2,
    bottom_thk=1.0,
    height_unit=7.0,
    bin_clearance=0.5,
)


class GridfinityBase(Component):
    """Gridfinity baseplate.

    ``grid_x`` and ``grid_y`` set the grid size (in units, e.g. 3x2).
    The base has magnet holes at each grid intersection and screw
    holes in the center of each cell. Override ``spec`` for non-standard
    grid sizes or custom magnet/screw dimensions.
    """

    grid_x = Param(int, min=1)
    grid_y = Param(int, min=1)
    spec = Param(GridfinitySpec, default=STANDARD_GRIDFINITY)

    def setup(self):                                    # framework hook: optional
        s = self.spec
        self.outer_w = self.grid_x * s.grid_unit
        self.outer_l = self.grid_y * s.grid_unit

    def build(self):
        s = self.spec
        plate = cube([self.outer_w, self.outer_l, s.base_height])
        cutters = []

        for gx in range(self.grid_x):
            for gy in range(self.grid_y):
                cx = (gx + 0.5) * s.grid_unit
                cy = (gy + 0.5) * s.grid_unit

                # Screw hole in center of each cell.
                cutters.append(
                    cylinder(h=s.screw_h, d=s.screw_d).translate([cx, cy, 0])
                )

                # Magnet holes at each corner of each cell.
                for dx in (-1, 1):
                    for dy in (-1, 1):
                        mx = cx + dx * (s.grid_unit / 2 - s.magnet_inset)
                        my = cy + dy * (s.grid_unit / 2 - s.magnet_inset)
                        cutters.append(
                            cylinder(h=s.magnet_h, d=s.magnet_d).translate([mx, my, 0])
                        )

        if cutters:
            return difference(plate, union(*cutters).through(plate))
        return plate


class GridfinityBin(Component):
    """Gridfinity storage bin.

    ``grid_x``, ``grid_y`` set the footprint in grid units.
    ``height_units`` sets the bin height in spec-defined increments
    (standard: 7mm). ``dividers_x`` splits the bin into compartments
    along x. Override ``spec`` for non-standard variants.
    """

    grid_x = Param(int, min=1)
    grid_y = Param(int, min=1)
    height_units = Param(int, min=1)
    dividers_x = Param(int, default=1, min=1)
    spec = Param(GridfinitySpec, default=STANDARD_GRIDFINITY)

    def setup(self):                                    # framework hook: optional
        s = self.spec
        self.outer_w = self.grid_x * s.grid_unit - s.bin_clearance
        self.outer_l = self.grid_y * s.grid_unit - s.bin_clearance
        self.total_h = self.height_units * s.height_unit + s.lip_height

    def build(self):
        s = self.spec
        outer = cube([self.outer_w, self.outer_l, self.total_h])
        inner_w = self.outer_w - 2 * s.wall_thk
        inner_l = self.outer_l - 2 * s.wall_thk
        inner_h = self.total_h - s.bottom_thk
        inner = cube([inner_w, inner_l, inner_h]).translate(
            [s.wall_thk, s.wall_thk, s.bottom_thk]
        )
        shell = difference(outer, inner.through(outer))

        if self.dividers_x > 1:
            divider_spacing = inner_w / self.dividers_x
            dividers = []
            for i in range(1, self.dividers_x):
                x = s.wall_thk + i * divider_spacing - s.wall_thk / 2
                dividers.append(
                    cube([s.wall_thk, inner_l, inner_h]).translate(
                        [x, s.wall_thk, s.bottom_thk]
                    )
                )
            return union(shell, *dividers)

        return shell
