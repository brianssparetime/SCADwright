"""A 3D-printable rocket on a coiled-spring stand — scadwright brag.

Showcases (all in ~40 lines of actual code):

- Parabolic ogive nose: 2D polygon built from the parabola formula
  in a list comprehension, then rotate_extrude'd in one expression.
- Coiled-spring stem: an almond cross-section (two mirrored circular
  segments meeting on a chord) path_extrude'd along a tapered
  helix_path (radius funnels inward toward the rocket body). OpenSCAD
  has no native helical sweep — you'd build the polyhedron's vertices
  and faces by hand.
- Square baseplate with filleted vertical edges (Cube.fillet) and
  four M2 counterbore mounting holes — Counterbore Component, nested
  linear_copy for the 2x2 array, through() for clean cuts.
- Parabolic backswept fins: 2D profile sampled directly from a
  swept polygon (y = base_h·t − α·(base_w·(1−t))² along the leading
  edge), linear_extrude'd for thickness, with 3D edge rounding via
  Minkowski sum.
- Surface-aware attach with axial offset along a cylindrical wall
  (attach + at_z=), reading the post-rotate bbox so the fin lands
  flush despite the fillet's inset.
- Auto-EPS at every coincident face (attach + fuse=, through()).
- Radial copies via rotate_copy.
- Cylindrical text wrap (add_text with meridian= + relief= for
  engraving) — text follows the curved body, one call.
- Per-feature fragmentation: ``with resolution(fn=32)`` for the body
  and stand, ``fn=64`` on the nose rotate_extrude and fin Minkowski.

Run:
    python examples/rocket.py
"""

import math

from scadwright import bbox, render, resolution
from scadwright.boolops import difference, minkowski, union
from scadwright.composition_helpers import linear_copy
from scadwright.primitives import cube, cylinder, polygon, sphere
from scadwright.shapes import (
    counterbore_for_screw, get_screw_spec, helix_path, path_extrude,
)

body_h, body_r = 60, 10

# Body, nose, and engine bell at default fragmentation.
with resolution(fn=32):
    body = cylinder(h=body_h, r=body_r)
    # Parabolic nose: revolve a half-profile (r, z) where r = body_r * sqrt(1 - z/h).
    nose_h, n_pts = 18, 24
    nose = polygon(points=[(0.0, 0.0)] + [
        (body_r * math.sqrt(1 - i/n_pts), nose_h * i/n_pts) for i in range(n_pts + 1)
    ]).rotate_extrude(fn=64).attach(body, on="top")
    # Square baseplate with filleted vertical edges and four M2 socket-
    # head counterbore holes. counterbore_for_screw pulls clearance_d /
    # head_d / head_h from the ISO M-spec database — head sits flush
    # with the top face of the plate. Nested linear_copy makes a 2x2
    # corner array, through() extends past coincident faces.
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

    # Helicoidal stem swept along a tapered helix_path — radius funnels
    # from body_r-2 at the plate down to 4 at the body, three turns
    # over stem_h. Almond/lens cross-section: two mirrored circular
    # segments arching above and below a shared chord on y=0 — same
    # width as a round wire (chord_r=1.5) but flattened to sag=0.75,
    # so the coil reads as wound ribbon. overhang= extends the helix
    # past its nominal endpoints by half the cross-section length on
    # each side so the tilted endcap centers on the joint plane —
    # fully buried in plate below and body above, no seam.
    n_turns = 3
    chord_r, sag = 1.5, 0.75
    overhang = chord_r
    seg_r = (chord_r**2 + sag**2) / (2 * sag)
    half = math.asin(chord_r / seg_r)
    n_arc = 8
    wire = [
        (s * seg_r * math.sin(half - 2*half*i/n_arc),
         s * ((sag - seg_r) + seg_r * math.cos(half - 2*half*i/n_arc)))
        for s in (+1, -1) for i in range(n_arc)
    ]
    stem = path_extrude(
        wire,
        helix_path(r=body_r - 2, r_end=4.0, pitch=stem_h/n_turns,
                   turns=n_turns, overhang=overhang, points_per_turn=64),
    ).up(plate_thk)
    # Position the stand below the body so the helix's nominal top
    # (excluding overhang) sits at body's bottom face (z=0). The
    # overhang then embeds the endcap into the body above and into
    # the plate below — no fuse= needed.
    stand = union(plate, stem).down(plate_thk + stem_h)

# Three swept fins, mounted flush with the body bottom. The 2D
# profile is a triangle whose tip pulls back parabolically with
# radial distance — y → y − α*x² so the bottom edge curves down to
# the swept tip and the leading edge arcs from the root top to that
# tip. Built directly as a sampled polygon and linear_extrude'd;
# Minkowski with a small sphere rounds all three edges. at="lside"
# puts the body-facing root chord on the cylinder wall; we read the
# post-rotate bbox so attach centers correctly, then push the fin
# radially inward by the fillet so the body-side curve embeds in
# the wall.
fin_fillet, edge_r, tip_back, n_curve = 2, 0.8, 12, 16
base_w_eff, base_h_eff, thk_eff = 14 - 2*edge_r, 22 - 2*edge_r, 2 - 2*edge_r
sweep = lambda x: (tip_back / base_w_eff**2) * x**2
fin_profile = (
    [(base_w_eff * i/n_curve, -sweep(base_w_eff * i/n_curve))
     for i in range(n_curve + 1)]
    + [(base_w_eff * (1 - t/n_curve),
        base_h_eff * (t/n_curve) - sweep(base_w_eff * (1 - t/n_curve)))
       for t in range(1, n_curve + 1)]
)
fin_blank = minkowski(
    polygon(points=fin_profile).linear_extrude(height=thk_eff),
    sphere(r=edge_r, fn=16),
).rotate([90, 0, 0])
fin = (
    fin_blank.attach(
        body, on="outer_wall", at="lside",
        at_z=bbox(fin_blank).size[2] / 2 - body_h / 2,
        fuse=True,
    ).left(fin_fillet)
)
fins = fin.rotate_copy(angle=120, n=3, axis=[0, 0, 1])

# Engraved name on the body wall — text wraps around the cylinder.
labeled_body = body.add_text(
    label="SCAD-1", on="outer_wall", meridian=0,
    font_size=4, spacing=1.6, relief=-0.4,
)

rocket = union(labeled_body, nose, stand, fins)
render(rocket, "rocket.scad")
