"""Locator-joint Components: AlignmentPin, PressFitPeg."""

from __future__ import annotations

from scadwright.boolops import union
from scadwright.component.anchors import anchor
from scadwright.component.base import Component
from scadwright.component.params import Param
from scadwright.primitives import cylinder


class AlignmentPin(Component):
    """Cylindrical locator pin with a tapered lead-in tip.

    For location only (not load-bearing): the pin slides into a matching
    socket with a lead-in chamfer for easy engagement. Typically used in
    pairs to constrain two parts' relative position while other features
    (screws, clips) provide retention.

    Sits on z=0 with its tip at z=``h``. Publishes ``socket_d``
    (= ``d`` + 2*``clearance``) and a ``.socket`` @property returning
    the matching blind-hole cutter.
    """

    equations = [
        "d, h, lead_in > 0",
        "clearance >= 0",
        "socket_d == d + 2 * clearance",
        "lead_in < h",
        "lead_in < d / 2",
    ]
    clearance = Param(float, default=0.1)

    base = anchor(at=(0, 0, 0), normal=(0, 0, -1))
    tip = anchor(at="0, 0, h", normal=(0, 0, 1))

    def build(self):
        body_h = self.h - self.lead_in
        r = self.d / 2
        body = cylinder(h=body_h, r=r)
        tapered_tip = cylinder(
            h=self.lead_in,
            r1=r,
            r2=r - self.lead_in,
        ).up(body_h)
        return union(body, tapered_tip)

    @property
    def socket(self):
        """Cutter for the matching blind hole (same height as the pin)."""
        return cylinder(h=self.h, r=self.socket_d / 2)


class PressFitPeg(Component):
    """Flanged pin for press-fit sheet-to-sheet assembly.

    A shaft with a broader flange at its base and a tapered lead-in at
    its tip. The flange seats against one sheet; the shaft passes through
    a matching hole (sized ``interference`` smaller than the shaft on
    each side) in the opposing sheet and holds by friction.

    Flange sits on z=0; the shaft rises from z=``flange_h``; the tip is
    at z=``flange_h`` + ``shaft_h``. Publishes ``socket_d``
    (= ``shaft_d`` - 2*``interference``) and a ``.socket`` @property
    returning the matching through-hole cutter.
    """

    equations = [
        "shaft_d, shaft_h, flange_d, flange_h, lead_in > 0",
        "interference >= 0",
        "socket_d == shaft_d - 2 * interference",
        "flange_d > shaft_d",
        "lead_in < shaft_h",
        "lead_in < shaft_d / 2",
    ]
    interference = Param(float, default=0.1)

    seat = anchor(at="0, 0, flange_h", normal=(0, 0, -1))
    tip = anchor(at="0, 0, flange_h + shaft_h", normal=(0, 0, 1))

    def build(self):
        flange = cylinder(h=self.flange_h, r=self.flange_d / 2)
        shaft_body_h = self.shaft_h - self.lead_in
        shaft_body = cylinder(h=shaft_body_h, r=self.shaft_d / 2).up(self.flange_h)
        shaft_tip = cylinder(
            h=self.lead_in,
            r1=self.shaft_d / 2,
            r2=self.shaft_d / 2 - self.lead_in,
        ).up(self.flange_h + shaft_body_h)
        return union(flange, shaft_body, shaft_tip)

    @property
    def socket(self):
        """Through-hole cutter sized for interference fit with the shaft."""
        return cylinder(h=self.shaft_h, r=self.socket_d / 2)
