"""Grommet: vibration-isolating sleeve that sits in a plate's hole."""

from __future__ import annotations

from scadwright.boolops import difference
from scadwright.component.anchors import anchor
from scadwright.component.base import Component
from scadwright.extrusions import rotate_extrude
from scadwright.primitives import polygon
from scadwright.shapes.fasteners import clearance_hole


class Grommet(Component):
    """Vibration-isolating sleeve that sits in a plate's hole.

    The barrel passes through the plate; flanges above and below sandwich
    the plate between ``z = flange_thk`` and ``z = flange_thk + plate_thk``.
    An optional equatorial groove around the barrel — set ``groove_depth``
    and ``groove_width`` — seats in the plate hole, useful for printable
    TPU grommets where the groove is what catches the plate edge.

    Sits centered on the origin with its axis along +Z. Total height is
    ``plate_thk + 2 * flange_thk``; bottom flange face at z=0, top flange
    face at z=total_h.

    Common applications: flight-controller soft-mounting on a drone
    frame, sensor isolation on machine equipment, panel-mount strain
    relief for cabling.
    """

    equations = """
        plate_thk > 0
        plate_hole_d > 0
        flange_d > plate_hole_d
        ?flange_thk = ?flange_thk or 0.6
        ?slip = ?slip or 0.1
        ?screw:str = ?screw or "M3"
        ?groove_depth = ?groove_depth or 0
        ?groove_width = ?groove_width or 0
        groove_depth >= 0
        groove_width >= 0
        2 * groove_depth < barrel_d
        groove_width < plate_thk
        barrel_d = plate_hole_d - 2 * slip
        total_h = plate_thk + 2 * flange_thk
    """

    top = anchor(
        at="0, 0, total_h",
        normal=(0.0, 0.0, 1.0),
        kind="planar",
        surface_params={
            "axis": (0.0, 0.0, 1.0),
            "meridian_zero": (1.0, 0.0, 0.0),
            "rim_radius": "flange_d / 2",
        },
    )
    bottom = anchor(
        at=(0.0, 0.0, 0.0),
        normal=(0.0, 0.0, -1.0),
        kind="planar",
        surface_params={
            "axis": (0.0, 0.0, 1.0),
            "meridian_zero": (1.0, 0.0, 0.0),
            "rim_radius": "flange_d / 2",
        },
    )

    def build(self):
        flange_r = self.flange_d / 2.0
        barrel_r = self.barrel_d / 2.0
        ft = self.flange_thk
        pt = self.plate_thk
        total = self.total_h

        # Silhouette polygon in (r, z) from the axis outward and back.
        # CCW order keeps rotate_extrude facing outward.
        pts: list[tuple[float, float]] = [
            (0.0, 0.0),
            (flange_r, 0.0),
            (flange_r, ft),
            (barrel_r, ft),
        ]
        if self.groove_depth > 0:
            groove_r = barrel_r - self.groove_depth
            gw = self.groove_width
            g_lo = ft + (pt - gw) / 2.0
            g_hi = ft + (pt + gw) / 2.0
            pts += [
                (barrel_r, g_lo),
                (groove_r, g_lo),
                (groove_r, g_hi),
                (barrel_r, g_hi),
            ]
        pts += [
            (barrel_r, ft + pt),
            (flange_r, ft + pt),
            (flange_r, total),
            (0.0, total),
        ]

        body = rotate_extrude(polygon(points=pts))
        bore = clearance_hole(self.screw, depth=total + 2).down(1)
        return difference(body, bore)

    def tight_bbox(self):
        from scadwright.bbox import bbox
        return bbox(self)
