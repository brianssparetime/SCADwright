from scadwright import resolution
from scadwright.boolops import difference
from scadwright.primitives import cube, cylinder
with resolution(fn=64):
    body = cube([40, 40, 20], center="xy")
    hole = cylinder(h=22, r=5, center=True)
    MODEL = difference(
        body,
        hole.translate([10, 0, 0]),
        hole.translate([-10, 0, 0]),
    )
