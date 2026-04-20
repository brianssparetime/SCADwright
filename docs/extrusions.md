# Extrusions

Extrusions take a 2D shape and turn it into a 3D shape. There are two ways: pull the 2D shape upward (`linear_extrude`), or sweep it around the Z axis (`rotate_extrude`).

Imports used on this page:

```python
from scadwright.extrusions import linear_extrude, rotate_extrude
```

## `linear_extrude`

Pulls a 2D shape straight up to make a 3D solid.

```python
# Plain extrusion: a circle becomes a cylinder.
linear_extrude(circle(r=5, fn=24), height=10)

# Same thing as a chained method.
circle(r=5, fn=24).linear_extrude(height=10)

# A twisted, tapered, centered prism:
circle(r=5, fn=24).linear_extrude(
    height=20,
    twist=180,             # degrees of rotation over the full height
    scale=2,               # the top is 2× the size of the bottom
    center=True,           # straddle the XY plane (otherwise sits on Z=0)
)
```

**Parameters:**

- `height` — how far to pull the shape up.
- `twist` — degrees of rotation as you go from bottom to top. Defaults to 0.
- `scale` — scale factor at the top. A scalar scales uniformly; a 2-vector `[sx, sy]` scales per-axis. Defaults to 1.
- `slices` — optional explicit number of layers. Useful when twisting; otherwise OpenSCAD picks based on facet settings.
- `center` — `True` straddles the XY plane; `False` (default) puts the base on Z=0.

The 2D child can be any 2D shape — a built-in primitive, a `polygon`, or one of the [shape library](shapes/README.md) 2D shapes.

## `rotate_extrude`

Sweeps a 2D shape around the Z axis to make a 3D solid of revolution. Think bowls, washers, vases.

```python
# A tube: the profile is a thin rectangle off-axis; sweeping it makes a tube.
profile = polygon(points=[[5, 0], [7, 0], [7, 10], [5, 10]])
rotate_extrude(profile)

# Chained form, with a partial sweep:
profile.rotate_extrude(angle=180)       # half-sweep (semicircle of revolution)
```

**Parameters:**

- `angle` — degrees to sweep. Defaults to 360 (full revolution). Less than 360 makes a partial sweep.
- `convexity` — optional render hint.

The 2D profile must lie in the X≥0 half of the plane. Points with negative X cause OpenSCAD render errors.

---

### Advanced notes

- `linear_extrude(scale=...)` doesn't pre-compute slices for you; passing a large `twist` without enough slices produces faceted, blocky output. Either set `slices=` explicitly or wrap the call in `with resolution(fn=...):`.
- `rotate_extrude` accepts any 2D primitive but is most often used with `polygon` for non-trivial profiles.
- For partial-angle `rotate_extrude` the bounding box currently treats the swept region as if it were a full disc (pessimistic but safe).

### See also

- [Curves and sweep](shapes/curves.md) -- `path_extrude` sweeps a 2D profile along an arbitrary 3D path (the general case of extrusion)
