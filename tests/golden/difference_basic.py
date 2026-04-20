from scadwright.boolops import difference
from scadwright.primitives import cube, cylinder
MODEL = difference(
    cube([10, 10, 10], center=True),
    cylinder(h=12, r=2, center=True, fn=32),
)
