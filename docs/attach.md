# Attaching shapes — `attach()`

`Node.attach()` positions one shape relative to another by naming which faces should touch. No manual coordinate math.

Anchors are the named attachment points this verb consumes — every shape gets six by default, and Components can declare their own. See [Anchors](anchors.md) for the data type and authoring API; this page is about *using* them.

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

Use `on=` and `using_anchor=` to pick which anchors to align:

```python
peg.attach(plate, on="bottom", using_anchor="top")       # peg underneath plate
peg.attach(plate, on="rside", using_anchor="lside")      # peg to the right of plate
peg.attach(plate, on="top", using_anchor="top")          # align top faces (peg hangs down)
```

`on` names the anchor on the parent (the thing being attached to); `using_anchor` names the anchor on self (the thing being moved). The same `on` convention is used by `add_text()`.

Both `on` and `using_anchor` accept friendly names (`"top"`, `"bottom"`, `"front"`, `"back"`, `"lside"`, `"rside"`) or axis-sign aliases (`"+z"`, `"-z"`, `"+y"`, `"-y"`, `"+x"`, `"-x"`). Friendly names are preferred in code.

Custom Component anchors are referenced by their attribute name on the Component:

```python
sensor = cube([8, 8, 4]).attach(Bracket(w=20, thk=3, depth=15), on="mount_face")
```

## Orienting to oppose normals — `orient=True`

By default, `attach()` only translates. Pass `orient=True` to also rotate self so the two anchors' normals oppose each other (faces touching):

```python
peg.attach(plate, on="rside", using_anchor="bottom", orient=True)
```

