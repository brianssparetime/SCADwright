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
    python examples/pentacon-six-mount/rear_lens_cap.py
"""

import math

from scadwright import Component, Param
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

    # The shared bayonet spec flows in as one parameter; the equations read
    # its values (including its derived `bore_r` and `lug_tip_r`) with a
    # `spec.` prefix.
    spec = Param()

    equations = """
        cap_wall, disc_thk, roof_thk, axial_clear, lead_in > 0
        bore_cut_r = spec.bore_r + spec.fit_clearance
        channel_outer_r = spec.lug_tip_r + spec.fit_clearance
        channel_mid_r = (bore_cut_r + channel_outer_r) / 2
        channel_band = channel_outer_r - bore_cut_r
        channel_band > 0
        cap_od = 2 * (channel_outer_r + cap_wall)
        cap_h = disc_thk + spec.lug_axial + axial_clear + roof_thk + lead_in
    """

    # Maker's mark raised on the closed-back (z = 0) face.
    label_relief = 0.6
    label_size = 7.0

    def tight_bbox(self):                                  # framework hook: declare extents past the Difference
        # build() ends in a difference(), which the framework can't measure
        # without evaluating the CSG. The channels and bore all sit inside
        # the blank cup; the only thing past it is the raised back-face
        # label, which stands `label_relief` proud below z = 0.
        from scadwright import BBox
        r = self.cap_od / 2
        return BBox(min=(-r, -r, -self.label_relief), max=(r, r, self.cap_h))

    def build(self):                                       # framework hook: required; returns the shape
        eps = default_eps()
        floor = self.disc_thk
        # Angular half-width of an entry slot: the lug's own half-width
        # plus the fit gap, converted from mm to degrees at the channel.
        half = self.spec.lug_span_deg / 2 + math.degrees(self.spec.fit_clearance / self.channel_mid_r)
        twist = self.spec.lock_twist_deg

        # Cup: a wall whose bore admits the lens barrel, closed at the
        # bottom by a solid disc.
        solid = union(
            Tube(h=self.cap_h, od=self.cap_od, id=self.spec.bore_dia + 2 * self.spec.fit_clearance),
            cylinder(h=self.disc_thk, r=self.cap_od / 2),
        )

        band = dict(r=self.channel_mid_r, width=self.channel_band)
        cutters = []
        for k in range(int(self.spec.lug_count)):
            center = k * self.spec.lug_step_deg
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
                .linear_extrude(height=self.spec.lug_axial + self.axial_clear)
                .up(floor)
            )
        # Raised maker's mark on the closed-back (z = 0) face.
        yield difference(solid, *cutters).add_text(
            label="Pentacon Six", on="bottom",
            relief=self.label_relief, font_size=self.label_size,
        )


class PentaconSixRearLensCap(RearLensCap):
    """A rear lens cap dimensioned for the Pentacon Six mount.

    `spec` binds the shared `PentaconSixMount`, so the `equations` read
    every bayonet value straight from it and the twist-lock channels match
    the body cap's lugs.
    """

    spec = PentaconSixMount

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
