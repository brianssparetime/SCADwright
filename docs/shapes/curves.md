# Curves and sweep

Path generators and sweep operations for creating shapes along 3D curves.

```python
from scadwright.shapes import (
    path_extrude, circle_profile,
    helix_path, bezier_path, catmull_rom_path,
    Helix, Spring,
)
```

## `path_extrude(profile, path)`

Sweeps a 2D cross-section along a 3D path, producing a polyhedron.

```python
profile = circle_profile(2, segments=12)
path = helix_path(r=10, pitch=5, turns=3)
shape = path_extrude(profile, path)
```

- `profile` -- list of (x, y) points describing the cross-section, counter-clockwise.
- `path` -- list of (x, y, z) points.
- `closed` -- connect last section back to first (for torus-like shapes). Default `False`.
- `convexity` -- OpenSCAD rendering hint. Default `10`.

When `closed=False`, flat end-caps are generated. The profile is oriented perpendicular to the path using rotation-minimizing frames to avoid twisting.

## `circle_profile(r, segments=16)`

Generates a circular cross-section for use with `path_extrude`:

```python
wire = circle_profile(1.5, segments=12)
tube_shape = path_extrude(wire, my_path)
```

## Path generators

### `helix_path(r, pitch, turns)`

Helical path centered on the z-axis, starting at (r, 0, 0) and rising in +z:

```python
path = helix_path(r=10, pitch=5, turns=3, points_per_turn=36)
```

### `bezier_path(control_points, steps=32)`

Cubic Bezier curve through 4 control points:

```python
path = bezier_path([(0,0,0), (10,0,5), (10,10,5), (0,10,0)], steps=24)
```

### `catmull_rom_path(points, steps_per_segment=16)`

Smooth curve passing through every point:

```python
path = catmull_rom_path([(0,0,0), (10,5,0), (20,0,0), (30,5,0)])
```

## Components

### `Helix`

Solid helix: a circular cross-section swept along a helical path.

```python
coil = Helix(r=10, wire_r=1, pitch=5, turns=3)
```

- `r` -- helix radius (center of wire to axis)
- `wire_r` -- wire cross-section radius
- `pitch` -- z-rise per full turn
- `turns` -- number of turns

### `Spring`

Compression spring with optional flat ends for stable resting.

```python
s = Spring(r=8, wire_r=0.5, pitch=3, turns=5)
s = Spring(r=8, wire_r=0.5, pitch=3, turns=5, flat_ends=False)
```

- Same params as `Helix`, plus `flat_ends` (default `True`).
- Flat ends add half-turn at zero pitch at each end so the spring sits flat.
