"""Torus and Elbow Components."""

from __future__ import annotations

from scadwright.boolops import difference
from scadwright.component.anchors import anchor
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.extrusions import rotate_extrude
from scadwright.primitives import circle


class Torus(Component):
    """Torus (donut) centered on the origin in the XY plane.

    ``major_r`` is the distance from the center of the torus to the
    center of the tube. ``minor_r`` is the tube radius. Optional
    ``angle`` sweeps a partial torus (default 360 for a full ring).
    """

    equations = """
        major_r, minor_r > 0
        ?angle = ?angle or 360.0
        angle > 0
        angle <= 360
        minor_r < major_r
    """

    def build(self):
        cross = circle(r=self.minor_r).right(self.major_r)
        return rotate_extrude(cross, angle=self.angle)


class Elbow(Component):
    """Hollow pipe bend — partial torus with wall thickness.

    Two ends, both perpendicular to the tube axis at their respective
    sweep angles. ``id``/``od``/``thk`` are coupled by
    ``od = id + 2·thk``; specify any two. ``bend_radius`` is the
    distance from the bend's center axis (the Z-axis) to the tube's
    centerline. ``angle`` is the swept angle in degrees, defaulting to
    90° (the most common pipe bend); ``angle ∈ (0, 360]``.

    The elbow sweeps CCW in the XY plane from angle=0 to angle=``angle``::

        Elbow(id=8, od=12, bend_radius=20)           # 90° default
        Elbow(id=8, thk=2, bend_radius=20, angle=180) # U-bend, od solved
        Elbow(od=12, thk=2, bend_radius=20)          # id solved

    Anchors ``start`` (at the angle=0 face) and ``end`` (at the
    angle=``angle`` face) point outward along their tube tangents and
    carry ``rim_radius=od/2``, so ``attach()`` lines up cleanly with
    another pipe end and ``add_text(on="start")`` arc-on-rim works.

    The constraint ``od/2 < bend_radius`` prevents the tube from
    self-intersecting on the inner side of the bend — pick a
    ``bend_radius`` larger than the tube's outer radius.
    """

    equations = """
        od = id + 2*thk
        id, od, thk > 0
        bend_radius > 0
        ?angle = ?angle or 90.0
        angle > 0
        angle <= 360
        od / 2 < bend_radius
        end_x = bend_radius * cos(angle)
        end_y = bend_radius * sin(angle)
        end_nx = -sin(angle)
        end_ny = cos(angle)
    """

    start = anchor(
        at="bend_radius, 0, 0",
        normal=(0.0, -1.0, 0.0),
        kind="planar",
        surface_params={
            "axis": (0.0, 1.0, 0.0),
            "meridian_zero": (1.0, 0.0, 0.0),
            "rim_radius": "od/2",
        },
    )
    end = anchor(
        at="end_x, end_y, 0",
        normal="end_nx, end_ny, 0",
        kind="planar",
        surface_params={
            "axis": "end_nx, end_ny, 0",
            "meridian_zero": (0.0, 0.0, 1.0),
            "rim_radius": "od/2",
        },
    )

    def build(self):
        outer = circle(r=self.od / 2.0).right(self.bend_radius)
        inner = circle(r=self.id / 2.0).right(self.bend_radius)
        return difference(
            rotate_extrude(outer, angle=self.angle),
            rotate_extrude(inner, angle=self.angle),
        )

    def tight_bbox(self):
        # The bore is an interior cut from the partial torus; the outer
        # rotate_extrude's bbox is tight.
        from scadwright.bbox import bbox
        return bbox(self)
