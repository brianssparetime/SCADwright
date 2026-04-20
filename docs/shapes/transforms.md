# Curve-based transforms

Transforms that operate on shapes using curve/path logic. These register as chainable methods on every shape (like built-in transforms).

```python
from scadwright.shapes.curves.paths import helix_path, bezier_path
```

Importing `scadwright.shapes` registers all three transforms automatically.

## `.along_curve(path, count)`

Place copies of a shape at evenly-spaced points along a 3D path, oriented to follow the path direction.

```python
bolt = Bolt(size="M3", length=8)
path = bezier_path([(0,0,0), (20,0,10), (40,0,0), (60,0,10)])
bolt.along_curve(path=path, count=6)
```

Each copy is rotated so its z-axis aligns with the path tangent at that point.

## `.bend(radius, axis="z")`

Wrap linear geometry into a circular arc around a cylinder of the given radius.

```python
bar = cube([2, 2, 30])
ring = bar.bend(radius=15)
```

The shape's extent along the bend axis is mapped to an arc. This is an approximation using segmented slicing -- increase the segment count via longer shapes or smaller radii.

`axis` controls the bend direction: `"x"`, `"y"`, or `"z"` (default).

## `.twist_copy(angle, count)`

Create stacked copies with incremental rotation around z.

```python
blade = cube([20, 3, 1])
fan = blade.twist_copy(angle=45, count=8)
```

Each copy is rotated by `angle` degrees relative to the previous one and offset upward by the shape's height. The first copy is unrotated.
