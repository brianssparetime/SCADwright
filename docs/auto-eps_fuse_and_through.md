# Eliminating manual epsilon overlap

OpenSCAD requires a small overlap (epsilon) whenever two shapes share a face in a boolean operation. Without it, the geometry kernel produces artifacts or non-manifold output. scadwright provides two tools to handle this automatically.

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
