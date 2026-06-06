# Polyhedra and basic 3D shapes

Prisms, pyramids, Platonic solids, torus, and dome.

```python
from scadwright.shapes import (
    Prism, Pyramid, Prismoid, Wedge,
    Tetrahedron, Octahedron, Dodecahedron, Icosahedron,
    Torus, Dome, Capsule, PieSlice,
)
```

## `Prism(sides, r, h)`

N-sided prism centered on the origin, base on z=0. Pass `top_r` for a frustum (tapered prism).

```python
Prism(sides=6, r=10, h=20)              # hexagonal prism
Prism(sides=4, r=10, h=15, top_r=5)     # square frustum
```

![Prism](images/prism.png)

*`Prism(sides=6, r=12, h=20)` — a hexagonal column.*

## `Pyramid(sides, r, h)`

N-sided pyramid with apex at (0, 0, h), base on z=0.

```python
Pyramid(sides=4, r=10, h=20)            # square pyramid
Pyramid(sides=3, r=8, h=12)             # triangular
```

![Pyramid](images/pyramid.png)

*`Pyramid(sides=4, r=12, h=20)` — a square pyramid with apex above the origin.*

## `Prismoid(bot_w, bot_d, top_w, top_d, h, shift=(0, 0))`

Rectangular frustum: a rectangle `bot_w` × `bot_d` on z=0 tapering to `top_w` × `top_d` at z=`h`. `shift=(dx, dy)` offsets the top face relative to the base center — useful for transition parts. For a pointed apex (rectangular pyramid), use `Pyramid` with `sides=4`.

```python
Prismoid(bot_w=20, bot_d=20, top_w=10, top_d=10, h=15)
Prismoid(bot_w=20, bot_d=20, top_w=10, top_d=10, h=15, shift=(5, 0))
```

![Prismoid](images/prismoid.png)

*`Prismoid(bot_w=20, bot_d=20, top_w=10, top_d=10, h=15)` — a truncated square pyramid.*

## `Wedge(base_w, base_h, thk, fillet=0)`

Right-triangular prism. Cross-section is a right triangle with legs along +x (`base_w`) and +y (`base_h`), extruded `thk` along +z; the right-angle vertex sits at the origin. Doubles as the library's rib / gusset shape. `fillet` (default 0) softens all three corners; note that rounding an acute corner shrinks the envelope by more than the fillet radius, so shallow triangles shrink noticeably.

```python
Wedge(base_w=10, base_h=6, thk=20)              # bare ramp / gusset
Wedge(base_w=10, base_h=6, thk=20, fillet=1)    # rounded corners
```

![Wedge](images/wedge.png)

*`Wedge(base_w=10, base_h=6, thk=20)` — triangular-prism ramp or rib.*

## Platonic solids

All inscribed in a sphere of radius `r`, centered on the origin.

```python
Tetrahedron(r=10)
Octahedron(r=10)
Dodecahedron(r=10)
Icosahedron(r=10)
```

![Icosahedron](images/icosahedron.png)

*`Icosahedron(r=15)` — a 20-faced regular polyhedron, inscribed in a sphere of radius 15.*

## `Torus(major_r, minor_r)`

Donut centered on the origin in the XY plane. Optional `angle` for a partial sweep.

```python
Torus(major_r=20, minor_r=5)            # full ring
Torus(major_r=20, minor_r=5, angle=180) # half ring
```

`minor_r` must be less than `major_r`.

![Torus](images/torus.png)

*`Torus(major_r=20, minor_r=5)` — a donut lying flat in the XY plane.*

## `Dome(any two of: sphere_r, cap_height, cap_dia, cap_r)`

A portion of a sphere sliced by a plane. Flat face on z=0, curved surface rising in +z (apex at z=`cap_height`). Four parameters linked by two equations — supply any consistent pair and the solver fills in the rest. Solid only.

```python
Dome(sphere_r=15, cap_height=15)        # hemisphere
Dome(cap_dia=30, cap_height=15)         # same hemisphere, diameter form
Dome(sphere_r=20, cap_height=8)         # shallow cap
Dome(cap_dia=30, cap_height=5)
```

Parameters: `cap_height`, `cap_dia`, `cap_r`, `sphere_r`. You can read all four off the instance once it's built.

For a hollow shell, build it from two domes:

```python
outer = Dome(sphere_r=15, cap_height=15)
inner = Dome(sphere_r=13, cap_height=13)
shell = difference(outer, inner)
```

Anchors: `base` (flat z=0 face, `rim_radius=cap_r`) and `surface` (`kind=spherical`, sphere center at `z = cap_height − sphere_r`, reach with `polar=`/`angle=`). Polar angles past the cap's rim land in empty space — the framework doesn't clamp.

![Dome](images/dome.png)

*`Dome(sphere_r=15, cap_height=15)` — a hemisphere (the special case where the cap's apex sits on the sphere's equator).*

See [examples/convex-caliper.py](../examples/convex-caliper.py) for a worked example using `Dome` as a feeler tip.

## `Ogive(base_r, length, kind="tangent")`

Pointed nose cone — a solid of revolution with a chosen meridian. Base on z=0 (radius `base_r`), tip on the axis at z=`length`. `base_d` is also accepted (`base_d = 2 · base_r`).

`kind` selects the meridian shape:

