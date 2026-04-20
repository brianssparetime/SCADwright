# Polyhedra and basic 3D shapes

Prisms, pyramids, Platonic solids, torus, dome, and spherical cap.

```python
from scadwright.shapes import (
    Prism, Pyramid,
    Tetrahedron, Octahedron, Dodecahedron, Icosahedron,
    Torus, Dome, SphericalCap,
)
```

## `Prism(sides, r, h)`

N-sided prism centered on the origin, base on z=0. Pass `top_r` for a frustum (tapered prism).

```python
Prism(sides=6, r=10, h=20)              # hexagonal prism
Prism(sides=4, r=10, h=15, top_r=5)     # square frustum
```

## `Pyramid(sides, r, h)`

N-sided pyramid with apex at (0, 0, h), base on z=0.

```python
Pyramid(sides=4, r=10, h=20)            # square pyramid
Pyramid(sides=3, r=8, h=12)             # triangular
```

## Platonic solids

All inscribed in a sphere of radius `r`, centered on the origin.

```python
Tetrahedron(r=10)
Octahedron(r=10)
Dodecahedron(r=10)
Icosahedron(r=10)
```

## `Torus(major_r, minor_r)`

Donut centered on the origin in the XY plane. Optional `angle` for a partial sweep.

```python
Torus(major_r=20, minor_r=5)            # full ring
Torus(major_r=20, minor_r=5, angle=180) # half ring
```

`minor_r` must be less than `major_r`.

## `Dome(r)`

Hemisphere with flat face on z=0. Optional `thk` for a hollow shell.

```python
Dome(r=15)                              # solid hemisphere
Dome(r=15, thk=2)                       # hollow dome, 2mm wall
```

## `SphericalCap(any two of six params)`

A portion of a sphere sliced by a plane. Flat face on z=0, dome rising in +z. Four parameters linked by two equations -- specify any two and the solver fills in the rest.

```python
SphericalCap(sphere_r=20, cap_height=8)
SphericalCap(cap_dia=30, cap_height=5)
```

Parameters: `cap_height`, `cap_dia`, `cap_r`, `sphere_r`. All are published as readable attributes after construction.

See [examples/convex-caliper.py](../examples/convex-caliper.py) for a worked example that defines this Component inline to demonstrate the equation solver.
