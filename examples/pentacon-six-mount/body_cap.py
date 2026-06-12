"""Pentacon Six body cap — protects the camera's open throat.

A body cap mimics the back of a lens. It presents the *male* side of the
bayonet: a skirt that drops into the camera throat with three
outward-projecting lugs, a barrel that runs on past the lugs toward the
camera as the lens's does, and a disc that covers the opening. The
camera's own locking collar clamps the lugs, so the printed part needs
nothing but the skirt, the lugs, and the cover.

`BodyCap` is the reusable, parametric part; `PentaconSixBodyCap` pins its
dimensions to the shared `spec.py` — the same file the rear lens cap
reads, so the lug pattern on both parts always matches.

Run:
    python examples/pentacon-six-mount/body_cap.py
"""

from scadwright import Component, Param
from scadwright.api.tolerances import default_eps
from scadwright.boolops import union
from scadwright.design import Design, run, variant
from scadwright.primitives import cylinder
from scadwright.shapes import Arc, Tube

from spec import PentaconSixMount


class BodyCap(Component):
    """Disc-capped skirt with three male bayonet lugs.

    The skirt is sized to drop into the throat with `fit_clearance` of
    slack; the lugs project outward so the camera's collar can grab them,
    exactly as a lens's lugs do. Past the lugs the skirt runs on toward
    the camera by the lens barrel's protrusion, so the cap reaches into a
    rear cap's barrel well just as the real lens would. `skirt_h` fixes
    the lug depth, so lengthening the barrel never moves the lugs.
    """

    # The shared bayonet spec flows in as one parameter; the equations read
    # its values with a `spec.` prefix.
    spec = Param()

    equations = """
        skirt_wall, skirt_h, disc_thk, disc_lip > 0
        spec.lug_axial < skirt_h
        # Skirt fills the throat at the measured bore, no slip-fit gap: the
        # camera's collar grips the lugs, so a snug barrel is wanted here.
        skirt_od = spec.bore_dia
        skirt_or = skirt_od / 2
        skirt_id = skirt_od - 2 * skirt_wall
        skirt_id > 0
        disc_od = spec.bore_dia + 2 * disc_lip
        # skirt_h sets how deep the lugs sit; the barrel then runs on past
        # them toward the camera by the lens's protrusion. This is the full
        # tube length, lugs included.
        skirt_full_h = skirt_h + spec.barrel_past_lugs
        # The lug face that lands on a rear cap's channel floor.
        lug_seat = disc_thk + skirt_h
    """

    # Mount type label raised on the outward cover face.
    label_relief = 0.6
    label_size = 7.0

    def build(self):                                       # framework hook: required; returns the shape
        eps = default_eps()
        # Cover disc sitting against the camera's flange face (z = 0).
        disc = cylinder(h=self.disc_thk, r=self.disc_od / 2)
        # Skirt dropping into the throat and running on past the lugs as
        # the lens barrel does, overlapping the disc slightly for a clean
        # union.
        skirt = (
            Tube(h=self.skirt_full_h, od=self.skirt_od, id=self.skirt_id)
            .up(self.disc_thk - eps)
        )
        # Three lugs at the lug depth `skirt_h` sets, partway down the
        # skirt. Each is an annular sector projecting outward from the
        # skirt wall by `lug_radial`, at one of the three 120-degree
        # positions. Sized off `lug_seat`, not the full tube, so the barrel
        # extension never shifts them.
        z_lug = self.lug_seat - self.spec.lug_axial
        half = self.spec.lug_span_deg / 2
        lugs = [
            Arc(
                r=self.skirt_or + self.spec.lug_radial / 2,
                width=self.spec.lug_radial,
                angles=(k * self.spec.lug_step_deg - half, k * self.spec.lug_step_deg + half),
            )
            .linear_extrude(height=self.spec.lug_axial)
            .up(z_lug)
            for k in range(int(self.spec.lug_count))
        ]
        # Raised mount type label on the outward cover face (z = 0).
        return union(disc, skirt, *lugs).add_text(
            label="Pentacon Six", on="bottom",
            relief=self.label_relief, font_size=self.label_size,
        )


class PentaconSixBodyCap(BodyCap):
    """A body cap dimensioned for the Pentacon Six mount.

    `spec` binds the shared `PentaconSixMount`, so the `equations` read
    every bayonet value straight from it and this cap can't disagree with
    the rear lens cap about the lug pattern.
    """

    spec = PentaconSixMount

    # This cap's own print choices.
    skirt_wall = 2.0     # skirt wall thickness (hollow, to save plastic)
    skirt_h    = 6.0     # depth from the disc to the lug plane
    disc_thk   = 2.0     # cover-disc thickness
    disc_lip   = 3.0     # how far the disc overhangs the throat


class body_cap(Design):
    """The body cap as a single printable part."""

    part = PentaconSixBodyCap()

    @variant(fn=96, default=True)
    def cap(self):
        return self.part


if __name__ == "__main__":
    run()