This rotates the peg so its bottom normal faces in the -X direction (opposing the plate's rside +X normal), then translates it into position.

When the normals already oppose (e.g. attaching bottom-to-top), `orient=True` produces the same result as `orient=False`.

## Chaining placements after `attach()`

`attach()` returns a Node, so directional helpers chain naturally for offset placement:

```python
peg.attach(plate).right(10)              # on top, shifted 10 in +X
peg.attach(plate, orient=True).up(2)     # face-down, 2mm above the contact
```

See [Transformations](transformations.md) for the full set of chained helpers.

## Parametric placement on rotational surfaces

Cylinders, cones, spheres, and the rim/cap of those shapes carry surface metadata on their anchors (a central axis, a radius, a meridian-zero direction). That lets `attach()` accept parametric kwargs — `angle=`, `at_z=`, `at_radial=`, `polar=` — that compute a placement point on the surface for you.

### Angular position — `angle=`

For attachments at a specific angle around a cylinder, cone, or rim, pass `angle=` (degrees CCW from +X, or one of the friendly aliases `"rside"`, `"back"`, `"lside"`, `"front"`, `"+x"`, `"+y"`, `"-x"`, `"-y"`):

```python
hub = cylinder(h=20, r=10)
peg = cube([2, 2, 5])

# Around the cylinder's wall:
peg.attach(hub, on="outer_wall", angle=30)              # peg at 30° meridian on the wall
peg.attach(hub, on="outer_wall", angle="back")          # = angle=90

# On the top cap, at the rim:
peg.attach(hub, on="top", angle=0)                      # rim at +X
peg.attach(hub, on="top", angle=120)                    # rim at 120°
```

`angle=` works on three anchor surface kinds:

- **Cylindrical wall** (`outer_wall` of a cylinder): `angle=` rotates the anchor's position and normal around the surface axis. The result puts self at that angular position on the wall, normal pointing radially outward.
- **Conical wall** (`outer_wall` of a cone, where `r1 != r2`): same rotation, but the normal used for `orient=True` is the cone's *slanted* surface normal — so `peg.attach(cone, on="outer_wall", angle=0, orient=True)` aligns the peg perpendicular to the slanted wall, not the cone's central axis.
- **Cap with rim radius** (`top` / `bottom` of a cylinder or cone): `angle=` places at angular position on the cap. Default radial position is the cap's rim radius; pass `at_radial=` to override (see below).

For other anchor kinds (a cube's `top`, a custom Component anchor without surface metadata), `angle=` raises a clear error.

### Axial offset — `at_z=`

For attachments along a cylindrical or conical wall — "30° meridian, 5 mm above mid-wall" — pass `at_z=` (mm offset from the anchor's reference axial position, mid-wall on `outer_wall`):

```python
peg.attach(hub, on="outer_wall", at_z=5)              # +X meridian, 5 mm above mid-wall
peg.attach(hub, on="outer_wall", angle=30, at_z=5)    # 30° meridian, 5 mm above mid-wall
```

`at_z=` shifts along the cylinder's actual axis line, so it tracks correctly when the host has been translated or rotated. Compare with chaining `.up(5)` after `attach`, which translates in world space and only matches the cylinder's axis when that axis happens to be world +Z.

On a conical wall, `at_z=` also adjusts the position radially so the new anchor stays on the slanted surface. An `at_z=` that drives the local cone radius non-positive (past the cone tip) raises a clear error rather than silently producing junk geometry.

`at_z=` is only valid on cylindrical, conical, and meridional wall anchors. On a rim, the in-plane radial offset is `at_radial=` instead. On a cube face or other anchor without a surface axis, `at_z=` raises.

### Radial offset on a cap — `at_radial=`

For placements interior to the rim of a cap, pass `at_radial=`:

```python
peg.attach(hub, on="top", angle=0, at_radial=5)         # 5 mm from cap center
peg.attach(hub, on="top", angle=0, at_radial=0)         # exact cap center
```

`at_radial=` overrides the default (the cap's `rim_radius`). `at_radial=0` is the legitimate "center of cap" case.

`at_radial=` requires `angle=` (cap placement is polar; both kwargs are needed together). It's only valid on cap anchors that carry a `rim_radius` — on a cube's `top`, a cylindrical wall, or a sphere, it raises.

The same kwarg name and semantics are used by `add_text(at_radial=)` for the radius of a rim-arc text path.

### Polar / azimuth on a sphere — `polar=` + `angle=`

`sphere()` publishes the six bbox-tangent anchors (all kind `"spherical"`) plus a `surface` anchor for arbitrary polar / azimuth placement:

```python
ball = sphere(r=10)

peg.attach(ball, on="surface", polar=30, angle=45)   # 30° from +Z axis, 45° azimuth
peg.attach(ball, on="surface", angle=90)             # equator wrap (polar defaults to 90)
peg.attach(ball, on="surface", polar=0)              # north pole
peg.attach(ball, on="surface", polar=180)            # south pole
```

`polar=` is degrees from the north-pole direction (range [0, 180]). `angle=` here is the azimuth, degrees CCW from the +X meridian. If only `angle=` is supplied, `polar` defaults to 90 (equator). If only `polar=` is supplied, `angle` defaults to 0 (the +X meridian).

`at_z=` and `at_radial=` are not valid on spherical anchors — sphere placement uses the `polar` / `angle` pair.

The polar/azimuth math uses the host's local frame, so a sphere that has been translated, rotated, or scaled tracks correctly: `sphere(r=5).rotate([0, 90, 0])` rotates the north pole to point along +X, and `polar=0` lands at the rotated pole.

### Which hosts publish which anchor kinds

- `cylinder()` (the primitive) — `outer_wall`, plus rim metadata on `top` and `bottom`.
- `Tube` — `outer_wall`, `inner_wall`, plus rim metadata on `top` and `bottom`.
- `Funnel` — `outer_wall` and `inner_wall` (conical), plus rim metadata on `top` and `bottom`.
- `sphere()` — six bbox-tangent anchors plus `surface`.
- `Barrel` — `outer_wall` and `inner_wall` (curved meridian), plus rim metadata on `top` and `bottom`.

Other shapes — `cube()`, `RectTube`, `RingGear`, `Bearing`, `RoundedBox`, etc. — only carry the six bbox-derived planar anchors. Their outer surfaces aren't simple rotational surfaces (rectangular, toothed, balls-and-races), so a single `angle=` rotation around an axis doesn't have a meaningful target. Use bbox-derived faces, or attach to a raw `cylinder()` if you need angular placement.

## Manifold-clean planar joints — `fuse=True`

When two solids meet at exactly-coincident planar faces, OpenSCAD's preview shows wavering or missing surfaces — the renderer can't classify points on a coincident boundary. Pass `fuse=True` to add a tiny overlap that fixes it:

```python
pylon = Tube(od=7, id=3, h=8).attach(floor, fuse=True)
```

`fuse=True` only applies to planar contact; on a convex-outer curved host it raises and points at `bridge=True`. For the full mechanism (bonds, `disable_eps_fuse()`, known limits, the symmetric `fuse(a, b, ...)` form, and `through()` for difference-cutters), see [Eliminating manual epsilon overlap](auto-eps_fuse_and_through.md).

## Attaching to a curved surface — `bridge=True`

Bridging is the curved-host analogue of `fuse=True`, but it isn't an eps adjustment — it's a *structural* piece of material that fills the inscription gap between a peg's flat near-face and a cylinder/cone/sphere surface. Without it, a peg placed tangent to a curved host visually balances on a thin contact line.

```python
peg = cube([2, 2, 5])
hub = cylinder(h=20, r=10)
mount = peg.attach(hub, on="outer_wall", angle=30, orient=True, bridge=True)
```

Add `fuse=True` alongside for an `eps` overlap on the peg side (a manifold-clean union between the peg and the bridge):

```python
peg.attach(hub, on="outer_wall", angle=30, orient=True, bridge=True, fuse=True)
```

`bridge=True` requires a convex-outer curved on-anchor (`cylindrical`, `conical`, or `spherical`); on a planar host or concave-inner wall it raises. `bridge=True` and `bond=` don't combine — `bond=` is the planar-eps mechanism, `bridge=True` is the curved-host fill.

Full bridge mechanism (geometry, validation, the coaxial-normal requirement, behavior under `disable_eps_fuse()`, limitations) lives in [Putting things on curved surfaces: `bridge=True`](anchors.md#putting-things-on-curved-surfaces-bridge-true).

## Symmetric form — `fuse(a, b, ...)`

`attach()` only attempts local extension on `self` — `other` isn't part of the returned value, so an extension on `other` would be invisible to downstream operations. For the symmetric case where either side may carry the extension, use the free function `fuse(a, b, on=..., using_anchor=..., ...)` from `scadwright.boolops`. See the dispatch table in [auto-eps_fuse_and_through.md](auto-eps_fuse_and_through.md).

## Naming convention

The four placement kwargs that show up across the anchor-aware APIs:

| Kwarg | Type | Meaning |
|---|---|---|
| `on=` | string (anchor name) or `Anchor` | The anchor on the **other** shape — the host being attached/decorated. |
| `using_anchor=` | string (anchor name) | The anchor on **self** — the moving shape (only on `attach()` and `fuse()`). |
| `at=` | 3-tuple or string-expr (3D coordinate) | A 3D position. Used by `anchor()` declarations, `with_anchor()`, and `add_text()`'s ad-hoc placement (paired with `normal=`). Always a coordinate — never an offset. |
| `offset=` | 2-tuple (mm) | An in-face nudge for a named anchor (only on `add_text()`). 2D offset along the anchor's tangent plane. |

The split keeps `at=` consistent: it's always a 3D coordinate in some local frame. For nudging a named anchor in its tangent plane, use `offset=`.

Anchor-name kwargs (`on=`, `using_anchor=`) and position kwargs (`at=`) stay distinct: anchor names are always selectors, coordinates are always coordinates.
