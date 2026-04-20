# 2D profiles

Factory functions and Components for common 2D shapes. Extrude them with `linear_extrude` or `rotate_extrude` to make 3D parts.

```python
from scadwright.shapes import (
    rounded_rect, rounded_square, regular_polygon,
    Sector, Arc, RoundedEndsArc, RoundedSlot,
)
```

## `rounded_rect(x, y, r, *, fn=None)`

Rectangle with rounded corners, centered on the origin. `r=0` falls back to a plain square.

```python
rounded_rect(20, 10, 2, fn=16)
```

## `rounded_square(size, r, *, fn=None)`

Convenience wrapper around `rounded_rect`. `size` can be a single number (square) or `[w, h]`.

```python
rounded_square(10, 2)               # 10x10 with 2mm corner radius
rounded_square([20, 10], 2)         # 20x10
```

## `regular_polygon(sides, r)`

Regular n-sided polygon inscribed in a circle of radius `r`, centered on the origin. First vertex on the +X axis.

```python
regular_polygon(sides=6, r=5)       # hexagon
```

## `Sector(r, angles, fn=None)`

Pie slice cut from a disc.

```python
Sector(r=10, angles=(0, 60), fn=24)
```

## `Arc(r, angles, width, fn=None)`

Ring segment -- like a Sector but only the outer band. Published attributes: `inner_r`, `outer_r`.

```python
Arc(r=10, angles=(0, 90), width=2, fn=24)
```

## `RoundedEndsArc(r, angles, width, end_r, fn=None)`

An Arc with semicircular caps on its ends.

```python
RoundedEndsArc(r=10, angles=(0, 90), width=1, end_r=0.5, fn=24)
```

## `RoundedSlot(length, width, fn=None)`

Capsule / stadium shape: rectangle with semicircular caps on the short sides. When `length` equals `width`, the result is a circle.

```python
RoundedSlot(length=20, width=4, fn=16)
```
