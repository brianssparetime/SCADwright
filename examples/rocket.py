"""A 3D-printable rocket on a coiled-spring stand

Total: 59 lines of code in scadwright; ~360 in equivalent OpenSCAD.

By component (scadwright / openscad):

- Nose (Ogive Component → rotate_extrude):  3  / ~5
- Body (Barrel arc-revolved bulge):          1  / ~10
- Fins (polygon + Minkowski + attach):      16  / ~50
- Nozzle (Barrel + halve()):                 1  / ~15
- Helicoid (Helix + almond_profile):         7  / ~120
- Base plate (filleted cube):                3  / ~10
- Bolt-holes (M2 counterbores from ISO
  spec + 2x2 hole_grid + through()):         6  / ~25
- Engravings (two curved-meridian add_text
  calls; per-glyph proportional spacing
  and surface-tangent rotation; SCAD-1 +
  multi-line punchline):                     8  / ~90

Average: 6x reduction.

"""

from scadwright import bbox, render, resolution
from scadwright.boolops import difference, minkowski, union
from scadwright.composition_helpers import hole_grid
from scadwright.primitives import cube, polygon, sphere
from scadwright.shapes import (
    Barrel, Helix, Ogive, almond_profile, counterbore_for_screw,
)

body_h, body_r = 60, 10
body_bulge = 1.5  # convex barrel: mid radius is 1.5 mm wider than the rims
nozzle_h, nozzle_flare = 12, 3  # half-barrel nozzle below the fin line
barrel_h = body_h - nozzle_h

with resolution(fn=32):
    # Body = upper Barrel; nozzle = upper half of a fatter Barrel, halved
    # then lowered into place — flares outward going down to the rim.
    body = Barrel(h=barrel_h, end_r=body_r, bulge=body_bulge).up(nozzle_h)
    nozzle = Barrel(h=2*nozzle_h, end_r=body_r, bulge=nozzle_flare).down(nozzle_h).halve(z=1)
    # Parabolic ogive nose. r(z) = body_r * sqrt(1 - z/length); the
    # Component samples the meridian and rotate_extrudes it.
    nose = Ogive(base_r=body_r, length=18, kind="parabolic", fn=64).attach(
        body, on="top",
    )
    # Filleted M2-counterbored baseplate; hole_grid spreads the holes
    # into a centered 2x2 corner array; through() flushes the cuts.
    plate_w, plate_thk, stem_h = 22, 3, 18
    plate_solid = cube([plate_w, plate_w, plate_thk], center="xy").fillet("vertical", r=2)
    # through=plate_thk recesses the head bore inside the plate (head
    # top flush with plate top); .through() then eps-extends both faces.
    hole = counterbore_for_screw("M2", through=plate_thk)
    corner = plate_w/2 - 3
    holes = hole_grid(
        rows=2, cols=2,
        row_spacing=2*corner, col_spacing=2*corner,
        hole=hole,
    )
    plate = difference(plate_solid, holes.through(plate_solid, axis="z"))

    # Tapered Helix with almond cross-section. overhang=chord_r centers
    # the tilted endcaps on the plate/body joint planes, no fuse= needed.
    n_turns, chord_r, sag = 3, 1.5, 0.75
    stem = Helix(
        wire_profile=almond_profile(chord_r=chord_r, sag=sag),
        r=body_r - 2, r_end=4.0, pitch=stem_h/n_turns, turns=n_turns,
        overhang=chord_r, points_per_turn=64,
    ).up(plate_thk).color("gold")
    stand = union(plate, stem).down(plate_thk + stem_h)

# Parabolic-swept fins: polygon → linear_extrude → Minkowski sphere
# rounds the edges. attach reads the post-rotate bbox so the fin
# lands flush; .left(fin_fillet) embeds the body-side curve.
fin_fillet, edge_r, tip_back, n_curve = 2, 0.8, 12, 16
bw, bh = 14 - 2*edge_r, 22 - 2*edge_r
sweep = lambda x: tip_back * (x / bw)**2
fin_profile = (
    [(bw*i/n_curve, -sweep(bw*i/n_curve)) for i in range(n_curve + 1)]
    + [(bw*(1 - i/n_curve), bh*i/n_curve - sweep(bw*(1 - i/n_curve)))
       for i in range(1, n_curve + 1)]
)
fin_blank = minkowski(
    polygon(points=fin_profile).linear_extrude(height=2 - 2*edge_r),
    sphere(r=edge_r, fn=16),
).rotate([90, 0, 0])
fins = fin_blank.attach(
    body, on="outer_wall", using_anchor="lside",
    at_z=bbox(fin_blank).size[2]/2 - barrel_h/2 - nozzle_h,
).left(fin_fillet).rotate_copy(angle=120, n=3, axis=[0, 0, 1])

# Engraved labels: 
labeled_body = body.color("gold").add_text(
    label="SCADwright:", on="outer_wall", angle=45,
    font_size=2.5, spacing=1.2, relief=0.5, at_z = 16,
).add_text(
    label="Can your SCAD do\nthis in < 60 lines?",
    on="outer_wall", angle=45, text_dir="axial", rotate_glyphs=True,
    font_size=2.5, line_spacing=1.5, relief=-0.5, spacing=1.0, at_z = -3,
)

rocket = union(labeled_body, nose, stand, fins, nozzle)
render(rocket, "rocket.scad")
