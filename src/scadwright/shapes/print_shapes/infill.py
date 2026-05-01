"""Infill panel Components: honeycomb, grid, triangular grid."""

from __future__ import annotations

import math

from scadwright.boolops import difference, union
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.extrusions import linear_extrude
from scadwright.primitives import cube, polygon


class HoneycombPanel(Component):
    """Honeycomb infill panel: hex grid of holes in a rectangular slab.

    ``size`` is ``(x, y, z)`` outer dimensions. ``cell_size`` is the
    distance across flats of each hexagonal cell. ``wall_thk`` is the
    wall thickness between cells.
    """

    equations = """
        cell_size, wall_thk > 0
        len(size:tuple) = 3
    """

    def build(self):
        x, y, z = self.size
        slab = cube([x, y, z], center="xy")

        # Build a grid of hexagonal cutters.
        cs = self.cell_size
        wt = self.wall_thk
        pitch = cs + wt
        hex_r = cs / (2 * math.cos(math.pi / 6))  # circumradius

        # Hex profile.
        hex_pts = [
            (hex_r * math.cos(math.pi / 6 + i * math.pi / 3),
             hex_r * math.sin(math.pi / 6 + i * math.pi / 3))
            for i in range(6)
        ]
        hex_profile = polygon(points=hex_pts)
        hex_cutter = linear_extrude(hex_profile, height=z)

        cutters = []
        row_height = pitch * math.sin(math.pi / 3)
        cols = int(x / pitch) + 2
        rows = int(y / row_height) + 2

        for row in range(rows):
            for col in range(cols):
                cx = col * pitch + (pitch / 2 if row % 2 else 0) - x / 2
                cy = row * row_height - y / 2
                cutters.append(hex_cutter.translate([cx, cy, 0]))

        if not cutters:
            return slab
        return difference(slab, union(*cutters).through(slab))


class GridPanel(Component):
    """Rectangular grid infill panel: square holes in a slab.

    ``size`` is ``(x, y, z)``. ``cell_size`` and ``wall_thk`` control
    the grid spacing.
    """

    equations = """
        cell_size, wall_thk > 0
        len(size:tuple) = 3
    """

    def build(self):
        x, y, z = self.size
        slab = cube([x, y, z], center="xy")

        cs = self.cell_size
        wt = self.wall_thk
        pitch = cs + wt

        cutters = []
        cols = int(x / pitch) + 1
        rows = int(y / pitch) + 1
        cell = cube([cs, cs, z])

        for row in range(rows):
            for col in range(cols):
                cx = col * pitch + wt / 2 - x / 2
                cy = row * pitch + wt / 2 - y / 2
                cutters.append(cell.translate([cx, cy, 0]))

        if not cutters:
            return slab
        return difference(slab, union(*cutters).through(slab))


class TriGridPanel(Component):
    """Triangular grid infill panel: triangular holes in a slab.

    ``size`` is ``(x, y, z)``. ``cell_size`` is the triangle side
    length. ``wall_thk`` is wall thickness.
    """

    equations = """
        cell_size, wall_thk > 0
        len(size:tuple) = 3
    """

    def build(self):
        x, y, z = self.size
        slab = cube([x, y, z], center="xy")

        cs = self.cell_size
        wt = self.wall_thk
        # Equilateral triangle height.
        h_tri = cs * math.sqrt(3) / 2
        pitch_x = cs + wt
        pitch_y = h_tri + wt

        cutters = []
        cols = int(x / pitch_x) + 2
        rows = int(y / pitch_y) + 2

        for row in range(rows):
            for col in range(cols):
                cx = col * pitch_x + (pitch_x / 2 if row % 2 else 0) - x / 2
                cy = row * pitch_y - y / 2
                # Upward-pointing triangle.
                tri = polygon(points=[
                    (-cs / 2, 0),
                    (cs / 2, 0),
                    (0, h_tri),
                ])
                cutters.append(
                    linear_extrude(tri, height=z).translate([cx, cy, 0])
                )

        if not cutters:
            return slab
        return difference(slab, union(*cutters).through(slab))
