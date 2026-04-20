from scadwright.boolops import union
from scadwright.primitives import cube, sphere
MODEL = union(
    cube([10, 10, 10]),
    sphere(r=7).translate([5, 5, 5]),
)
