# Bounding boxes and tests

scadwright can answer geometric questions about a shape without sending it to OpenSCAD: how big is it, where is it, does it fit in a print volume, does it overlap with another shape. These are the building blocks for writing automated tests of your designs.

Imports used on this page:

```python
from scadwright import bbox, tight_bbox, tree_hash
from scadwright.asserts import assert_fits_in, assert_contains, assert_no_collision, assert_bbox_equal
```

## Bounding boxes

A *bounding box* is the smallest axis-aligned box that contains a shape. `bbox(shape)` returns one:

```python
part = cube([10, 20, 30]).right(5)

bb = bbox(part)
bb.min        # (5, 0, 0)    — the bottom-front-left corner
bb.max        # (15, 20, 30) — the top-back-right corner
bb.size       # (10, 20, 30)
bb.center     # (10, 10, 15)
```

The bounding box is computed in *world coordinates* — it accounts for any transforms applied to the shape. Rotated shapes get a "loose" box that's larger than the rotated shape itself; that's the cost of staying axis-aligned.

`bbox` works on any shape: primitives, transforms, CSG combinations, components, custom transforms.

### `BBox`

The bounding box object has a few useful methods:

```python
bb.contains(other_bb)         # True if other fits entirely inside bb
bb.overlaps(other_bb)         # True if any volume is shared
bb.union(other_bb)            # smallest box containing both
bb.intersection(other_bb)     # overlap, or None if disjoint
bb.transformed(matrix)        # apply a Matrix to the 8 corners, take a new AABB
```

You can also build one by hand:

```python
BBox(min=(0, 0, 0), max=(10, 20, 30))
```

## Test assertions

Four helpers raise `AssertionError` (the same kind pytest uses) with informative messages on failure.

### `assert_fits_in(node, envelope)`

Checks that a shape's bounding box fits within an envelope.

```python
def test_widget_fits_in_print_volume():
    assert_fits_in(Widget(width=180), [200, 200, 50])
```

`envelope` is either:

- a 3-element size like `[200, 200, 50]` (interpreted as a centered box of that size), or
- a `BBox`.

### `assert_no_collision(a, b)`

Checks that two shapes' bounding boxes don't overlap.

```python
def test_two_widgets_dont_collide():
    a = Widget(width=40)
    b = Widget(width=40).right(60)
    assert_no_collision(a, b)
```

### `assert_contains(outer, inner)`

Checks that one shape's bounding box fully contains another's.

```python
def test_electronics_fit_inside_case():
    assert_contains(case, electronics)
```

### `assert_bbox_equal(node, expected_bbox, tol=1e-9)`

Pins a shape's bounding box to a specific value (with floating-point tolerance).

```python
assert_bbox_equal(part, BBox(min=(0, 0, 0), max=(10, 20, 30)))
```

## Regression-pinning geometry: `tree_hash`

`tree_hash(node)` returns a short stable string. The hash changes only if the geometry semantically changes — moving the same script to a different file, or reformatting scadwright's emitter output, doesn't change it.

```python
def test_widget_geometry_pinned():
    assert tree_hash(Widget(width=40)) == "a1b2c3d4e5f6..."
```

Use this to lock in known-good versions of a part. When a code change shifts geometry unexpectedly, the test fails with the new hash; you compare the rendered SCAD to be sure the change was intended, then update the expected hash.

## Inspecting transforms

For users who want to know "where did this shape end up?", scadwright exposes its transform math.

### `Matrix`

A 4×4 transform matrix. Useful for computing placements, transforming points/vectors, and composing transforms without building shapes. See [the Matrix reference](matrix.md) for the full surface.

```python
m = Matrix.translate(5, 0, 0) @ Matrix.rotate_z(45)
m.apply_point((1, 0, 0))     # where (1,0,0) ends up after this transform
```

### `resolved_transform(node)`

Returns a `Matrix` describing the world-space transform at a node. For a top-level shape it's identity (no transforms above it).

---

### Advanced notes

- Bounding boxes are axis-aligned (AABBs). For a rotated shape they're a loose upper bound, not the tightest possible box. There's no oriented-bounding-box (OBB) support yet; a primitive-only `tight_bbox(prim)` exists as a stub for future expansion.
- For composed shapes (transforms, CSG, components), use `bbox` exclusively. `tight_bbox` raises on anything but bare primitives.
- `tree_hash` excludes source-location information, so the same code in different files hashes the same. It also walks Components by their parameter values plus the materialized tree, so changing a parameter changes the hash.
- For Components, the bounding box is computed once per instance and cached. `_invalidate()` clears the cache.
- The `Matrix` type is hashable and immutable. All operations (`compose`, `apply_point`, `invert`) return new matrices.
