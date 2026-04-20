from scadwright.boolops import hull
from scadwright.primitives import cube, cylinder
MODEL = hull(
    cube([10, 10, 1]),
    cylinder(h=10, r=1, fn=12).translate([5, 5, 0]),
)
