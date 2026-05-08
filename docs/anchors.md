# Anchors and attachment

Anchors are named attachment points on shapes. Each anchor has a position (where it is in space) and a normal (which direction it faces). The `attach()` method uses anchors to position one shape relative to another without manual coordinate math.

Imports used on this page:

```python
from scadwright import Component, anchor
from scadwright.primitives import cube, cylinder
```

## Basic usage

Every shape gets six standard anchors derived from its bounding box:

| Name     | Axis-sign | Normal    | Position                  |
|----------|-----------|-----------|---------------------------|
| `top`    | `+z`      | (0,0,1)   | center of top face        |
| `bottom` | `-z`      | (0,0,-1)  | center of bottom face     |
| `front`  | `-y`      | (0,-1,0)  | center of front face      |
| `back`   | `+y`      | (0,1,0)   | center of back face       |
| `lside`  | `-x`      | (-1,0,0)  | center of left face       |
| `rside`  | `+x`      | (1,0,0)   | center of right face      |

The friendly names (`top`, `bottom`, etc.) and axis-sign names (`+z`, `-z`, etc.) both work everywhere. Friendly names are preferred in code.

Stack a peg on top of a plate:

```python
plate = cube([40, 40, 2])
peg   = cube([10, 10, 5]).attach(plate)    # bottom of peg on top of plate
```

`attach()` defaults to `on="top"` (the anchor on the other shape) and `at="bottom"` (the anchor on self), so `peg.attach(plate)` means "put my bottom on your top."

## Choosing faces

Use `on` and `at` to pick which anchors to align:

```python
peg.attach(plate, on="bottom", at="top")       # peg underneath plate
peg.attach(plate, on="rside", at="lside")      # peg to the right of plate
peg.attach(plate, on="top", at="top")           # align top faces (peg hangs down)
```

