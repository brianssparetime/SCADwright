"""TubeClamp: saddle or split clamp for round or rectangular tubes."""

from __future__ import annotations

from scadwright.boolops import difference
from scadwright.component.anchors import anchor
from scadwright.component.base import Component
from scadwright.composition_helpers import linear_copy
from scadwright.primitives import cube, cylinder
from scadwright.shapes.fasteners import clearance_hole


class TubeClamp(Component):
    """Clamp that holds a tube against a parent surface.

    Two cross-sections (round via ``tube_d``, or rectangular via
    ``tube_w`` plus optional ``tube_h``; ``tube_h`` defaults to
    ``tube_w`` for square tubes), and two styles:

    - ``"saddle"`` — open-top cradle. The tube rests in a semicircular
      (round) or rectangular pocket cut into the top of a block.
      Mounting bolts pass through the body on either side of the tube
      into a parent below. A second piece (strap, cap, or another
      saddle) is needed to hold the tube down.
    - ``"split"`` — full enclosure with a saw-cut and a perpendicular
      pinch bolt that draws the two halves together, gripping the
      tube. The saw cut runs vertically through the body's centerline
      from the top down to just above the bottom wall, so the bottom
      ``wall_thk`` slice acts as a flex hinge (vise-jaw style). The
      pinch bolt is a horizontal clearance hole above the bore;
      tightening it closes the saw cut. Mounting bolts pass through
      the body below.

    Common applications: drone-frame arm mounts, conduit and PVC pipe
    holders, garden-hose mounts, cable bundle clamps, robot-arm members,
    telescope tube saddles.

    The clamp's tube axis runs along +X. The base sits on z=0 so the
    bbox-derived ``bottom`` anchor is the mount-to-parent face.
    """

    equations = """
        exactly_one(?tube_d, ?tube_w)
        ?tube_d > 0
        ?tube_w > 0
        ?tube_h = ?tube_h or ?tube_w
        ?tube_h > 0
        clamp_length > 0
        wall_thk > 0
        bolt_offset > 0
        ?screw:str = ?screw or "M3"
        ?n_bolts:int = ?n_bolts or 2
        n_bolts in (2, 4)
        ?style:str = ?style or "saddle"
        style in ("saddle", "split")
        ?saw_cut_width = ?saw_cut_width or 0.5
        ?bolt_axial_inset = ?bolt_axial_inset or (wall_thk + 2)
    """

    def _cross_section(self) -> tuple[float, float, bool]:
        """Return (cradle_w, cradle_h, is_round)."""
        if self.tube_d is not None:
            return self.tube_d, self.tube_d, True
        return self.tube_w, self.tube_h, False

    def _body_dimensions(self) -> tuple[float, float, float]:
        """Return (length, width, height) of the outer block."""
        cradle_w, cradle_h, _ = self._cross_section()
        length = self.clamp_length
        width = cradle_w + 2 * self.bolt_offset + 2 * self.wall_thk
        if self.style == "saddle":
            height = self.wall_thk + cradle_h
        else:
            height = cradle_h + 2 * self.wall_thk
        return length, width, height

    def _mounting_bolts(self, body_h: float):
        """Build the n_bolts mounting-bolt cutters. Bolts go along -Z
        through the body, accessed from below.
        """
        cradle_w, _, _ = self._cross_section()
        bolt_y = cradle_w / 2 + self.bolt_offset
        hole = clearance_hole(self.screw, depth=body_h + 2).down(1)
        if self.n_bolts == 2:
            return hole.back(bolt_y).mirror_copy(normal=(0, 1, 0))
        # n_bolts == 4
        bolt_x = self.clamp_length / 2 - self.bolt_axial_inset
        corners = hole.right(bolt_x).back(bolt_y)
        return corners.mirror_copy(normal=(1, 0, 0)).mirror_copy(normal=(0, 1, 0))

    def _saddle(self):
        cradle_w, cradle_h, is_round = self._cross_section()
        length, width, height = self._body_dimensions()
        body = cube([length, width, height], center="xy")
        tube_center_z = self.wall_thk + cradle_h / 2

        # Cradle cut: extends above the body top so the cradle opens
        # upward.
        if is_round:
            # Round cradle: a cylinder along +X, centered at the tube
            # axis. Its top sits exactly at the body top (the half above
            # the axis is cut away, leaving the U-shape).
            cutter = (
                cylinder(h=length + 2, r=cradle_h / 2)
                .rotate([0, 90, 0])
                .up(tube_center_z)
            )
        else:
            # Rectangular pocket: cube cutter cradle_w wide. Total
            # cutter height = cradle_h (pocket depth) + 1 mm
            # overpenetration above the body top so the cradle opens
            # upward without leaving a 0-thickness lid.
            overhang = 1.0
            cutter_h = cradle_h + overhang
            cutter = (
                cube([length + 2, cradle_w, cutter_h], center="xy")
                .up(self.wall_thk + cutter_h / 2)
            )

        return difference(body, cutter, self._mounting_bolts(height))

    def _split(self):
        cradle_w, cradle_h, is_round = self._cross_section()
        length, width, height = self._body_dimensions()
        body = cube([length, width, height], center="xy")
        tube_center_z = height / 2

        # Tube bore: full cross-section cutout along +X, centered at
        # the body mid-height.
        if is_round:
            bore = (
                cylinder(h=length + 2, r=cradle_h / 2)
                .rotate([0, 90, 0])
                .up(tube_center_z)
            )
        else:
            bore = cube(
                [length + 2, cradle_w, cradle_h], center="xy",
            ).up(tube_center_z)

        # Saw cut: thin vertical slot from the top of the body down
        # through the bore's centerline and slightly past, splitting
        # the upper half into +Y and -Y halves. The cut runs along +X
        # for the full clamp length.
        saw_depth = height / 2 + cradle_h / 2 + 1
        saw_top = height + 1
        saw_bottom = saw_top - saw_depth
        saw = cube(
            [length + 2, self.saw_cut_width, saw_depth], center="xy",
        ).up((saw_top + saw_bottom) / 2)

        # Pinch bolt: horizontal clearance hole crossing the saw cut.
        # Located above the bore, axially centered. After
        # rotate([90,0,0]) the cylinder runs +Y starting at y=0; the
        # translate puts its base at y=-(width/2 + 1) so the cutter
        # spans the full body width with 1 mm overpenetration each end.
        pinch_z = tube_center_z + cradle_h / 2 + (height - (tube_center_z + cradle_h / 2)) / 2
        pinch = (
            clearance_hole(self.screw, depth=width + 2)
            .rotate([90, 0, 0])
            .translate([0, -width / 2 - 1, pinch_z])
        )

        return difference(
            body, bore, saw, pinch, self._mounting_bolts(height),
        )

    def build(self):
        if self.style == "saddle":
            return self._saddle()
        return self._split()

    def tight_bbox(self):
        from scadwright.bbox import bbox
        return bbox(self)
