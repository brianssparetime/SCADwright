"""Visual reference for ``add_text``'s ``text_dir`` / ``rotate_glyphs`` /
``flip`` kwargs.

Generates an 8-cell grid showing every combination of the three flags
applied to "TEXT" on a curved host. The 2x4 layout matches the table in
docs/add_text.md; alternating hosts (cylinder / tapered cone / barrel)
prove the same flag combinations work uniformly across surface kinds.

Run with:

    cd examples && python text_orientations.py

The companion ``tools/render_text_orientations.py`` renders the
resulting .scad and overlays per-cell labels for embedding in docs.
"""

from scadwright import render, resolution
from scadwright.boolops import union
from scadwright.primitives import cylinder
from scadwright.shapes import Barrel

# (text_dir, rotate_glyphs, flip, host kind)
COMBOS = [
    ("circumferential", False, False, "cyl"),     # default — letters upright, wraps around
    ("circumferential", False, True,  "cone"),    # letters upside-down, wraps other way
    ("circumferential", True,  False, "barrel"),  # letters on their backs
    ("circumferential", True,  True,  "cyl"),     # letters on their backs, other way
    ("axial",           False, False, "cone"),    # upright column, top-to-bottom
    ("axial",           False, True,  "barrel"),  # upside-down column, bottom-to-top
    ("axial",           True,  False, "cyl"),     # wine-bottle: letters rotated 90° CCW
    ("axial",           True,  True,  "cone"),    # wine-bottle, the other way
]

PITCH_Y = 32
PITCH_Z = 38
HOST_H = 24


def _make_host(kind):
    if kind == "cyl":
        return cylinder(h=HOST_H, r=8)
    if kind == "cone":
        return cylinder(h=HOST_H, r1=10, r2=5)
    if kind == "barrel":
        return Barrel(h=HOST_H, end_r=8, bulge=2)
    raise ValueError(kind)


with resolution(fn=48):
    cells = []
    for i, (td, rg, fl, kind) in enumerate(COMBOS):
        row, col = i // 4, i % 4
        host = _make_host(kind)
        labeled = host.add_text(
            label="TEXT", on="outer_wall", meridian=0,
            font_size=5, relief=-0.6,
            text_dir=td, rotate_glyphs=rg, flip=fl,
        )
        cells.append(labeled.translate([0, col * PITCH_Y, -row * PITCH_Z]))
    grid = union(*cells)

render(grid, "text_orientations.scad")
