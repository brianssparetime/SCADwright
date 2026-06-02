# Composition helpers

Helpers that take a shape (or shapes) and produce the original *plus* transformed copies, all unioned together. They cover patterns that show up constantly in real designs: mirrored symmetry, rotational symmetry, linear arrays, swept shapes.

Imports used on this page:

```python
from scadwright.composition_helpers import (
    linear_copy, rotate_copy, mirror_copy, hole_grid,
    multi_hull, sequential_hull,
)
```

Each helper has two forms:

- A **chained method** on a single shape: `node.mirror_copy(...)`.
- A **top-level function** taking many shapes: `mirror_copy(..., a, b, c)`.

Use whichever reads better.

## `mirror_copy`

Keeps the shape and adds a mirrored copy.

```python
# Single shape — positional normal:
cube([10, 5, 2]).translate([5, 0, 0]).mirror_copy([1, 0, 0])

# Single shape — kwarg normal (matches the standalone form):
cube([10, 5, 2]).translate([5, 0, 0]).mirror_copy(normal=[1, 0, 0])

# A whole group at once (mirrors all of them together):
mirror_copy(
    cube([5, 5, 5]).translate([5, 0, 0]),
    sphere(r=2, fn=12).translate([7, 0, 5]),
    normal=[1, 0, 0],
)

# Positional SCAD-style form also works:
mirror_copy([1, 0, 0], cube([5, 5, 5]).translate([5, 0, 0]))
```

The mirror plane is given by its *normal*, same as `mirror`. Both the chained method and the standalone helper accept either a positional vector or a `normal=` kwarg. Recommended form for new code:
- Chained: `shape.mirror_copy(normal=[...])`
- Standalone: `mirror_copy(*shapes, normal=[...])`

## `rotate_copy`

Rotates the shape around an axis, keeping `n` total copies (including the original).

```python
# Chained: the shape comes first; angle positional, n optional.
cube([5, 1, 10]).translate([10, 0, 0]).rotate_copy(angle=90, n=4)
# 4-fold rotational symmetry around Z, 90° apart.

# Standalone: angle first, then variadic shapes, n/axis as kwargs.
rotate_copy(60, sphere(r=1).translate([5, 0, 0]), n=6)
# 6 spheres around Z, 60° apart.

# Standalone with default n=4:
rotate_copy(90, cube([3, 3, 10]).translate([8, 0, 0]))
```

**Parameters:**

- `angle` — degrees per step.
- `n` — total copies including the original. Default `4`. Keyword-only in the standalone form (variadic shapes go positional).
- `axis` — axis to rotate around. Defaults to Z.

## `linear_copy`

Translates the shape repeatedly, keeping `n` total copies.

```python
cylinder(h=10, r=2, fn=16).linear_copy([8, 0, 0], n=5)
# 5 cylinders along X, 8 apart.
```

**Parameters:**

- `offset` — translation per step.
- `n` — total copies including the original.

## `array`

Convenience alias over `linear_copy` for the common case of arraying along a principal axis.

```python
cube(5).array(count=3, spacing=10)            # default: array along X
cube(5).array(count=4, spacing=6, axis="y")
cube(5).array(count=2, spacing=10, axis="z")
cube(2).array(count=3, spacing=5, axis=[1, 1, 0])   # diagonal
```

**Parameters:**

- `count` — total copies including the original (positive integer).
- `spacing` — distance between adjacent copies. Negative spacing arrays in the opposite direction.
- `axis` — `"x"`, `"y"`, `"z"` (case-insensitive) or an explicit 3-vector.

