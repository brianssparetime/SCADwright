# Attaching shapes with `attach()`

`attach()` positions one shape relative to another by naming which faces should touch. You don't have to compute the coordinate math yourself.

The names you pass to `attach()` are *anchors*: named points on a shape's surface. Every shape gets six by default (one per face of the bounding box), and Components can name more. See [Anchors](anchors.md) for what anchors are and how to declare your own; this page is about using them with `attach()`.

Imports used on this page:

```python
from scadwright.primitives import cube, cylinder, sphere
from scadwright.shapes import Tube, Funnel
```

## Basic usage

Stack a peg on top of a plate:

```python
plate = cube([40, 40, 2])
peg   = cube([10, 10, 5]).attach(plate)    # bottom of peg on top of plate
```

`attach()` defaults to `on="top"` (the anchor on the other shape) and `using_anchor="bottom"` (the anchor on self), so `peg.attach(plate)` means "put my bottom on your top."

## Choosing faces

Use `on=` and `using_anchor=` to pick which anchors line up:

```python
peg.attach(plate, on="bottom", using_anchor="top")       # peg underneath plate
peg.attach(plate, on="rside", using_anchor="lside")      # peg to the right of plate
peg.attach(plate, on="top", using_anchor="top")          # align top faces (peg hangs down)
```

`on` names the anchor on the parent (the thing being attached to). `using_anchor` names the anchor on self (the thing being moved). The same `on` convention is used by `add_text()`.

Both accept friendly names (`"top"`, `"bottom"`, `"front"`, `"back"`, `"lside"`, `"rside"`) or axis-sign aliases (`"+z"`, `"-z"`, `"+y"`, `"-y"`, `"+x"`, `"-x"`). Friendly names read better in code.

Custom Component anchors are referenced by their attribute name on the Component:

```python
sensor = cube([8, 8, 4]).attach(Bracket(w=20, thk=3, depth=15), on="mount_face")
```

## Rotating so faces touch: `orient=True`

By default, `attach()` only translates: self moves but doesn't rotate. Pass `orient=True` to also rotate self so the two anchors point at each other, putting their faces in contact:

```python
peg.attach(plate, on="rside", using_anchor="bottom", orient=True)
```

This rotates the peg so its bottom faces in the `-X` direction, opposite to the plate's `rside` (`+X`) face. After the rotation, `attach()` translates the peg into place.

When the two anchors already point at each other (for example, `bottom` to `top`), `orient=True` doesn't add rotation; it produces the same result as `orient=False`.

## Chaining placements after `attach()`

`attach()` returns a shape, so you can chain `.right()`, `.up()`, and other directional helpers to offset the placed part:

```python
peg.attach(plate).right(10)              # on top, shifted 10 in +X
peg.attach(plate, orient=True).up(2)     # face-down, 2 mm above the contact
```

See [Transformations](transformations.md) for the full list of chained helpers.

## Placement on cylinders, cones, and spheres

Cylinders, cones, spheres, and their rims and caps know how their surfaces are shaped, so `attach()` can place things by angle or position on the surface instead of by raw `(x, y, z)`. Four options cover the common cases: `angle=`, `at_z=`, `at_radial=`, and `polar=`. Each is described below.

### Angular position: `angle=`

For attachments at a specific angle around a cylinder, cone, or rim, pass `angle=` (degrees CCW from `+X`, or one of the friendly aliases `"rside"`, `"back"`, `"lside"`, `"front"`, `"+x"`, `"+y"`, `"-x"`, `"-y"`):

```python
hub = cylinder(h=20, r=10)
peg = cube([2, 2, 5])

# Around the cylinder's wall:
peg.attach(hub, on="outer_wall", angle=30)              # peg at 30° on the wall
peg.attach(hub, on="outer_wall", angle="back")          # same as angle=90

# On the top cap, at the rim:
peg.attach(hub, on="top", angle=0)                      # rim at +X
peg.attach(hub, on="top", angle=120)                    # rim at 120°
```

`angle=` works on three kinds of surface:

