"""A 3D-printable rocket on a coiled-spring stand — scadwright brag.

Showcases (all in ~40 lines of actual code):

- Parabolic ogive nose: 2D polygon built from the parabola formula
  in a list comprehension, then rotate_extrude'd in one expression.
- Coiled-spring stem: round wire profile path_extrude'd along a
  helix_path. (OpenSCAD has no native helical sweep — you'd build
  the polyhedron's vertices and faces by hand.)
- Square baseplate with filleted vertical edges (Cube.fillet) and
  four M3 counterbore mounting holes — Counterbore Component, nested
  linear_copy for the 2x2 array, through() for clean cuts.
- Right-triangular fins (Wedge with l/w/h + 2D corner fillet) with
  3D edge rounding via Minkowski sum.
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
    Wedge, counterbore_for_screw, get_screw_spec, helix_path, path_extrude,
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

    # Helicoidal stem swept along a 3D helix path — path_extrude and
    # helix_path are scadwright primitives (OpenSCAD has no native
    # helical sweep, only linear_extrude with twist). Round wire
    # profile, two full turns between plate and rocket body.
    n_turns = 2
    wire = [(1.5*math.cos(2*math.pi*i/16), 1.5*math.sin(2*math.pi*i/16)) for i in range(16)]
    stem = path_extrude(
        wire,
        helix_path(r=body_r - 2, pitch=stem_h/n_turns, turns=n_turns, points_per_turn=64),
    ).up(plate_thk)
    # The stand's "top" anchor is on the helical wire's tip — a
    # near-point contact that falls into the cross-section path's
    # documented non-convex limitation. Use fuse=False here; the
    # stem touches the body at a vertex either way.
    stand = union(plate, stem).attach(body, on="bottom", at="top")

# Three swept-leading-edge fins, mounted flush with the body bottom.
# Wedge's right-triangular profile becomes the fin; rotate so base_h
# runs along the body axis. at="lside" puts the body-facing face on
# the cylinder wall. The fillet rounds all three corners — to keep the
# rounded body-side corner from leaving a gap, we read the post-rotate
# axial extent so attach centers correctly, then push the fin radially
# inward by the fillet so the body-side curve embeds in the wall.
fin_fillet, edge_r = 2, 0.8
fin_blank = minkowski(
    Wedge(base_w=14 - 2*edge_r, base_h=22 - 2*edge_r, thk=2 - 2*edge_r,
          fillet=fin_fillet - edge_r, fn=64),
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