For more complex spacing (per-step deltas that aren't a simple axis × scalar), use `linear_copy` directly.

## `hole_grid`

Replicate a hole cutter in a `rows × cols` rectangular grid. The grid spans `(rows - 1) * row_spacing` along the row direction (Y) and `(cols - 1) * col_spacing` along the column direction (X). By default it centers on the origin; pass `center=False` to place the bottom-left hole at the origin.

```python
from scadwright.composition_helpers import hole_grid
from scadwright.shapes import clearance_hole

# Flight-controller stack mount (4 holes in a 30.5×30.5 mm square).
plate = cube([60, 60, 3], center="xy")
cutter = hole_grid(
    rows=2, cols=2,
    row_spacing=30.5, col_spacing=30.5,
    hole=clearance_hole("M3", depth=3),
).through(plate, axis="z")          # break through both faces, no coincident seam
result = difference(plate, cutter)

# A 3×4 vent array on a panel.
panel = cube([60, 50, 3], center="xy")
vents = hole_grid(
    rows=3, cols=4,
    row_spacing=10, col_spacing=10,
    hole=cylinder(h=3, r=2.5),
).through(panel, axis="z")
result = difference(panel, vents)
```

The grid centers on the origin, so center the parent on it too (`center="xy"`). Call `.through()` on the grid before the `difference()`: it extends each hole past the coincident faces by a hair, so the cut breaks cleanly through instead of leaving a zero-thickness surface that flickers in preview and can fail to render. `hole_grid` adds no overlap on its own.

**Parameters (all kwarg-only):**

- `rows`, `cols` — positive integers.
- `row_spacing`, `col_spacing` — distance between adjacent holes along each axis.
- `hole` — any cutter shape: `clearance_hole("M3", ...)`, a `Counterbore`, a plain `cylinder`, or a custom node.
- `center` — when `True` (default), the grid is centered on the origin. When `False`, the bottom-left hole sits at the origin.

For irregular hole positions, use `linear_copy` directly or hand-translate each hole.

## `multi_hull`

Hulls each of the `others` with `first`, and unions the results. Useful when several shapes branch out from a single anchor.

```python
hub = cube([3, 3, 3], center=True)
spokes = [
    sphere(r=1.5).right(10),
    sphere(r=1.5).forward(10),
    sphere(r=1.5).up(10),
]
multi_hull(hub, *spokes)
```

## `sequential_hull`

Hulls each consecutive pair of shapes. Useful for "swept" shapes along a path.

```python
points = [(0, 0, 0), (5, 5, 0), (10, 5, 5), (10, 0, 10)]
sequential_hull(
    *[sphere(r=1, fn=8).translate(list(p)) for p in points]
)
# Hulls (p0,p1), (p1,p2), (p2,p3) — like a plastic tube along the path.
```

## `halve`

Cuts a shape down to one half (or a quadrant, or an octant) by intersecting it with the kept half-space(s). Takes a signed 3-vector; each nonzero component picks an axis and the side to keep. Useful for section views and printing halves.

```python
part.halve([0, 1, 0])           # keep +y, cut -y
part.halve([0, -1, 0])          # keep -y
part.halve([1, 1, 0])           # keep +x,+y quadrant
part.halve(y=1)                 # kwarg form
halve(part, [0, 0, 1])          # standalone form
```

Cut planes pass through the world origin on their axes, so translate first to cut elsewhere:

```python
part.translate([0, 10, 0]).halve([0, 1, 0])   # cuts at y=10 relative to part
```

By default the kept-region box is sized to just enclose the shape's world-space bbox plus a 2% margin, so the emitted SCAD shows numbers proportional to the part. Pass `size=N` (cube edge length) to override — useful when the bbox can't be computed cheaply or when a fixed size is needed for downstream tooling.

`bbox()` of a halved shape returns the AABB of the *kept* region, not the original shape — `halve()` emits as `intersection(part, kept_box)` and the BBoxVisitor for Intersection folds children's bboxes via intersection, so the clipping is automatic. This matters for things like reading `bbox(part).min[2]` to compute how far below the bed a printed half extends.

## `arrange_on_bed`

Packs parts onto the print bed in rows, lifts each onto z=0, fit-checks against the plate, and returns the union. Replaces the bbox-→-translate-→-assert boilerplate that print variants accumulate.

```python
return arrange_on_bed(housing_left, housing_right, mating_disc,
                      plate=(256, 256), gap=8)
```

```python
def arrange_on_bed(*parts, gap=5.0, plate=(256, 256),
                   lift_to_bed=True, assert_fit=True, sort=None) -> Union: ...
```

Conventions:

- **Origin at bed front-left corner** (0, 0). Matches typical slicer defaults (PrusaSlicer, Cura). For center-of-bed coordinate systems, translate the result by `[-plate[0]/2, -plate[1]/2, 0]`.
- **Rows along +X, wrapping along +Y.** Parts fill left-to-right; when one would cross the plate width, the layout starts a new row past the previous row's deepest part. Within a row, parts are centered across the row's depth. Parts that all fit in one line stay a single row.
- **`sort=None`** (the default) packs in argument order. **`sort="depth"`** sorts parts deepest-first, which keeps rows uniform and wastes less bed.
- **`lift_to_bed=True`** (the default) translates each part so its `bbox.min[2] = 0` — printing requires non-negative Z. Pass `lift_to_bed=False` for layouts where the parts already sit on the bed.
- **`assert_fit=True`** (the default) raises `ValidationError` at construction time when the wrapped layout exceeds `plate`, naming the row count and overflow magnitude. Pass `assert_fit=False` to lay parts out anyway (useful when you want to inspect a too-large variant).

This fills the bed in rows, not optimal nesting: parts are packed as axis-aligned rectangles, so an interlocking or triangular arrangement is out of scope. Pre-rotate or reorder parts to pack tighter.

Iterables in the args flatten one level, matching the CSG-arg convention: `arrange_on_bed([a, b], c)` works the same as `arrange_on_bed(a, b, c)`.

---

### Advanced notes

- The chained-form and top-level-form produce equivalent SCAD output for the single-shape case — pick whichever reads better in context.
- All helpers produce a `union(...)` under the hood; you can think of them as shorthand for hand-writing the union.
