from scadwright.primitives import cube
# 4-fold rotational symmetry around Z (90 degrees, 4 copies).
MODEL = cube([5, 1, 10]).translate([10, 0, 0]).rotate_copy(angle=90, n=4)
