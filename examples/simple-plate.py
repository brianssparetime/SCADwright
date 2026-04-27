"""A plate with two holes. The simplest possible scadwright script.

No Components, no Design, no equations: just primitives, booleans,
and a render call. This is Stage 1 from docs/organizing_a_project.md.

Run:
    python examples/simple-plate.py
"""

from scadwright import render
from scadwright.boolops import difference
from scadwright.primitives import cube, cylinder

plate = cube([80, 40, 5], center="xy")
hole = cylinder(h=7, d=6, fn=32).down(1)

part = difference(
    plate,
    hole.left(20),
    hole.right(20),
)

render(part, "simple-plate.scad")