- `"tangent"` (default) — circular arc tangent to the body cylinder at the base. The classic rocketry tangent ogive; arc radius `ρ = (base_r² + length²) / (2·base_r)`. Requires `length ≥ base_r` (shorter tangent ogives degenerate into a bulged shape; for blunt noses use `parabolic` or `elliptical`).
- `"parabolic"` — `r(z) = base_r · √(1 − z/length)`, the n=½ power-series ogive used by the rocket showcase.
- `"elliptical"` — half-ellipse meridian: `r(z) = base_r · √(1 − (z/length)²)`. Allows blunt noses (`length < base_r`).

```python
Ogive(base_r=10, length=18)                       # tangent (default)
Ogive(base_r=10, length=18, kind="parabolic")     # rocket-nose flavor
Ogive(base_d=20, length=8, kind="elliptical")     # blunt half-ellipse
```

Anchors: `base` (planar at z=0 with `rim_radius=base_r`, so `add_text(on="base")` arc-on-rim works) and `tip` (point at z=`length`, `+z` normal). The tip is a vertex, not a face.

## `Paraboloid(radius, depth, focal_length)`

Solid bowl paraboloid — vertex at the origin, rim disk at z=`depth` with radius `radius`. Meridian: `r(z) = 2·√(f·z)` where `f` is the focal length, related by `4·f·depth = radius²`. Specify any consistent two of `radius`/`diameter`, `depth`, `focal_length`; the framework solves the rest.

```python
Paraboloid(radius=10, depth=8)              # rim r=10 at z=8, vertex at origin
Paraboloid(diameter=20, depth=8)            # diameter alternative
Paraboloid(radius=10, focal_length=3.125)   # depth solved (4·f·d = r²)
```

Anchors: bbox-derived `bottom` is the vertex point (z=0). Declared `top` is the rim disk at z=`depth` with `rim_radius=radius`, so `add_text(on="top")` arc-on-rim works for labels around the dish edge.

Solid only — a constant-thickness shell isn't a parabolic offset of itself, so hollow dishes need an explicit subtract: `difference(Paraboloid(...), Paraboloid(...).up(thk))`.

Distinct from [`Ogive(kind="parabolic")`](#ogivebase_r-length-kindtangent), which uses the same parabola but with the tip pointing up (a nose cone). Paraboloid has the vertex on the ground and opens upward (a bowl or dish).

## `Ellipsoid(a, b, c)`

Sphere with three independent semi-axes — centered on the origin (matches `sphere()` convention; chain `.up(c)` for a sitting-on-the-ground orientation). Each axis accepts a diameter alternative (`dx = 2a`, `dy = 2b`, `dz = 2c`); mix and match per axis.

```python
Ellipsoid(a=10, b=8, c=6)        # all radii
Ellipsoid(dx=20, dy=16, dz=12)   # all diameters
Ellipsoid(a=10, dy=16, c=6)      # mixed
```

The bbox-derived face anchors (`top`, `bottom`, `lside`, `rside`, `front`, `back`) sit exactly on the six axis-tip points — the ellipsoid is tangent to its bbox at those tips — so `.attach()` lines up cleanly without custom anchors.

## `Elbow(id, od, thk, bend_radius, angle=90)`

Hollow pipe bend — partial torus with wall thickness. The two end-faces are perpendicular to the tube axis at angle=0 and angle=`angle`, both planar with `rim_radius=od/2` so they mate cleanly with another pipe via `attach()`. `id`/`od`/`thk` follow the same pattern as `Tube` (`od = id + 2·thk`); specify any two. Default `angle=90` (the most common pipe bend); `angle ∈ (0, 360]`.

```python
Elbow(id=8, od=12, bend_radius=20)            # 90° elbow
Elbow(id=8, thk=2, bend_radius=20, angle=180) # 180° U-bend, od solved
Elbow(od=12, thk=2, bend_radius=20)           # id solved
```

The `od/2 < bend_radius` constraint prevents the tube from self-intersecting on the inner side — pick a `bend_radius` larger than the tube's outer radius.

Anchors: `start` at the angle=0 face (position `(bend_r, 0, 0)`, normal -y), and `end` at the angle=`angle` face (position and normal computed from the swept angle). Both planar with `rim_radius=od/2`, so `add_text(on="start", relief=-0.3)` engraves a label on the rim.

## `Capsule(r, length)`

Pill / stadium solid: a cylinder with hemispherical caps on both ends. `length` is the total end-to-end distance along +z (hemispheres included); `r` is the radius of both the cylinder and the caps. The straight-section height is readable on the instance as `straight_length`. `base` and `tip` anchors at z=0 and z=length point outward. For a horizontal capsule, rotate the result.

```python
Capsule(r=3, length=20)                             # vertical (z) pill
Capsule(r=3, length=20).rotate([0, 90, 0])          # horizontal along x
```

![Capsule](images/capsule.png)

*`Capsule(r=3, length=20)` — cylinder plus hemispheres, a common handle/grip profile.*

## `PieSlice(r, angles, h)`

3D cylindrical sector: a `Sector` profile extruded along +z. `angles` is a `(start_deg, end_deg)` pair, same as `Sector`.

```python
PieSlice(r=10, angles=(0, 90), h=5)
```

![Pie slice](images/pie-slice.png)

*`PieSlice(r=10, angles=(0, 90), h=5)` — a 90° cylindrical wedge.*
