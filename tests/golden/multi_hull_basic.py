from scadwright.composition_helpers import multi_hull
from scadwright.primitives import cube, sphere
# Hub-and-spoke: central cube hulled to each of three offset spheres.
hub = cube([3, 3, 3], center=True)
spokes = [
    sphere(r=1.5, fn=12).translate([10, 0, 0]),
    sphere(r=1.5, fn=12).translate([0, 10, 0]),
    sphere(r=1.5, fn=12).translate([0, 0, 10]),
]

MODEL = multi_hull(hub, *spokes)
