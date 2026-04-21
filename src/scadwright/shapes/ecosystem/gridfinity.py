"""Gridfinity base and bin Components.

Gridfinity is a modular storage system with a standardized 42mm grid.
These Components generate bases and bins compatible with the standard.
"""

from __future__ import annotations


from scadwright.boolops import difference, union
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cube, cylinder


# Gridfinity standard dimensions (mm).
GRID_UNIT = 42.0
BASE_HEIGHT = 5.0
MAGNET_D = 6.0
MAGNET_H = 2.4
SCREW_D = 3.0
SCREW_H = 6.0
LIP_HEIGHT = 4.4
WALL_THK = 1.2
BOTTOM_THK = 1.0
FILLET_R = 0.8


class GridfinityBase(Component):
    """Gridfinity baseplate.

    ``grid_x`` and ``grid_y`` set the grid size (in units, e.g. 3x2).
    The base has magnet holes at each grid intersection and screw
    holes in the center of each cell.
    """

    grid_x = Param(int, min=1)
    grid_y = Param(int, min=1)

    def setup(self):                                    # framework hook: optional
        self.outer_w = self.grid_x * GRID_UNIT
        self.outer_l = self.grid_y * GRID_UNIT

    def build(self):
        plate = cube([self.outer_w, self.outer_l, BASE_HEIGHT])
        cutters = []

        for gx in range(self.grid_x):
            for gy in range(self.grid_y):
                cx = (gx + 0.5) * GRID_UNIT
                cy = (gy + 0.5) * GRID_UNIT

                # Screw hole in center of each cell.
                cutters.append(
                    cylinder(h=SCREW_H, d=SCREW_D).translate([cx, cy, 0])
                )

                # Magnet holes at each corner of each cell.
                for dx in (-1, 1):
                    for dy in (-1, 1):
                        mx = cx + dx * (GRID_UNIT / 2 - 4.0)
                        my = cy + dy * (GRID_UNIT / 2 - 4.0)
                        cutters.append(
                            cylinder(h=MAGNET_H, d=MAGNET_D).translate([mx, my, 0])
                        )

        if cutters:
            return difference(plate, union(*cutters).through(plate))
        return plate


class GridfinityBin(Component):
    """Gridfinity storage bin.

    ``grid_x``, ``grid_y`` set the footprint in grid units.
    ``height_units`` sets the bin height in 7mm increments (standard).
    ``dividers_x`` splits the bin into compartments along x.
    """

    grid_x = Param(int, min=1)
    grid_y = Param(int, min=1)
    height_units = Param(int, min=1)
    dividers_x = Param(int, default=1, min=1)

    def setup(self):                                    # framework hook: optional
        self.outer_w = self.grid_x * GRID_UNIT - 0.5  # slight clearance
        self.outer_l = self.grid_y * GRID_UNIT - 0.5
        self.total_h = self.height_units * 7.0 + LIP_HEIGHT

    def build(self):
        outer = cube([self.outer_w, self.outer_l, self.total_h])
        inner_w = self.outer_w - 2 * WALL_THK
        inner_l = self.outer_l - 2 * WALL_THK
        inner_h = self.total_h - BOTTOM_THK
        inner = cube([inner_w, inner_l, inner_h]).translate(
            [WALL_THK, WALL_THK, BOTTOM_THK]
        )
        shell = difference(outer, inner.through(outer))

        if self.dividers_x > 1:
            divider_spacing = inner_w / self.dividers_x
            dividers = []
            for i in range(1, self.dividers_x):
                x = WALL_THK + i * divider_spacing - WALL_THK / 2
                dividers.append(
                    cube([WALL_THK, inner_l, inner_h]).translate([x, WALL_THK, BOTTOM_THK])
                )
            return union(shell, *dividers)

        return shell
