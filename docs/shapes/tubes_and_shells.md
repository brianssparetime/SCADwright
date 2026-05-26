# Tubes and shells

Parametric hollow shapes with equation-driven dimensions.

```python
from scadwright.shapes import Tube, Funnel, RoundedBox, UShapeChannel, RectTube, Barrel, SphericalShell
```

## `Tube(h, id|od|thk)`

Hollow cylinder. Specify any two of inner diameter, outer diameter, and wall thickness; the framework solves the third.

```python
Tube(h=10, id=8, thk=1)      # od solved = 10
Tube(h=10, id=8, od=10)      # thk solved = 1
Tube(h=10, od=10, thk=1)     # id solved = 8
```

![Tube](images/tube.png)

*`Tube(od=20, id=16, h=30)` — a thick-walled hollow cylinder.*

## `Funnel(h, thk, top_*, bot_*)`

Tapered tube. For each end, specify one of the inner or outer diameter.

```python
Funnel(h=20, thk=2, bot_id=10, top_id=14)
Funnel(h=20, thk=2, bot_od=14, top_od=18)
Funnel(h=20, thk=2, bot_id=10, top_od=18)    # mix and match
```

![Funnel](images/funnel.png)

*`Funnel(h=30, thk=2, bot_id=8, top_id=30)` — a wide-top taper to a narrow bottom.*

## `RoundedBox(size, r)`

Box with all edges rounded by a sphere of radius `r`. Centered on the origin. Each `size` axis must be larger than `2*r`.

```python
RoundedBox(size=(20, 10, 5), r=1)
```

![Rounded box](images/rounded-box.png)

*`RoundedBox(size=(40, 25, 15), r=3)` — a box with every edge and corner smoothly filleted.*

## `UShapeChannel(channel_width, channel_height, outer_width, outer_height, wall_thk, channel_length)`

Three-sided rectangular channel with equation-driven dimensions. Specify `channel_length` plus any two cross-section params; the framework solves the rest. `n_shape=True` flips the opening downward.

```python
UShapeChannel(wall_thk=2, channel_length=20, channel_width=10)
UShapeChannel(wall_thk=2, channel_length=20, channel_width=10, n_shape=True)
```

You can read `bottom_width`, `outer_width`, `outer_height` off the instance. Declares a `channel_opening` anchor at the center of the open face.

## `RectTube(outer_w, outer_d, inner_w, inner_d, wall_thk, h)`

Rectangular hollow tube. Two cross-section equations couple outer and inner by `wall_thk`, so any combination that fixes both per-axis dimensions is sufficient (e.g. `outer_w + wall_thk` → inner solved; `inner_w + outer_w` → wall_thk solved).

```python
RectTube(outer_w=30, outer_d=20, wall_thk=2, h=10)      # inner solved
RectTube(inner_w=20, inner_d=12, wall_thk=3, h=10)      # outer solved
```

![Rect tube](images/rect-tube.png)

*`RectTube(outer_w=30, outer_d=20, wall_thk=2, h=10)` — rectangular sibling of `Tube`.*

## `Barrel(h, end_d|end_r, mid_d|mid_r|bulge, thk?)`

Solid (or hollow) of revolution with a circular-arc meridian. End faces have diameter `end_d` at z=0 and z=h; the wall passes through diameter `mid_d` at the equator. `bulge = mid_r - end_r` is the signed radial sagitta — positive for the classic convex wine-barrel, negative for a waisted (concave) profile. Specify any consistent pair of (`end_d`/`end_r`) and (`mid_d`/`mid_r`/`bulge`); the framework solves the rest.

```python
Barrel(h=80, end_d=50, mid_d=64)             # convex (wine barrel)
Barrel(h=80, end_d=50, bulge=7)              # equivalent
Barrel(h=80, end_d=50, mid_d=42)             # concave (waist / hourglass)
Barrel(h=80, end_d=50, mid_d=64, thk=3)      # hollow shell, constant radial wall
```

Anchors:
- `top`, `bottom` — planar end faces with `rim_radius=end_r`. Same shape as `Tube`'s rims, so `add_text(on="top")` arcs work directly.
- `outer_wall` — `kind="meridional"`. The reference position is at the equator on the +X meridian; `attach(barrel, on="outer_wall", at_z=z, angle=θ)` lands a child *on the actual curved surface* at that axial offset (not on a cylinder approximation), with the surface normal locally tilted to the meridian's tangent plane. `at_z=0` is the equator, `at_z=±h/2` is a rim.
- `inner_wall` — same kind, on the bore meridian (`mid_r-thk` at the equator). Only meaningful when the barrel is hollow.

`add_text(on="outer_wall", angle=θ, at_z=z)` and `add_text(on="inner_wall", ...)` wrap the label along the curved wall: per-glyph radius and tilt follow the meridian, so text sits flush whether the barrel is convex or concave.

A `bulge` of exactly zero degrades silently to the equivalent `cylinder` or `Tube`, so parametric sweeps that cross zero curvature don't need a special-case branch. Pinched waists where `mid_r` collapses toward zero emit a `BarrelDegeneracyWarning` (filterable via the standard `warnings` module) but still build the geometry.

## `SphericalShell(id|od|thk)`

Hollow sphere centered at the origin. Provide any two of (`id`, `od`, `thk`); the third is solved (`od = id + 2*thk`).

```python
SphericalShell(od=20, id=14)             # 3 mm wall, 14 mm bore
SphericalShell(od=20, thk=3)             # equivalent; id solved
SphericalShell(id=14, thk=3)             # equivalent; od solved
```

Anchors:
- `outer_wall` — `kind="spherical"`, on the outer surface.
- `inner_wall` — `kind="spherical"`, `inner=True`, on the bore.

`sphere(d=14).fuse(SphericalShell(od=20, id=14))` auto-matches the sphere's outer surface to the shell's `inner_wall`. `SphericalShell` is the only standard-library shape that declares an `inner=True` spherical anchor, so it's the natural counterpart for fitting a sphere into a bore.