`on` names the anchor on the parent (the thing being attached to); `at` names the anchor on self (the thing being moved). The same `on` convention is used by other surface-aware verbs like `add_text()`. `at` is context-sensitive — see [`at=` across the API](#at-across-the-api) below.

Chain a translate for offset placement:

```python
peg.attach(plate).right(10)           # on top, shifted 10 in +X
```

## Orientation (`orient=True`)

By default, `attach()` only translates. Pass `orient=True` to also rotate self so the two anchors' normals oppose each other (faces touching):

```python
peg.attach(plate, on="rside", at="bottom", orient=True)
```

This rotates the peg so its bottom normal faces in the -X direction (opposing the plate's rside +X normal), then translates it into position.

When the normals already oppose (e.g. attaching bottom-to-top), `orient=True` produces the same result as `orient=False`.

## Manifold-clean unions: `fuse=True`

When two solids meet at exactly-coincident planar faces, OpenSCAD's preview can show wavering or missing surfaces — the renderer can't classify points on a coincident boundary. The fix is a tiny overlap.

Pass `fuse=True` to `attach()` to add that overlap:

```python
pylon = cube([5, 5, 10]).attach(floor, fuse=True)
```

### When local extension applies

Local extension activates only when **both** anchors have `kind="planar"` AND the side being extended is a shape the framework knows how to extend parametrically. Specifically:

- `Cube` (any of the six bbox face anchors).
- `Cylinder` planar caps (`top`, `bottom`).
- `linear_extrude` end-cap anchors (`top`, `bottom`).

These rules also apply through `Translate`, `Rotate`, and `Mirror` wrappers — `Cube.up(5).rotate([0, 90, 0])` still qualifies because the framework recurses through transforms to find the underlying primitive.

When local extension applies:

- `pylon.attach(floor, fuse=True)` — pylon's bottom extends into floor by eps; pylon's top stays exactly at the user-specified `z=10`.
- `Counterbore(...).through(plate)` — the cutter's outer dimensions are preserved exactly, so `through()`'s coincidence detection on the plate's faces still works.

### When local extension doesn't apply

`fuse=True` falls back to translating `self` by `eps` along the contact normal — the legacy bilateral shift. This affects:

- Non-planar interfaces. Either side has `kind="cylindrical"`, `"conical"`, or any non-`"planar"` anchor (e.g., a peg attached tangentially to a cylinder's `outer_wall`).
- Shapes without intrinsic extension support — raw `Polyhedron`, custom Components without parametric extension lookups, results of `difference()` / `intersection()` / `hull()`.

The shift moves the entire shape, so the opposite face also drifts by `eps`. Coincidence-sensitive operations like `through()` should run *before* a shift-based fuse, not after.

### `attach(fuse=True)` only extends `self`

`attach()` returns `self` translated to land on `other`. When `fuse=True`, the framework tries to locally extend `self` along the contact face. It does **not** try to extend `other` — `other` isn't part of the returned value, so an extension on `other` would be invisible to downstream operations.

For symmetric side selection — try one side, fall back to the other if the first doesn't qualify — use the standalone `fuse(a, b, on=..., at=..., eps=0.01)` function in `scadwright.boolops`. It returns the union directly, so an extension on `b` lives in the returned value where it can be used. When both sides qualify, `fuse()` picks the side whose extension produces simpler output.

## Angular placement on cylindrical surfaces

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

# On the cap interior to the rim — pass radius=:
peg.attach(hub, on="top", angle=0, radius=5)            # 5 mm from cap center
peg.attach(hub, on="top", angle=0, radius=0)            # exact cap center
```

`angle=` works on three anchor surface kinds:

- **Cylindrical wall** (`outer_wall` of a cylinder): `angle=` rotates the anchor's position and normal around the surface axis. The result puts self at that angular position on the wall, normal pointing radially outward.
- **Conical wall** (`outer_wall` of a cone, where `r1 != r2`): same rotation, but the normal used for `orient=True` is the cone's *slanted* surface normal — so `peg.attach(cone, on="outer_wall", angle=0, orient=True)` aligns the peg perpendicular to the slanted wall, not the cone's central axis.
- **Cap with rim radius** (`top` / `bottom` of a cylinder or cone): `angle=` places at angular position on the cap. Default radial position is the cap's rim radius; `radius=` overrides for placements interior to the rim.

For other anchor kinds (a cube's `top`, a custom Component anchor without surface metadata), `angle=` raises a clear error.

### Axial placement: `at_z=`

For attachments along a cylindrical or conical wall — "30° meridian, 5 mm above mid-wall" — pass `at_z=` (mm offset from the anchor's reference axial position):

```python
peg.attach(hub, on="outer_wall", at_z=5)              # +X meridian, 5 mm above mid-wall
peg.attach(hub, on="outer_wall", angle=30, at_z=5)    # 30° meridian, 5 mm above mid-wall
```

`at_z=` shifts along the cylinder's actual axis line, so it tracks correctly when the host has been translated or rotated. Compare with chaining `.up(5)` after `attach`, which translates in world space and only matches the cylinder's axis when that axis happens to be world +Z.

On a conical wall, `at_z=` also adjusts the position radially so the new anchor stays on the slanted surface. An `at_z=` that drives the local cone radius non-positive (past the cone tip) raises a clear error rather than silently producing junk geometry.

`at_z=` is only valid on cylindrical and conical wall anchors. On a rim, the in-plane radial offset is `radius=` instead. On a cube face or other anchor without a surface axis, `at_z=` raises.

### Hosts that publish cylindrical / conical / rim anchors

- `cylinder()` (the primitive) — `outer_wall`, plus rim metadata on `top` and `bottom`.
- `Tube` — `outer_wall`, `inner_wall`, plus rim metadata on `top` and `bottom`.
- `Funnel` — `outer_wall` and `inner_wall` (conical), plus rim metadata on `top` and `bottom`.

Other shapes — `cube()`, `RectTube`, `RingGear`, `Bearing`, `RoundedBox`, etc. — only carry the six bbox-derived planar anchors. Their outer surfaces aren't simple cylinders (rectangular, toothed, balls-and-races), so a single `angle=` rotation around an axis doesn't have a meaningful target. Use bbox-derived faces, or attach to a raw `cylinder()` if you need angular placement.

## Custom anchors on Components

Declare anchors at class scope with the `anchor()` descriptor, alongside equations:

```python
from scadwright import Component, anchor

class Bracket(Component):
    equations = "w, thk, depth > 0"

    mount_face = anchor(at="w/2, w/2, thk", normal=(0, 0, 1))

    def build(self):
        return cube([self.w, self.w, self.depth])
```

The `at=` argument accepts either a string of three comma-separated Python expressions (evaluated against the instance's attributes after params are set) or a literal tuple:

```python
fixed_point = anchor(at=(0, 0, 10), normal=(0, 0, 1))       # literal position
mount_face  = anchor(at="w/2, w/2, thk", normal=(0, 0, 1))  # expression
```

The attribute name (`mount_face`) becomes the anchor's name. Callers attach to it by that name:

```python
sensor = cube([8, 8, 4]).attach(Bracket(w=20, thk=3, depth=15), on="mount_face")
```

Custom anchors with the same name as a standard face (e.g. `"top"`) override the bbox-derived default. This lets a Component define a semantically meaningful "top" that differs from its bounding box top.

The `at=` string supports ternary expressions evaluated against instance attributes, so conditional positions don't need any special machinery: `anchor(at="0 if n_shape else h", normal=(0, 0, 1))`. Conditional **normals** are the narrow remaining case — `normal=` is a fixed tuple at class definition time, so a runtime-chosen normal is a framework-internal escape hatch (library Components only; not a user-facing pattern).

## Anchor propagation

Anchors (including custom ones) propagate through transforms:

```python
bracket = Bracket(w=20, thk=3, depth=15).right(20).up(10)
sensor = cube([8, 8, 4]).attach(bracket, on="mount_face")
# mount_face position is correctly shifted by both transforms
```

Boolean operations (union, difference, intersection) drop custom anchors. Only the standard bbox-derived faces survive, because a boolean combination creates new geometry whose custom attachment points are no longer meaningful.

Non-spatial wrappers (`.color()`, `.highlight()`, etc.) pass anchors through unchanged.

## Surface metadata: `kind` and `surface_params`

Every `Anchor` carries a `kind` field describing the surface it lies on. The default is `"planar"`. Curved-surface kinds — `"cylindrical"` and `"conical"` — also carry the geometric parameters of the surface (`radius` or `r1`/`r2`, `axis`, `length`) so [`add_text()`](add_text.md) can wrap text around them.

`cylinder()` carries an `outer_wall` anchor (cylindrical when `r1 == r2`, conical when tapered). `Tube` and `Funnel` carry `outer_wall` and `inner_wall` anchors.

```python
from scadwright.primitives import cylinder
from scadwright.anchor import get_node_anchors

a = get_node_anchors(cylinder(h=20, r=5))["outer_wall"]
a.kind                     # "cylindrical"
a.surface_param("radius")  # 5.0
a.surface_param("axis")    # (0.0, 0.0, 1.0)
a.surface_param("length")  # 20.0
```

Surface params transform alongside `position` and `normal`: rotating the host rotates the axis, scaling scales the radius and length. `cylinder(h=20, r=5).rotate([90, 0, 0])` reports `axis=(0, -1, 0)` for its outer wall, and `add_text(on="outer_wall", ...)` wraps correctly around the rotated cylinder.

```python
from scadwright import anchor

# Planar (the default — surface_params is omitted).
mount = anchor(at="w/2, w/2, thk", normal=(0, 0, 1))

# Cylindrical anchor on a Component. surface_params values can be
# Python expressions (strings) evaluated against instance attributes —
# same as `at=` strings.
outer_wall = anchor(
    at="od/2, 0, h/2",
    normal=(1, 0, 0),
    kind="cylindrical",
    surface_params={"axis": (0, 0, 1), "radius": "od/2", "length": "h"},
)
```

Use `Anchor.surface_param(name, default)` to read back a value.

## Shape-library anchors

Shape-library Components ship with useful custom anchors:

| Component      | Anchor name       | Description                     |
|----------------|-------------------|---------------------------------|
| `UShapeChannel`| `channel_opening` | Center of the open face         |
| `Standoff`     | `mount_top`       | Top of the standoff column      |
| `Bolt`         | `tip`             | Bottom of the shaft             |
| `Counterbore`  | `tip`             | Bottom of the shaft, points -z (mates to `Bolt.tip`) |

## `at=` across the API

`at=` answers "where on the placed/moved thing?" Its form varies with the call:

| Call | `at=` form | Meaning |
|---|---|---|
| `attach(other, on=..., at=...)` | string | anchor name on self (the thing being moved) |
| `add_text(on=..., at=(u, v))` | 2-tuple in mm | offset in the chosen face's tangent plane |
| `add_text(at=(x, y, z), normal=...)` | 3-tuple in mm | ad-hoc 3D position (no `on=`) |
| `anchor(at=..., normal=...)` (declaration) | 3-tuple or string-expr | the anchor's position |

The asymmetry is deliberate: `attach` moves an existing shape (which has its own anchors), so `at=` selects one. `add_text` stamps a generated 2D feature onto a host (no self-anchors), so `at=` is the placement offset within the chosen face. Anchor *declarations* use `at=` for the anchor's position itself.
