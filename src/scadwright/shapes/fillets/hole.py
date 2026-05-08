"""Countersink and Counterbore Components for screw holes."""

from __future__ import annotations

from scadwright.component.base import Component
from scadwright.component.anchors import anchor
from scadwright.primitives import polygon
from scadwright.shapes.fasteners.data import get_screw_spec


# Both Components are built as a single rotate_extrude of an L-shaped
# 2D profile rather than a union of two cylinders. The cylinder-stack
# approach has a coincident-face boundary at z=shaft_depth (the shaft's
# circular top is interior to the bore's wider circular bottom), which
# OpenSCAD's CSG can't classify cleanly when the Component is used as a
# difference cutter — the artifact is a wavering/blocky surface inside
# the resulting hole. Building the cutter as one solid via a closed
# 2D profile sidesteps the issue: there's no internal boundary by
# construction, and user-specified dimensions remain exact (no EPS).


class Countersink(Component):
    """Conical countersink profile for flat-head screws.

    Produces a stepped revolved solid: narrow shaft below, conical
    head recess above. The cone's wide end sits at the top of the
    shaft (z=shaft_depth) and narrows back to the shaft diameter at
    z=shaft_depth+head_depth.

    Publishes a ``tip`` anchor at z=0 pointing -z, matching the
    convention on ``Bolt`` — useful for ``part.attach(hole.tip)``.

    Use ``.through(parent)`` to auto-extend for clean cuts.
    """

    equations = "shaft_d, head_d, head_depth, shaft_depth > 0"

    tip = anchor(at=(0, 0, 0), normal=(0, 0, -1))

    def build(self):
        sd, hd = self.shaft_d / 2, self.head_d / 2
        z_step = self.shaft_depth
        z_top = self.shaft_depth + self.head_depth
        # Half-profile in the (r, z) plane, traversed CCW. The slanted
        # edge from (hd, z_step) to (sd, z_top) is the cone wall.
        return polygon(points=[
            (0.0, 0.0),
            (sd, 0.0),
            (sd, z_step),
            (hd, z_step),
            (sd, z_top),
            (0.0, z_top),
        ]).rotate_extrude()


class Counterbore(Component):
    """Cylindrical counterbore profile for socket-head screws.

    Produces a stepped revolved solid: narrow shaft below, wider
    cylindrical bore above. The shaft starts at z=0; the bore sits
    on top.

    Publishes a ``tip`` anchor at z=0 pointing -z, matching the
    convention on ``Bolt`` — useful for ``part.attach(hole.tip)``.

    Use ``.through(parent)`` to auto-extend for clean cuts.
    """

    equations = "shaft_d, head_d, head_depth, shaft_depth > 0"

    tip = anchor(at=(0, 0, 0), normal=(0, 0, -1))

    def build(self):
        sd, hd = self.shaft_d / 2, self.head_d / 2
        z_step = self.shaft_depth
        z_top = self.shaft_depth + self.head_depth
        # Half-profile in the (r, z) plane, traversed CCW.
        return polygon(points=[
            (0.0, 0.0),
            (sd, 0.0),
            (sd, z_step),
            (hd, z_step),
            (hd, z_top),
            (0.0, z_top),
        ]).rotate_extrude()


def counterbore_for_screw(
    size: str, shaft_depth: float, *, head: str = "socket"
) -> Counterbore:
    """Counterbore sized for a standard ISO metric screw of ``size``.

    Pulls clearance_d, head_d, and head_h from the ScrewSpec for the
    given size and head style. Use ``.through(parent)`` for clean cuts.
    """
    spec = get_screw_spec(size, head)
    return Counterbore(
        shaft_d=spec.clearance_d,
        head_d=spec.head_d,
        head_depth=spec.head_h,
        shaft_depth=shaft_depth,
    )


def countersink_for_screw(
    size: str, shaft_depth: float, *, head: str = "socket"
) -> Countersink:
    """Countersink sized for a standard ISO metric screw of ``size``.

    The cone diameter matches the screw's head_d; the shaft matches
    its clearance_d. Use ``.through(parent)`` for clean cuts.
    """
    spec = get_screw_spec(size, head)
    return Countersink(
        shaft_d=spec.clearance_d,
        head_d=spec.head_d,
        head_depth=spec.head_h,
        shaft_depth=shaft_depth,
    )
