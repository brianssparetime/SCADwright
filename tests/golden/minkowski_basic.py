from scadwright.boolops import minkowski
from scadwright.primitives import cube, sphere
MODEL = minkowski(
    cube([10, 10, 2], center="xy"),
    sphere(r=1, fn=8),
)
