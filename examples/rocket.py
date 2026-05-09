"""A 3D-printable rocket on a coiled-spring stand — scadwright brag.

Total: ~45 lines of code in scadwright; ~325 in equivalent OpenSCAD.

By component (scadwright / openscad):

- Nose (Ogive Component → rotate_extrude):  ~3  / ~5
- Body (Barrel arc-revolved bulge):         ~1  / ~10
- Fins (polygon + Minkowski + attach):      ~14 / ~50
- Nozzle (Barrel + halve()):                ~1  / ~15
- Helicoid (Helix + almond_profile):        ~5  / ~120
- Base plate (filleted cube):               ~3  / ~10
- Bolt-holes (M2 counterbores from ISO
  spec + 2x2 linear_copy + through()):      ~7  / ~25
- Engraving (curved-meridian add_text):     ~4  / ~50

Average: 7-8x reduction.

Showcases:

- Parabolic ogive nose via the ``Ogive`` Component (one line; the
  Component picks the meridian shape and emits a clean rotate_extrude).
- Coiled-spring stem: ``Helix`` Component with custom ``wire_profile=``
  (an ``almond_profile``), tapered ``r_end=``, and ``overhang=`` to
  bury the tilted endcaps in the plate and body.
- Half-barrel nozzle below the fin line: a fatter Barrel, ``.halve(z=1)``
  keeps the upper half — flares outward going down.
- Filleted M2-counterbored baseplate (Cube.fillet, Counterbore,
  nested linear_copy, through()).
- Parabolic backswept fins: sampled polygon → linear_extrude →
  Minkowski sphere for round edges.
- Surface-aware attach with axial offset (at_z=) on Barrel's
  meridional outer_wall anchor — the fin's body-side edge lands on
  the actual barrel surface.
- Auto-EPS at coincident faces (fuse=, through()).
- Radial copies via rotate_copy.
- Curved-meridian text wrap (add_text + meridian= + relief=).
- Per-feature fragmentation (with resolution(fn=...), per-call fn=).
"""

from scadwright import bbox, render, resolution
from scadwright.boolops import difference, minkowski, union
from scadwright.composition_helpers import linear_copy
from scadwright.primitives import cube, polygon, sphere
from scadwright.shapes import (
    Barrel, Helix, Ogive, almond_profile, counterbore_for_screw, get_screw_spec,
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
    # Parabolic ogive nose. r(z) = body_r * sqrt(1 - z/nose_h); the
    # Component samples the meridian and rotate_extrudes it.
    nose_h = 18
    nose = Ogive(base_r=body_r, length=nose_h, kind="parabolic", fn=64).attach(
        body, on="top",
    )
    # Filleted M2-counterbored baseplate; nested linear_copy spreads the
    # holes into a 2x2 corner array; through() flushes the cuts.
    plate_w, plate_thk, stem_h = 22, 3, 18
    plate_solid = cube([plate_w, plate_w, plate_thk], center="xy").fillet("vertical", r=2)
    head_h = get_screw_spec("M2", "socket").head_h
    hole = counterbore_for_screw("M2", shaft_depth=plate_thk - head_h)
    corner = plate_w/2 - 3
    holes = linear_copy(
        [0, 2*corner, 0], 2,
        linear_copy([2*corner, 0, 0], 2, hole.translate([-corner, -corner, 0])),
    )
    plate = difference(plate_solid, holes.through(plate_solid, axis="z"))

    # Tapered Helix with almond cross-section. overhang=chord_r centers
    # the tilted endcaps on the plate/body joint planes, no fuse= needed.
    n_turns, chord_r, sag = 3, 1.5, 0.75
    stem = Helix(
        wire_profile=almond_profile(chord_r=chord_r, sag=sag),
        r=body_r - 2, r_end=4.0, pitch=stem_h/n_turns, turns=n_turns,
        overhang=chord_r, points_per_turn=64,
    ).up(plate_thk)
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
fin = fin_blank.attach(
    body, on="outer_wall", using_anchor="lside",
    at_z=bbox(fin_blank).size[2]/2 - barrel_h/2 - nozzle_h,
).left(fin_fillet)
fins = fin.rotate_copy(angle=120, n=3, axis=[0, 0, 1])

# Engraved label wraps around the cylinder.
labeled_body = body.add_text(
    label="SCAD-1", on="outer_wall", meridian=0,
    font_size=4, spacing=1.6, relief=-0.4,
)

rocket = union(labeled_body, nose, stand, fins, nozzle)
render(rocket, "rocket.scad")
