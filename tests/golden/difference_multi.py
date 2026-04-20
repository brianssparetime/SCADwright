from scadwright.boolops import difference
from scadwright.primitives import cube, cylinder
# Difference with 3+ operands: first minus all others.
MODEL = difference(
    cube([40, 40, 20], center="xy"),
    cylinder(h=22, r=3, fn=32).translate([10, 0, 0]),
    cylinder(h=22, r=3, fn=32).translate([-10, 0, 0]),
)
