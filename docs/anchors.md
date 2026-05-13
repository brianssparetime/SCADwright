# Anchors

Anchors are named spots on a shape that you can attach other things to. Every shape gets six of them by default, one per face. Components can name more.

This page is about the anchors you get for free, how to declare your own, and what happens to anchors when you transform or combine shapes. For placing one shape against another, see [Attaching shapes](attach.md). For putting text on a surface, see [add_text](add_text.md).

Imports used on this page:

```python
from scadwright import Component, anchor
from scadwright.primitives import cube, cylinder
```

## The six standard faces

Every shape gets six standard anchors, one per face of its bounding box:

| Name     | Axis-sign | Normal    | Position                  |
|----------|-----------|-----------|---------------------------|
| `top`    | `+z`      | (0,0,1)   | center of top face        |
| `bottom` | `-z`      | (0,0,-1)  | center of bottom face     |
| `front`  | `-y`      | (0,-1,0)  | center of front face      |
| `back`   | `+y`      | (0,1,0)   | center of back face       |
| `lside`  | `-x`      | (-1,0,0)  | center of left face       |
| `rside`  | `+x`      | (1,0,0)   | center of right face      |

Both naming styles work everywhere. Friendly names like `top` read better in code.

These six always survive boolean operations like `union()` and `difference()`. Custom anchors follow different rules; see [How transforms and booleans affect anchors](#how-transforms-and-booleans-affect-anchors).

## Custom anchors on Components

Declare anchors inside your Component using `anchor()`:

```python
from scadwright import Component, anchor

class Bracket(Component):
    equations = "w, thk, depth > 0"

    mount_face = anchor(at="w/2, w/2, thk", normal=(0, 0, 1))

    def build(self):
        return cube([self.w, self.w, self.depth])
```

`at=` is the position. Use a tuple `(x, y, z)` for a fixed point, or a string with three comma-separated expressions if the position should depend on the Component's parameters:

```python
fixed_point = anchor(at=(0, 0, 10), normal=(0, 0, 1))       # literal position
mount_face  = anchor(at="w/2, w/2, thk", normal=(0, 0, 1))  # uses w and thk
```

The attribute name (`mount_face`) becomes the anchor's name when callers attach to it:

```python
sensor = cube([8, 8, 4]).attach(Bracket(w=20, thk=3, depth=15), on="mount_face")
```

If you give an anchor the same name as a standard face (like `"top"`), it replaces the default. Use this when your part has a semantically meaningful "top" that isn't the bounding-box top.

A Python `if`/`else` expression works inside `at=`, so conditional positions don't need anything special:

```python
anchor(at="0 if n_shape else h", normal=(0, 0, 1))
```

Typos in anchor expressions are caught early: if you misspell a parameter name in `at=`, you get a clear error at script-start, naming the bad anchor and the unknown name, instead of a confusing error later when someone uses the Component.

## Naming a point on a single shape: `with_anchor()`

If you want a named point on one specific shape without writing a Component, chain `with_anchor()`:

```python
peg = (
    cube([5, 5, 10])
    .with_anchor("base", at=(2.5, 2.5, 0), normal=(0, 0, -1))
)

placed = peg.attach(plate, on="top", using_anchor="base")
```

`at=` and `normal=` are 3-tuples in the shape's local space. The anchor moves with any transforms you apply afterward, the same way Component custom anchors do.

Use `with_anchor()` when you only need one named point on one shape. If you're building a parametric family of parts with several anchors, write a Component instead.

## Library shapes with extra anchors

These shape-library Components come with named anchors beyond the six standard faces:

| Component      | Anchor name       | Description                     |
|----------------|-------------------|---------------------------------|
| `UShapeChannel`| `channel_opening` | Center of the open face         |
| `Standoff`     | `mount_top`       | Top of the standoff column      |
| `Bolt`         | `tip`             | Bottom of the shaft             |
| `Counterbore`  | `tip`             | Bottom of the shaft, points -z (mates to `Bolt.tip`) |

Cylinders, cones, spheres, and rims also carry richer anchors that let you place things at a specific angle around an axis (like `angle=30`), at a specific axial position, or at a specific point on a sphere. See [Attaching shapes](attach.md#placement-on-cylinders-cones-and-spheres) for which options work where, and the list of library shapes that have these anchors.

## How transforms and booleans affect anchors

Transforms (translate, rotate, scale, mirror) carry anchors along, so you can attach to a shape after moving it:

```python
bracket = Bracket(w=20, thk=3, depth=15).right(20).up(10)
sensor = cube([8, 8, 4]).attach(bracket, on="mount_face")
# mount_face's position is correctly shifted by both .right() and .up().
```

Boolean operations are more selective. The six standard face anchors always survive (they're recomputed from the result's bounding box). Custom anchors follow these rules:

- **`union` and `intersection`** drop all custom anchors. When two shapes are combined, there's no clean rule for which custom anchors should still apply, so SCADwright drops them all.
- **`difference`** keeps custom anchors from the first shape (the one being cut into), with one safety check: if a cutter's bounding box covers the anchor's position, that anchor is dropped. The common case (drilling far from `mount_face`) keeps the anchor. The breaking case (drilling through `mount_face` itself) drops it, and the next `attach()` to that name gives you a clear error instead of silently producing wrong-looking output.

Effects like `.color()` and `.highlight()` don't move the shape, so anchors pass through unchanged.

## Clean unions with `fuse=True`

When two parts share a flat face, OpenSCAD's preview shows a seam where the surfaces meet. Pass `fuse=True` to `attach()` to add a tiny overlap that fixes it:

```python
pylon = cube([5, 5, 10]).attach(floor, fuse=True)
```

For the full set of related options (`bond=`, `disable_eps_fuse()`, the standalone `fuse(a, b)`, and `through()` for cutters), see [Eliminating manual epsilon overlap](auto-eps_fuse_and_through.md).

## Putting things on curved surfaces: `bridge=True`

Attaching a flat-bottomed peg to a cylinder, cone, or sphere with the usual `attach()` leaves a visible gap where the peg touches the curved surface; the peg looks balanced on a thin contact line. Pass `bridge=True` to fill that gap with a small piece of material so the peg looks merged into the host:

```python
peg = cube([2, 2, 5])
hub = cylinder(h=20, r=10)
mount = peg.attach(hub, on="outer_wall", angle=30, orient=True, bridge=True)
```

The bridge is part of the final design, not a rendering tweak. It fills the empty space between the peg's flat side and the curved surface so the part both looks and prints as one piece.

By default the bridge sits flush against the peg, which means the peg-and-bridge boundary is a coincident plane. If you want that union to render without a seam too, add `fuse=True`:

```python
peg.attach(hub, on="outer_wall", angle=30, orient=True, bridge=True, fuse=True)
```

`bridge=True` only works on the outside of a curved host. On a tube's inner wall, the peg's corners already sink into the wall material, so there's no gap to fill. For a clean union on an inner wall, pass `bond="shift"` instead.

See [Advanced notes](#advanced-notes) for how the bridge is built, what it checks before building, and the limitations to watch for.

## Advanced notes

The sections below are for corner cases. Most users won't need them.

### Curved anchors carry surface details

When an anchor sits on a curved surface, SCADwright stores extra information about the surface so `attach()` and `add_text()` can place things at a specific angle, axial position, or point on the surface. The supported `kind` values:

| `kind`         | Surface                                       | Where it appears                              |
|----------------|-----------------------------------------------|-----------------------------------------------|
| `"planar"`     | A flat face                                   | Default for all shapes                        |
| `"cylindrical"`| A straight wall around an axis                | `outer_wall` of a cylinder or `Tube`          |
| `"conical"`    | A tapered wall around an axis                 | `outer_wall` of a `Funnel` or tapered cylinder|
| `"spherical"`  | A round surface around a center point         | `surface` of a sphere                         |
| `"meridional"` | A curved-meridian wall (bulged or waisted)    | `outer_wall` and `inner_wall` of `Barrel`     |

Each kind needs certain extra fields to work. Most users won't write these by hand; library shapes set them up for you. If you do declare a curved anchor on your own Component, here's what each kind needs:

| Kind          | Required surface parameters |
|---------------|-----------------------------|
| `planar`      | (none) |
| `cylindrical` | `axis`, `radius`, `length` |
| `conical`     | `axis`, `r1`, `r2`, `length` |
| `spherical`   | `axis`, `axis_origin`, `meridian_zero`, `radius` |
| `meridional`  | `axis`, `axis_origin`, `meridian_zero`, `meridian_r`, `mid_r`, `meridian_s`, `length` |

Cap anchors on cylinders, cones, and barrels (`top`/`bottom`) are `kind="planar"` but also carry `axis`, `meridian_zero`, and `rim_radius`, so you can place things on the cap by angle and radius.

Pass these in `surface_params` when declaring the anchor:

```python
outer_wall = anchor(
    at="od/2, 0, h/2",
    normal=(1, 0, 0),
    kind="cylindrical",
    surface_params={"axis": (0, 0, 1), "radius": "od/2", "length": "h"},
)
```

String values inside `surface_params` are evaluated against the Component's parameters the same way `at=` strings are.

### What SCADwright checks when you declare an anchor

When you call `anchor()` or `with_anchor()` with a curved `kind`, SCADwright checks a few things to catch common typos:

| Kind          | Checks |
|---------------|--------|
| `cylindrical` | `normal` is a unit vector perpendicular to `axis`; `radius` and `length` are positive. |
| `conical`     | `normal` is a unit vector perpendicular to `axis`; `r1`, `r2` are non-negative (not both zero); `length` is positive. |
| `spherical`   | `position` lies at distance `radius` from `axis_origin`; `normal` is the radial direction (negated for `inner=True`); `radius` is positive. |
| `meridional`  | The required fields are present (the full arc geometry isn't double-checked). |
| `planar`      | (no curved-surface checks) |

What SCADwright can't check: whether the anchor you declared actually lines up with the geometry your `build()` produces. If you declare `kind="cylindrical"` with `radius=5` on a Component that actually builds `cylinder(r=10)`, SCADwright uses your declared values and the bridge ends up in the wrong place.

After a transform like `scale()`, the geometric checks aren't re-run. A non-uniform scale on a sphere produces an inconsistent anchor on purpose, since SCADwright doesn't model ellipsoids.

### How `bridge=True` builds the fill

`bridge=True` does these steps internally:

1. Takes the peg's cross-section in the plane facing the host.
2. Extrudes it along the contact normal by an inscription depth of `R - sqrt(R² - r²)`, where `R` is the host's radius at the contact point and `r` is the peg's largest extent in the tangent plane.
3. Subtracts the host from that prism, leaving exactly the gap-filling shape between peg and host.
4. Unions the result with the placed peg.

Before building, SCADwright checks that the peg's at-anchor lies on the peg's outermost face along its normal direction, and that the peg has non-zero extent in at least two axes. Otherwise the bridge would be empty or wrong-shaped, so you get a clear error instead.

`bridge=True` also requires that the peg's at-anchor normal points opposite the host's on-anchor normal. With `orient=True`, that's handled for you. Without it, if your peg isn't already aligned, you get a `"requires coaxial normals"` error rather than a wrong-looking part.

`bridge=True` and `bond=` can't combine. `bond=` is for the planar overlap mechanism; `bridge=True` is the curved-host fill. Passing both gives you an error.

### Bridge limitations

These cases either fail silently or fail at render time:

- **Non-convex pegs with an empty cross-section at the contact face.** A torus tangent point, two separated parts, or a peg with a `difference()` hole at the contact plane all fall in this bucket. The bridge ends up empty, and `bridge=True` becomes a no-op (same as if you'd passed `fuse=False`).
- **Polyhedron pegs with a degenerate cap exactly at the contact face.** OpenSCAD's CGAL renderer may fail with `"given mesh is not closed"` / `"Projection() failed"`. The build succeeds; rendering doesn't. Pass `fuse=False` on that one call as a workaround. The rocket fin in `examples/rocket.py` shows the pattern (it adds a manual `.left(fin_fillet)` to dodge the issue).

Both limitations also apply to the planar `fuse=True` cross-section path; see [Eliminating manual epsilon overlap](auto-eps_fuse_and_through.md#known-limits-and-recovery-paths) for the full list of cases where auto-eps can silently fail.

### `bridge=True` under `disable_eps_fuse()`

Inside a `with disable_eps_fuse():` block, the bridge geometry itself stays put: it's part of the design, not a rendering tweak. The small `-eps` peg-side slice that `fuse=True` adds (only when you pass both `bridge=True` and `fuse=True`) does drop. So a precision build wrapped in `disable_eps_fuse()` still gets accurate structural bridges.