- **Cylindrical wall** (`outer_wall` of a cylinder). `angle=` rotates the anchor around the surface axis. Self lands at that angular position on the wall, with the normal pointing radially outward.
- **Conical wall** (`outer_wall` of a cone, where `r1 != r2`). Same rotation. The wall is slanted, though, so `orient=True` aligns self perpendicular to the slanted wall, not perpendicular to the cone's central axis. So `peg.attach(cone, on="outer_wall", angle=0, orient=True)` tilts the peg with the surface.
- **Cap with rim radius** (`top` / `bottom` of a cylinder or cone). `angle=` places at that angular position on the cap. By default the part sits on the rim itself; pass `at_radial=` to put it interior to the rim (see below).

On other anchors (a cube's `top`, a custom Component anchor without these surface details), `angle=` raises a clear error.

### Axial offset: `at_z=`

Pass `at_z=` to shift along the wall axis ("5 mm above mid-wall"). The argument is mm offset from the anchor's reference axial position, which is mid-wall on `outer_wall`:

```python
peg.attach(hub, on="outer_wall", at_z=5)              # +X meridian, 5 mm above mid-wall
peg.attach(hub, on="outer_wall", angle=30, at_z=5)    # 30° meridian, 5 mm above mid-wall
```

`at_z=` shifts along the cylinder's actual axis line, so it tracks correctly when the host has been translated or rotated. Compare with chaining `.up(5)` after `attach()`: that one translates in world space, and only matches the cylinder's axis when the cylinder happens to point along world `+Z`.

On a conical wall, `at_z=` also adjusts the position outward (or inward) so the anchor stays on the slanted surface. If `at_z=` would push past the cone's tip, you get a clear error instead of broken geometry.

`at_z=` only applies to cylindrical, conical, and meridional walls. On a rim, use `at_radial=` for the in-plane radial offset. On a cube face or any anchor without a surface axis, `at_z=` raises.

### Radial offset on a cap: `at_radial=`

For placements inside the rim of a cap (not on the rim itself), pass `at_radial=`:

```python
peg.attach(hub, on="top", angle=0, at_radial=5)         # 5 mm from cap center
peg.attach(hub, on="top", angle=0, at_radial=0)         # exact cap center
```

`at_radial=` overrides the default of the cap's full radius. `at_radial=0` puts the part right at the cap's center.

`at_radial=` requires `angle=`, because cap placement uses both an angle and a radius. It only works on cap anchors that have a `rim_radius`. On a cube's `top`, a cylindrical wall, or a sphere, it raises an error.

The same option name and meaning are used by `add_text(at_radial=)` for the radius of a rim-arc text path.

### Polar and azimuth on a sphere: `polar=` + `angle=`

A `sphere()` has the six standard face anchors (each one tangent to the sphere where the bounding-box face would touch). It also has a `surface` anchor that lets you place a part anywhere on the sphere using polar angle and azimuth:

```python
ball = sphere(r=10)

peg.attach(ball, on="surface", polar=30, angle=45)   # 30° from +Z axis, 45° azimuth
peg.attach(ball, on="surface", angle=90)             # equator wrap (polar defaults to 90)
peg.attach(ball, on="surface", polar=0)              # north pole
peg.attach(ball, on="surface", polar=180)            # south pole
```

`polar=` is degrees from the north-pole direction (range `[0, 180]`). `angle=` here is the azimuth, degrees CCW from the `+X` meridian. If only `angle=` is supplied, `polar` defaults to 90 (equator). If only `polar=` is supplied, `angle` defaults to 0 (the `+X` meridian).

`at_z=` and `at_radial=` aren't valid on spherical anchors. Sphere placement uses the `polar` / `angle` pair only.

The math uses the host's local frame, so a sphere that's been translated, rotated, or scaled tracks correctly. For example, `sphere(r=5).rotate([0, 90, 0])` rotates the north pole to point along `+X`, and `polar=0` lands at the rotated pole.

### Shapes with extra anchors

| Shape | Extra anchors |
|---|---|
| `cylinder()` | `outer_wall`, plus angle and radius placement on `top` and `bottom` |
| `Tube` | `outer_wall`, `inner_wall`, plus angle and radius placement on `top` and `bottom` |
| `Funnel` | `outer_wall` and `inner_wall` (both conical), plus angle and radius placement on `top` and `bottom` |
| `sphere()` | `surface` (in addition to the six standard faces) |
| `Barrel` | `outer_wall` and `inner_wall` (curved meridian), plus angle and radius placement on `top` and `bottom` |

Other shapes like `cube()`, `RectTube`, `RingGear`, `Bearing`, and `RoundedBox` only have the six standard face anchors. Their outer surfaces aren't simple curved surfaces (they're rectangular, toothed, and so on), so `angle=` doesn't have a meaningful target. Use the standard face anchors, or attach to a plain `cylinder()` if you need angular placement.

