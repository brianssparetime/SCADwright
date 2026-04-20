from scadwright.boolops import intersection
from scadwright.primitives import cube, sphere
MODEL = intersection(
    cube([10, 10, 10], center=True),
    sphere(r=6, fn=32),
)
