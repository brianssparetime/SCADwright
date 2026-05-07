# Eliminating manual epsilon overlap

OpenSCAD requires a small overlap (epsilon) whenever two shapes share a face in a boolean operation. Without it, the geometry kernel produces artifacts or non-manifold output. SCADwright provides two tools to handle this automatically.

## `through(parent)` -- for cutters in `difference()`

Extends a cutter through any face of `parent` that it touches, adding a small overlap so `difference()` produces a clean cut:

```python
from scadwright.boolops import difference
from scadwright.primitives import cube, cylinder

box = cube([20, 20, 10])
part = difference(box, cylinder(h=10, r=3).through(box))
```

The cylinder's top and bottom are both flush with the box, so `through()` extends both ends by 0.01 (the default epsilon). No manual `EPS` constant needed.

### How it works

`through()` computes bounding boxes of the cutter and parent, detects which faces are coincident (within floating-point tolerance), and extends only those faces. Faces that aren't coincident are left alone:

```python
# Through-hole: both ends flush -> both extended
cylinder(h=10, r=3).through(box)

# Counterbore: only top is flush -> only top extended
cylinder(h=5, r=6).up(5).through(box)

# Blind pocket: neither end flush -> no change (harmless to call)
cylinder(h=4, r=3).up(3).through(box)
```

### Cut axis

`through()` auto-detects the cut axis by finding which axis has coincident faces. For ambiguous cases (e.g. a cube-shaped cutter), specify explicitly:

```python
cube([20, 20, 3]).up(3).through(box, axis="z")
```

### Custom epsilon

Default is 0.01. Override with `eps=`:

```python
cylinder(h=10, r=3).through(box, eps=0.1)
```

### Call order

Call `through()` after positioning the cutter. It needs to see the final position to detect coincident faces:

```python
cylinder(h=10, r=3).up(5).right(8).through(box)   # position first, then through
```

### Rotated cutters

For angled drill holes, chamfered countersinks on non-vertical faces, draft-angled inserts, and other rotated-cutter patterns, the world-axis path can't detect coincidence (the cutter's world AABB is inflated by the rotation). Pass `axis="local"` (or `"local_x"` / `"local_y"` / `"local_z"`) to evaluate coincidence in the cutter's local frame:

```python
import math

# 30°-tilted cylindrical drill, sized to span a 2 mm plate exactly:
plate = cube([20, 20, 2])
h = 2 / math.cos(math.radians(30))
drill = (
    cylinder(h=h, r=2)
    .rotate([0, 30, 0])
    .translate([10, 5, 0])
)
part = difference(plate, drill.through(plate, axis="local_z"))
```

`axis="local"` is a synonym for `axis="local_z"` (the cylinder convention). For non-cylindrical cutters, specify the local axis explicitly: `local_x`, `local_y`, or `local_z`.

How it works: `through()` walks the cutter's outer rotations and translations to find the cumulative local-to-world transform, projects the cutter's end-face centers (at the cutter's local origin on the cut axis) into world space, and checks them against the parent's AABB face planes. The extension applies as a `Translate(Scale(...))` inserted at the leaf level, so the SCAD output keeps the original `rotate(...)` calls plus a leaf-level `translate + scale` rather than collapsing into an opaque `multmatrix`.

With `axis=None` and a rotated cutter that has no world-axis coincidence, `through()` raises pointing at the local-axis form rather than silently no-opping. Cutters whose rotation happens to be axis-permuting (90° around a single axis — `rotate([0, 90, 0])`) keep an axis-aligned world bbox, so the world-axis path handles them and no error is raised.

Anisotropic Scale, Mirror, or other non-rotation transforms in the cutter's stack raise — the local-axis path requires a pure rotation. Apply scale to the underlying primitive's parameters instead.

## `attach(fuse=True)` -- for joints in `union()`

When two parts sit flush against each other (e.g. a pylon on a floor), `fuse=True` on `attach()` pushes self slightly into the contact face, eliminating the coincident-surface seam:

```python
from scadwright.boolops import union
from scadwright.shapes import Tube

floor = cube([40, 40, 2])
pylon = Tube(od=7, id=3, h=8).attach(floor, fuse=True)
part = union(floor, pylon)
```

The pylon overlaps the floor by 0.01 at the contact face. Override with `eps=`:

```python
Tube(od=7, id=3, h=8).attach(floor, fuse=True, eps=0.05)
```
