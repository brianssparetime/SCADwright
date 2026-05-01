"""Snap-joint Components: SnapHook, SnapPin."""

from __future__ import annotations

from scadwright.boolops import difference, union
from scadwright.component.anchors import anchor
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cube, cylinder, polyhedron


class SnapHook(Component):
    """Cantilever snap-fit hook with a ramped barb.

    A vertical arm with a triangular barb on its +Y face near the top.
    The barb has a flat catch (bottom face, perpendicular to the arm)
    that grips a ledge, and a slanted ramp (top face) that deflects the
    arm during insertion.

    Arm: z=[0, arm_length], x=[-width/2, +width/2], y=[0, thk].
    Barb: on the +Y face at the top; catch at z=arm_length-hook_height,
    ramp terminating at z=arm_length, tip protruding to y=thk+hook_depth.

    A 45° ramp (typical) is ``hook_height == hook_depth``.
    """

    equations = """
        arm_length, hook_depth, hook_height, thk, width > 0
        hook_height <= arm_length
    """

    def build(self):
        arm = cube([self.width, self.thk, self.arm_length], center="x")

        # Triangular barb: prism with catch (bottom), ramp (slanted),
        # and back face coincident with the arm's front. Small overlap
        # into the arm (0.01) keeps the union manifold-clean.
        y_back = self.thk - 0.01
        y_tip = self.thk + self.hook_depth
        z_bot = self.arm_length - self.hook_height
        z_top = self.arm_length
        x = self.width / 2
        vertices = [
            (-x, y_back, z_bot),   # 0 L back-bottom (catch level, at arm front)
            (-x, y_tip, z_bot),    # 1 L tip (catch edge)
            (-x, y_back, z_top),   # 2 L back-top (ramp terminus)
            (+x, y_back, z_bot),   # 3 R back-bottom
            (+x, y_tip, z_bot),    # 4 R tip
            (+x, y_back, z_top),   # 5 R back-top
        ]
        faces = [
            [0, 2, 1],        # left triangle (normal -x)
            [3, 4, 5],        # right triangle (normal +x)
            [0, 1, 4, 3],     # catch (bottom, normal -z)
            [1, 2, 5, 4],     # ramp (slanted, normal toward +y+z)
            [0, 3, 5, 2],     # back (overlaps into arm, normal -y)
        ]
        barb = polyhedron(points=vertices, faces=faces)
        return union(arm, barb)


class SnapPin(Component):
    """Split-tined compliant pin with retaining barbs.

    A cylindrical pin with a vertical slot cut through its tip,
    dividing the upper portion into two flexible tines. Each tine
    carries an outward barb near the top; the barbs compress inward
    during insertion through a matching hole, then spring back to
    retain the pin on the far side.

    The slot runs along the pin's axis with width ``slot_width`` in x
    and depth ``slot_depth`` measured from the top; the two tines lie
    on +x and -x sides of the slot and flex inward under load. Barbs
    protrude radially outward in ±x by ``barb_depth`` and occupy
    ``barb_height`` of z-extent at the tip.

    ``socket_d`` (= ``d`` + 2*``clearance``) is available on the
    instance, and ``.socket`` is a @property returning the matching
    through-hole cutter. If not passed, ``clearance`` resolves from the
    active scope or ``DEFAULT_CLEARANCES.snap``. Typical FDM values are
    0.1–0.3 mm.
    """

    _clearance_category = "snap"

    equations = """
        d, h, slot_width, slot_depth, barb_depth, barb_height, clearance > 0
        socket_d = d + 2 * clearance
        slot_depth < h
        barb_height <= slot_depth
        slot_width < d
        barb_depth < d / 2
    """

    base = anchor(at=(0, 0, 0), normal=(0, 0, -1))
    tip = anchor(at="0, 0, h", normal=(0, 0, 1))

    def build(self):
        body = cylinder(h=self.h, r=self.d / 2)

        # Slot cutter: cube sized to the cylinder's diameter in y and the
        # requested depth in z. Its ±y faces land on the cylinder's ±d/2
        # bbox faces and its top face on z=h, so through(body) extends
        # those faces automatically — no manual EPS.
        slot_cutter = (
            cube([self.slot_width, self.d, self.slot_depth], center="x")
            .back(self.d / 2)
            .up(self.h - self.slot_depth)
            .through(body)
        )
        pin = difference(body, slot_cutter)

        barb_right = self._barb()
        barb_left = barb_right.mirror([1, 0, 0])
        return union(pin, barb_right, barb_left)

    def _barb(self):
        """Right-side (+x) barb. Mirror across x for the left barb."""
        r = self.d / 2
        bw = self.d * 0.5  # tangential (y) width of the barb
        x_back = r - 0.01  # slight inset for manifold overlap with tine
        x_tip = r + self.barb_depth
        z_bot = self.h - self.barb_height
        z_top = self.h
        y = bw / 2
        vertices = [
            (x_back, -y, z_bot),   # 0 back-bottom -y
            (x_tip,  -y, z_bot),   # 1 tip -y
            (x_back, -y, z_top),   # 2 back-top -y
            (x_back, +y, z_bot),   # 3 back-bottom +y
            (x_tip,  +y, z_bot),   # 4 tip +y
            (x_back, +y, z_top),   # 5 back-top +y
        ]
        faces = [
            [0, 2, 1],        # -y triangle (normal -y)
            [3, 4, 5],        # +y triangle (normal +y)
            [0, 1, 4, 3],     # catch (bottom, normal -z)
            [1, 2, 5, 4],     # ramp (slanted, normal toward +x+z)
            [0, 3, 5, 2],     # back (overlaps into tine, normal -x)
        ]
        return polyhedron(points=vertices, faces=faces)

    @property
    def socket(self):
        """Through-hole cutter sized to pin d + 2*clearance."""
        return cylinder(h=self.h, r=self.socket_d / 2)
