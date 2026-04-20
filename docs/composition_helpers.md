# Composition helpers

Helpers that take a shape (or shapes) and produce the original *plus* transformed copies, all unioned together. They cover patterns that show up constantly in real designs: mirrored symmetry, rotational symmetry, linear arrays, swept shapes.

Imports used on this page:

```python
from scadwright.composition_helpers import (
    linear_copy, rotate_copy, mirror_copy, multi_hull, sequential_hull,
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

Differences out half (or a quadrant, or an octant) of a shape. Takes a signed 3-vector; each nonzero component picks an axis and the side to keep. Useful for section views and printing halves.

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

A `size=` kwarg overrides the default cutter-cube edge length (default `1e4`, much larger than any practical part). Set it smaller only if the huge cube literal in the output SCAD bothers you.

---

### Advanced notes

- The chained-form and top-level-form produce equivalent SCAD output for the single-shape case — pick whichever reads better in context.
- All helpers produce a `union(...)` under the hood; you can think of them as shorthand for hand-writing the union.
