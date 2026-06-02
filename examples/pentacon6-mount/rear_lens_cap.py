"""Pentacon Six rear lens cap — protects the back of a lens.

This cap presents the *female* side of the bayonet: a cup whose wall has
three channels that the lens's male lugs drop into and then twist under.
Line the channels up with the lens lugs, drop the cap on, turn it 60
degrees, and a thin roof of plastic above each channel traps the lugs;
the uncut wall at the end of each channel is the stop.

`RearLensCap` is the reusable, parametric part; `PentaconSixRearLensCap`
pins its dimensions to the shared `spec.py`, so the channels here are cut
from the same lug spec the body cap renders as solid tabs.

Run:
    python examples/pentacon6-mount/rear_lens_cap.py
"""

import math

from scadwright import Component
from scadwright.api.tolerances import default_eps
from scadwright.boolops import difference, union
from scadwright.design import Design, run, variant
from scadwright.primitives import cylinder
from scadwright.shapes import Arc, Tube

from spec import PentaconSixMount


class RearLensCap(Component):
    """A closed cup with a three-channel twist-lock bayonet.

    The cup bore clears the lens barrel (and the lens's orientation
    post, which sits at the bore edge). Each channel is cut in two
    passes: a full-height entry slot the lug drops through, and a
    lug-tall rotation channel sweeping `lock_twist_deg` to one side of
    it. The wall left above the rotation channel is the retaining roof;
    the wall left below is the floor the lug rests on.
    """

    equations = """
        bore_dia, lug_radial, lug_axial, lug_span_deg, lug_step_deg, lock_twist_deg > 0
        cap_wall, disc_thk, roof_thk, axial_clear, lead_in, fit_clearance > 0
        lug_count >= 1
        bore_r = bore_dia / 2
        bore_cut_r = bore_r + fit_clearance
        lug_tip_r = bore_r + lug_radial
        channel_outer_r = lug_tip_r + fit_clearance
        channel_mid_r = (bore_cut_r + channel_outer_r) / 2
        channel_band = channel_outer_r - bore_cut_r
        channel_band > 0
        cap_od = 2 * (channel_outer_r + cap_wall)
        cap_h = disc_thk + lug_axial + axial_clear + roof_thk + lead_in
    """

    def build(self):                                       # framework hook: required; returns the shape
        eps = default_eps()
        floor = self.disc_thk
        # Angular half-width of an entry slot: the lug's own half-width
        # plus the fit gap, converted from mm to degrees at the channel.
        half = self.lug_span_deg / 2 + math.degrees(self.fit_clearance / self.channel_mid_r)
        twist = self.lock_twist_deg

        # Cup: a wall whose bore admits the lens barrel, closed at the
        # bottom by a solid disc.
        solid = union(
            Tube(h=self.cap_h, od=self.cap_od, id=self.bore_dia + 2 * self.fit_clearance),
            cylinder(h=self.disc_thk, r=self.cap_od / 2),
        )

        band = dict(r=self.channel_mid_r, width=self.channel_band)
        cutters = []
        for k in range(int(self.lug_count)):
            center = k * self.lug_step_deg
            # Entry slot: full height above the floor, so a lug drops in.
            cutters.append(
                Arc(angles=(center - half, center + half), **band)
                .linear_extrude(height=self.cap_h - floor + eps)
                .up(floor)
            )
            # Rotation channel: a lug-tall band sweeping `twist` to one
            # side of the entry slot. The intact wall above it is the
            # roof; the intact wall past its far end is the stop.
            cutters.append(
                Arc(angles=(center - half, center + half + twist), **band)
                .linear_extrude(height=self.lug_axial + self.axial_clear)
                .up(floor)
            )
        yield difference(solid, *cutters)


class PentaconSixRearLensCap(RearLensCap):
    """A rear lens cap dimensioned for the Pentacon Six mount.

    Every bayonet value is read straight from `PentaconSixMount`, the
    shared spec, so the twist-lock channels are sized from the same lug
    spec as the body cap. Only the cap's own print choices are set here.
    """

    # Bayonet contract — read from the shared spec.
    bore_dia       = PentaconSixMount.bore_dia
    lug_count      = PentaconSixMount.lug_count
    lug_span_deg   = PentaconSixMount.lug_span_deg
    lug_radial     = PentaconSixMount.lug_radial
    lug_axial      = PentaconSixMount.lug_axial
    lug_step_deg   = PentaconSixMount.lug_step_deg
    lock_twist_deg = PentaconSixMount.lock_twist_deg
    fit_clearance  = PentaconSixMount.fit_clearance

    # This cap's own print choices.
    cap_wall    = 2.5     # wall outside the lug channels
    disc_thk    = 2.0     # closed-end disc thickness
    roof_thk    = 1.2     # retaining roof above the rotation channels
    axial_clear = 0.3     # vertical slack for the lug in its channel
    lead_in     = 2.0     # extra rim height above the roof


class rear_lens_cap(Design):
    """The rear lens cap as a single printable part."""

    part = PentaconSixRearLensCap()

    @variant(fn=96, default=True)
    def cap(self):
        return self.part


if __name__ == "__main__":
    run()
