"""Golden: a custom transform with module hoisting.

`chamfer_top` widens the top of any node by a small minkowski with a sphere.
Used twice with the same params -> single hoisted module, two call sites.
"""

from scadwright.boolops import minkowski, union
from scadwright.primitives import cube, sphere
from scadwright.transforms import transform
@transform("chamfer_top")
def _chamfer_top(node, *, depth):
    return minkowski(node, sphere(r=depth, fn=8))


MODEL = union(
    cube([10, 10, 5]).chamfer_top(depth=1),
    cube([6, 6, 8]).translate([15, 0, 0]).chamfer_top(depth=1),
)
