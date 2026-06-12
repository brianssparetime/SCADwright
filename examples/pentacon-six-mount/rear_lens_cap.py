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

    The cup bore admits the lens barrel and sinks it into a well deep
    enough that the barrel's back, which runs on past the lugs, clears
    the closed disc. Each lug channel is cut in two passes: an entry slot
    the lug drops through, run the full way down to the post groove, and a
    lug-tall rotation channel sweeping `lock_twist_deg` to one side of it.
    A separate, narrower groove deeper in the well, at the same radial
    depth as the lug channels, lets the lens's orientation post turn clear
    of them; the post drops to it through the same entry slot as its lug.
    The wall left above the rotation channel is the retaining roof; the
    wall left below is the floor the lug rests on.
    """

    # The shared bayonet spec flows in as one parameter; the equations read
    # its values (including its derived `bore_r` and `lug_tip_r`) with a
    # `spec.` prefix.
    spec = Param()

    equations = """
        cap_wall, disc_thk, axial_clear > 0
        barrel_clear, post_axial_clear, entry_clear > 0
        bore_clear, lug_radial_clear > 0
        aperture_pin_clear >= 0
        # Bore the barrel passes through, plus its own slip-fit gap. This
        # radius is also the inner wall of the lug/post channels.
        bore_cut_r = spec.bore_r + bore_clear
        # Outer wall of the lug channels: the lug tip plus the fit gap and
        # the extra radial room the lug turns in.
        channel_outer_r = spec.lug_tip_r + spec.fit_clearance + lug_radial_clear
        channel_mid_r = (bore_cut_r + channel_outer_r) / 2
        channel_band = channel_outer_r - bore_cut_r
        channel_band > 0
        # Sink the lens far enough that its barrel, and the aperture pin
        # swinging behind it, both clear the closed disc: the barrel's reach
        # past the lugs, a comfort gap, plus room for the aperture pin.
        barrel_well = spec.barrel_past_lugs + barrel_clear + aperture_pin_clear
        # The lugs rest a well's depth above the disc; this is that plane.
        lug_floor = disc_thk + barrel_well
        # The orientation post turns in a groove cut to the same radial depth
        # as the lug channels, a touch taller than the post is wide so it
        # turns freely (its width is pin_dia, not adjusted).
        post_axial = spec.pin_dia + axial_clear + post_axial_clear
        # The post sits centered in the barrel's reach past the lugs, so its
        # groove is sunk this far below the lug floor, down in the well and
        # clear of the lug channels.
        pin_center_axial = spec.barrel_past_lugs / 2
        post_center_z = lug_floor - pin_center_axial
        cap_od = 2 * (channel_outer_r + cap_wall)
        # The rim seats against the lens shoulder, which the mount fixes a set
        # distance above the lug face. The wall left between the rotation
        # channel and that rim is the retaining roof.
        roof_thk = spec.axial_lug_face_to_lens_shoulder - axial_clear
        roof_thk > 0
        cap_h = lug_floor + spec.lug_axial + axial_clear + roof_thk
    """

    # Mount type label raised on the closed-back (z = 0) face.
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
        # Lugs rest a well's depth above the disc, so the barrel running on
        # past them has room to sink toward the closed bottom.
        floor = self.lug_floor
        # Rotation-channel half-width (the locked fit): the lug's own
        # half-width plus the fit gap, in degrees at the channel.
        half = self.spec.lug_span_deg / 2 + math.degrees(self.spec.fit_clearance / self.channel_mid_r)
        # Entry slot is widened by `entry_clear` per side so the lugs drop in
        # without binding; the locked fit above stays at `half`.
        half_entry = half + math.degrees(self.entry_clear / self.channel_mid_r)
        # The post spans its width circumferentially at the bore edge.
        post_half = math.degrees((self.spec.pin_dia / 2 + self.spec.fit_clearance) / self.spec.bore_r)
        # Bottom of the post groove, centered in the barrel well.
        post_bot = self.post_center_z - self.post_axial / 2
        twist = self.spec.lock_twist_deg

        # Cup: a wall whose bore admits the lens barrel, closed at the
        # bottom by a solid disc.
        solid = union(
            Tube(h=self.cap_h, od=self.cap_od, id=self.spec.bore_dia + 2 * self.bore_clear),
            cylinder(h=self.disc_thk, r=self.cap_od / 2),
        )

        band = dict(r=self.channel_mid_r, width=self.channel_band)
        cutters = []
        for k in range(int(self.spec.lug_count)):
            center = k * self.spec.lug_step_deg
            # Entry slot: the wide drop-in column, run all the way down to the
            # post groove so the lug and the post below it enter through this
            # one slot.
            cutters.append(
                Arc(angles=(center - half_entry, center + half_entry), **band)
                .linear_extrude(height=self.cap_h - post_bot + eps)
                .up(post_bot)
            )
            # Rotation channel: a lug-tall band sweeping `twist` to one
            # side of the entry slot. The intact wall above it is the
            # roof; the intact wall past its far end is the stop.
            cutters.append(
                Arc(angles=(center - half, center + half + twist), **band)
                .linear_extrude(height=self.spec.lug_axial + self.axial_clear)
                .up(floor)
            )
            # Post groove: same radial band as the lug channels, centered in
            # the barrel well below them. It sweeps the same `twist`, so the
            # post turns in its own groove nearer the disc.
            cutters.append(
                Arc(angles=(center - post_half, center + post_half + twist), **band)
                .linear_extrude(height=self.post_axial)
                .up(post_bot)
            )
        # Raised mount type label on the closed-back (z = 0) face.
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
    axial_clear = 0.5     # vertical slack for the lug and post in their channels
    barrel_clear = 0.5    # comfort gap below the lugs for the barrel's back
    aperture_pin_clear = 10.0  # extra well depth so the lens's aperture pin clears the disc
    post_axial_clear = 0.3  # extra axial slack on the post groove (atop axial_clear)
    entry_clear = 0.5     # extra circumferential room per side on the lug entry slots
    bore_clear = 0.6      # slip-fit gap per side on the bore (-> 61.2 mm ID)
    lug_radial_clear = 1.0  # extra radial room per side for the lug tip in its channel


class rear_lens_cap(Design):
    """The rear lens cap as a single printable part."""

    part = PentaconSixRearLensCap()

    @variant(fn=96, default=True)
    def cap(self):
        return self.part


if __name__ == "__main__":
    run()
