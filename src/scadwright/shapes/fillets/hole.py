"""Countersink and Counterbore Components for screw holes."""

from __future__ import annotations

from scadwright.component.base import Component
from scadwright.component.anchors import anchor
from scadwright.errors import ValidationError
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
    size: str,
    *,
    through: float | None = None,
    shaft_depth: float | None = None,
    head: str = "socket",
) -> Counterbore:
    """Counterbore sized for a standard ISO metric screw of ``size``.

    Pass exactly one of:

    - ``through=plate_thk`` — the thickness of the parent the screw
      goes through. The factory computes ``shaft_depth = through −
      head_h`` so the head bore sits *inside* the parent with its top
      face flush with the parent's top. ``.through(parent)`` then
      eps-extends both ends correctly; no coplanar shoulder.
    - ``shaft_depth=`` — the lower cylinder's height directly. Use this
      when the counterbore isn't sized to a host thickness (e.g. blind
      holes, custom stacks).

    Pulls ``clearance_d``, ``head_d``, and ``head_h`` from the
    ``ScrewSpec`` for the given size and head style.
    """
    if (through is None) == (shaft_depth is None):
        raise ValidationError(
            "counterbore_for_screw: pass exactly one of through= (the "
            "thickness of the parent the screw goes through, so the head "
            "bore is recessed inside it) or shaft_depth= (the lower "
            "cylinder's height directly, for non-through-hole cases)."
        )
    spec = get_screw_spec(size, head)
    if through is not None:
        if through < spec.head_h:
            raise ValidationError(
                f"counterbore_for_screw: through={through} is less than "
                f"the head height ({spec.head_h}) for {size!r} {head!r}; "
                f"the head bore alone wouldn't fit inside the parent. "
                f"Either thicken the host, or use shaft_depth= explicitly "
                f"for a deliberately-protruding head."
            )
        shaft_depth = through - spec.head_h
    return Counterbore(
        shaft_d=spec.clearance_d,
        head_d=spec.head_d,
        head_depth=spec.head_h,
        shaft_depth=shaft_depth,
    )


def countersink_for_screw(
    size: str,
    *,
    through: float | None = None,
    shaft_depth: float | None = None,
    head: str = "socket",
) -> Countersink:
    """Countersink sized for a standard ISO metric screw of ``size``.

    Pass exactly one of:

    - ``through=plate_thk`` — the thickness of the parent the screw
      goes through. The factory computes ``shaft_depth = through −
      head_h`` so the conical recess sits *inside* the parent with the
      cone's wide rim flush with the parent's top.
    - ``shaft_depth=`` — the lower cylinder's height directly.

    The cone diameter matches the screw's ``head_d``; the shaft matches
    its ``clearance_d``.
    """
    if (through is None) == (shaft_depth is None):
        raise ValidationError(
            "countersink_for_screw: pass exactly one of through= (the "
            "thickness of the parent the screw goes through, so the cone "
            "recess is inside it) or shaft_depth= (the lower cylinder's "
            "height directly, for non-through-hole cases)."
        )
    spec = get_screw_spec(size, head)
    if through is not None:
        if through < spec.head_h:
            raise ValidationError(
                f"countersink_for_screw: through={through} is less than "
                f"the head height ({spec.head_h}) for {size!r} {head!r}; "
                f"the cone recess alone wouldn't fit inside the parent."
            )
        shaft_depth = through - spec.head_h
    return Countersink(
        shaft_d=spec.clearance_d,
        head_d=spec.head_d,
        head_depth=spec.head_h,
        shaft_depth=shaft_depth,
    )
