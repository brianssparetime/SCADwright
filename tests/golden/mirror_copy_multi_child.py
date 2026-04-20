from scadwright.composition_helpers import mirror_copy
from scadwright.primitives import cube, sphere
# Top-level form: keeps and mirrors an entire group of children.
MODEL = mirror_copy(
    [1, 0, 0],
    cube([5, 5, 5]).translate([5, 0, 0]),
    sphere(r=2, fn=12).translate([7, 0, 5]),
)
