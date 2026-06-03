"""Pentacon Six body cap — protects the camera's open throat.

A body cap mimics the back of a lens. It presents the *male* side of the
bayonet: a short skirt that drops into the camera throat, three
outward-projecting lugs near the skirt's far end, and a disc that covers
the opening. The camera's own locking collar clamps the lugs, so the
printed part needs nothing but the skirt, the lugs, and the cover.

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
    slack; the lugs sit near its far end and project outward so the
    camera's collar can grab them, exactly as a lens's lugs do.
    """

    # The shared bayonet spec flows in as one parameter; the equations read
    # its values with a `spec.` prefix.
    spec = Param()

    equations = """
        skirt_wall, skirt_h, disc_thk, disc_lip > 0
        spec.lug_axial < skirt_h
        skirt_od = spec.bore_dia - 2 * spec.fit_clearance
        skirt_or = skirt_od / 2
        skirt_id = skirt_od - 2 * skirt_wall
        skirt_id > 0
        disc_od = spec.bore_dia + 2 * disc_lip
    """

    # Maker's mark raised on the outward cover face.
    label_relief = 0.6
    label_size = 7.0

    def build(self):                                       # framework hook: required; returns the shape
        eps = default_eps()
        # Cover disc sitting against the camera's flange face (z = 0).
        disc = cylinder(h=self.disc_thk, r=self.disc_od / 2)
        # Skirt dropping into the throat, overlapping the disc slightly
        # for a clean union.
        skirt = (
            Tube(h=self.skirt_h, od=self.skirt_od, id=self.skirt_id)
            .up(self.disc_thk - eps)
        )
        # Three lugs near the far end of the skirt. Each is an annular
        # sector projecting outward from the skirt wall by `lug_radial`,
        # at one of the three 120-degree positions.
        z_lug = self.disc_thk + self.skirt_h - self.spec.lug_axial
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
        # Raised maker's mark on the outward cover face (z = 0).
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
    skirt_h    = 6.0     # how deep the skirt reaches into the throat
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
