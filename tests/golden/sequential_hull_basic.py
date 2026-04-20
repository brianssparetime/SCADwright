from scadwright.composition_helpers import sequential_hull
from scadwright.primitives import sphere
# Sweep: a chain of small spheres hulled pairwise creates a "tube" along the path.
points = [(0, 0, 0), (5, 5, 0), (10, 5, 5), (10, 0, 10)]
MODEL = sequential_hull(
    *[sphere(r=1, fn=8).translate(list(p)) for p in points]
)
