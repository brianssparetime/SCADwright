# A 2D profile on a surface with `wrap_2d()`

`wrap_2d()` puts a 2D profile, most often an imported SVG logo, on a host's surface as raised or inset relief, the way [`add_text()`](add_text.md) puts wrapped text there. Placement uses [anchors](anchors.md), the same system `attach()` and `add_text()` use. After `wrap_2d()`, the host's anchors stay intact, so you can chain more decorations or call `attach()`.

```python
from scadwright.primitives import cube, cylinder, sphere, scad_import, polygon
from scadwright.shapes import Tube, Barrel
```

- [The 30-second version](#the-30-second-version)
- [The profile](#the-profile)
- [Sizing with `size=`](#sizing-with-size)
- [Two projections: `wrap` and `flat`](#two-projections-wrap-and-flat)
- [Where the relief goes](#where-the-relief-goes)
- [Inner walls](#inner-walls)
- [Raised vs inset](#raised-vs-inset)
- [The geometry without the host](#the-geometry-without-the-host)
- [Argument reference](#argument-reference)
- [Things that fail](#things-that-fail)

## The 30-second version

```python
logo = scad_import("logo.svg", bbox=((0, 0, 0), (124, 106, 0)))

# Raised on a flat lid:
cube([60, 60, 4], center="xy").wrap_2d(profile=logo, relief=1.0, on="top", size=40)

# Wrapped around a bottle, inset:
cylinder(h=80, r=25).wrap_2d(profile=logo, relief=-0.8, on="outer_wall", size=60)
```

`relief` is signed: positive raises the profile outward by that amount and unions it on, negative cuts it that deep into the host. `size=` sets the profile's width in mm (aspect preserved). `on=` picks a surface by anchor name, exactly as in `add_text()`.

## The profile

`profile=` is any 2D node. The common source is an imported SVG:

```python
logo = scad_import("logo.svg", bbox=((0, 0, 0), (124, 106, 0)))
```

OpenSCAD fills the interior of closed paths and ignores stroke, stroke-width, fill color, and opacity. Line art drawn as strokes imports as nothing; author it as filled outlines. Holes come from opposite path winding (even-odd / nonzero), not from white overlays.

The `bbox=` hint is the profile's extent in mm as OpenSCAD imports it. OpenSCAD maps an SVG's pixels to mm at about 72 dpi, so a 351 px-wide drawing arrives near 124 mm — pass that, not the SVG's `viewBox` width. The hint is what `size=` scales against, so it has to match the imported geometry. A polygon or other built profile carries its own extent and needs no hint:

```python
star = polygon([(0, 10), (3, 3), (10, 3), (4, -2), (6, -9), (0, -4),
                (-6, -9), (-4, -2), (-10, 3), (-3, 3)])
cylinder(h=40, r=15).wrap_2d(profile=star, relief=0.6, on="outer_wall", size=18)
```

## Sizing with `size=`

`size=` is the profile's target size in mm:

```python
panel = cube([80, 80, 4], center="xy")
panel.wrap_2d(profile=logo, relief=1.0, on="top", size=50)        # 50 mm wide, aspect kept
panel.wrap_2d(profile=logo, relief=1.0, on="top", size=(50, 30))  # 50 x 30 mm, may distort
panel.wrap_2d(profile=logo, relief=1.0, on="top")                 # the profile's own extent
```

A scalar sets the width and preserves aspect; a `(w, h)` pair sets both. `None` uses the profile's bbox as-is.

## Two projections: `wrap` and `flat`

A profile reaches a curved surface in one of two ways, chosen by `projection=`.

`projection="wrap"` slices the profile into columns and lays each one tangent at its arc angle. It is developable and keeps proportions (arc length on the surface matches the flat drawing), so it is the faithful choice on a cylinder, where it is the default.

```python
cylinder(h=80, r=25).wrap_2d(profile=logo, relief=-0.8, on="outer_wall", size=60)  # projection="wrap"
```

`projection="flat"` presses the profile straight onto the surface from one direction, a flat orthographic projection. It bounds the relief with the host surface itself, so the depth is uniform and the result is watertight on any curved wall. It is the only projection on a sphere, cone, or barrel, and it is their default.

```python
sphere(r=30).wrap_2d(profile=logo, relief=-1.0, on="+z", size=24)   # projection="flat"
cylinder(h=60, r1=30, r2=18).wrap_2d(profile=logo, relief=0.8, on="outer_wall", size=20)  # cone
Barrel(h=80, end_r=25, bulge=10).wrap_2d(profile=logo, relief=-1.0, on="outer_wall", size=30)
```

The flat projection distorts toward grazing angles, so it suits a small shape on a large surface — a badge on a domed lid, a ball, a fat barrel. A shape that spans a wide arc smears at its edges; reach for `wrap` on a cylinder when proportions matter.

The default follows the surface: `wrap` on a cylinder, `flat` everywhere else. Pass `projection=` to override.

## Where the relief goes

Placement reuses `add_text()`'s vocabulary. Pass `on=` as an anchor name, or place ad-hoc with `at=` + `normal=`:

```python
cyl = cylinder(h=60, r=20)
cyl.wrap_2d(profile=logo, relief=0.6, on="outer_wall", size=24)                 # default +X meridian
cyl.wrap_2d(profile=logo, relief=0.6, on="outer_wall", size=24, angle="back")   # face name
cyl.wrap_2d(profile=logo, relief=0.6, on="outer_wall", size=24, angle=37)       # degrees CCW
cyl.wrap_2d(profile=logo, relief=-0.4, on="outer_wall", size=20, at_z=-12)      # 12 mm below mid-wall
```

`angle=` (the angular position around the axis) and `at_z=` (the axial offset from mid-wall) apply on cylindrical, conical, and barrel walls. A sphere places by `on=` or `at=` alone.

## Inner walls

A hollow shape's `inner_wall` takes a profile the same way an outer wall does. Raised relief stands into the bore, and inset cuts outward into the wall.

```python
Tube(h=40, od=30, thk=6).wrap_2d(profile=logo, relief=-0.6, on="inner_wall", size=12)   # engraved inside the bore
```

## Raised vs inset

`relief > 0` raises the profile and unions it onto the host; `relief < 0` cuts it that deep and is a difference. The depth is measured normal to the surface, and the host's anchors survive either way:

```python
lid = cylinder(h=4, r=30)
lid.wrap_2d(profile=logo, relief=0.8, on="top", size=40)    # stands proud
lid.wrap_2d(profile=logo, relief=-0.5, on="top", size=40)   # engraved
```

## The geometry without the host

`wrap_2d_geometry()` returns the placed relief on its own, without combining it with the host — for use as a cutter, or to pull a difference out of a `force_render` scope so the cached body does not re-evaluate it. Same kwargs as `wrap_2d()`; the sign of `relief` still chooses the direction.

```python
smooth = body.force_render()
cutter = body.wrap_2d_geometry(profile=logo, relief=-0.6, on="outer_wall", size=30)
result = difference(smooth, cutter)
```

## Argument reference

| Argument | Meaning |
| --- | --- |
| `profile` | The 2D node to place (imported SVG, polygon, outline). Required. |
| `relief` | Signed depth in mm. Positive raises and unions; negative insets and differences. Required. |
| `on` | Anchor name or `Anchor`. |
| `at`, `normal` | Ad-hoc 3D placement: a coordinate and a direction. |
| `angle` | Angular position around the axis (degrees CCW or a face name). Cylindrical, conical, and barrel walls. |
| `at_z` | Axial offset from mid-wall, in mm. Cylindrical, conical, and barrel walls. |
| `size` | Target size in mm: a scalar (width, aspect kept) or a `(w, h)` pair. `None` uses the profile's extent. |
| `projection` | `"wrap"` (developable, cylinder) or `"flat"` (orthographic, any curved wall). Defaults by surface. |
| `segments` | Column count for `"wrap"`. Higher is smoother, lower is faster. Ignored by `"flat"`. |
| `eps` | Host overshoot that keeps the boolean watertight. Defaults from tolerances. |

## Things that fail

- `projection="wrap"` on a sphere or barrel: a flat drawing has no developable map onto a non-developable surface. Use `flat`.
- `projection="wrap"` on a cone: the flat-slice wrap leaves non-manifold seams on the taper. Use `flat` (the default on cones).
- A relief deeper than the barrel's meridian radius of curvature: the offset surface would self-intersect. Use a shallower relief.
- A relief that reaches the bore axis or the sphere center: too deep for the radius. Use a shallower relief.
- `relief == 0`: nothing to add or cut.
- A 3D `profile`: pass a 2D node, not an extruded solid.
- An imported profile with no `bbox=` hint: it cannot be sized or placed — give `scad_import` the extent.
- `angle=` or `at_z=` on a sphere or flat face: those set the position on a cylindrical, conical, or barrel wall.