## Clean joints with `fuse=True`

When two parts share a flat face, OpenSCAD's preview shows a seam where the surfaces meet. Pass `fuse=True` to add a tiny overlap that fixes it:

```python
pylon = Tube(od=7, id=3, h=8).attach(floor, fuse=True)
```

`fuse=True` only works on flat-face contacts. On a cylinder, cone, or sphere it raises an error and points at `bridge=True` instead. For the full mechanism (`bond=`, `disable_eps_fuse()`, known limits, the symmetric `fuse(a, b, ...)` form, and `through()` for cutters), see [Eliminating manual epsilon overlap](auto-eps_fuse_and_through.md).

## Attaching to a curved surface: `bridge=True`

A flat-bottomed peg attached to a cylinder, cone, or sphere with the usual `attach()` leaves a visible gap where the peg touches the curve; the peg looks balanced on a thin contact line. Pass `bridge=True` to fill that gap with a small piece of material so the peg looks merged into the host:

```python
peg = cube([2, 2, 5])
hub = cylinder(h=20, r=10)
mount = peg.attach(hub, on="outer_wall", angle=30, orient=True, bridge=True)
```

The bridge is part of the final design, not a rendering tweak. It fills the empty space between the peg's flat side and the curved surface so the part both looks and prints as one piece.

By default the bridge sits flush against the peg, which means the peg-and-bridge boundary is a coincident plane. If you also want that union to render without a seam, add `fuse=True`:

```python
peg.attach(hub, on="outer_wall", angle=30, orient=True, bridge=True, fuse=True)
```

`bridge=True` only works on the outside of a cylinder, cone, or sphere. On a tube's inner wall the peg's corners already sink into the wall material, so there's no gap to fill; pass `bond="shift"` instead for a clean union there.

`bridge=True` and `bond=` can't combine. `bond=` is for the flat-face overlap mechanism; `bridge=True` is the curved-surface fill. Passing both gives an error.

For how the bridge is built, what it checks, and the limitations to watch for, see [Putting things on curved surfaces](anchors.md#putting-things-on-curved-surfaces-bridge-true) in `anchors.md`.

## Naming convention

The four placement options that show up across `attach()`, `add_text()`, and anchor declarations:

| Option | Type | Meaning |
|---|---|---|
| `on=` | string (anchor name) or `Anchor` | The anchor on the *other* shape (the one being attached to). |
| `using_anchor=` | string (anchor name) | The anchor on *self* (the shape being moved). Only on `attach()` and `fuse()`. |
| `at=` | 3-tuple or string expression | A 3D position. Used by `anchor()` declarations, `with_anchor()`, and `add_text()`'s ad-hoc placement (paired with `normal=`). Always a coordinate, never an offset. |
| `offset=` | 2-tuple (mm) | An in-face nudge for a named anchor (only on `add_text()`). 2D offset along the face. |

The split keeps `at=` consistent: it always means "a 3D coordinate in some local frame." For nudging a named anchor along the face it sits on, use `offset=` instead.

Anchor-name options (`on=`, `using_anchor=`) and position options (`at=`) stay distinct: anchor names are always selectors, coordinates are always coordinates.

## Advanced notes

### Symmetric form: `fuse(a, b, ...)`

`attach(fuse=True)` only extends `self`. If `self` can't be extended at the contact face but `other` can, the extension is lost: `other` isn't part of the returned shape. For cases where either side might need to carry the extension, use the free function `fuse(a, b, on=..., using_anchor=..., ...)` from `scadwright.boolops`. It picks whichever side qualifies, and when both do it picks the one that produces simpler output. See the dispatch table in [Eliminating manual epsilon overlap](auto-eps_fuse_and_through.md).
