# Anchors

Anchors are named attachment points on shapes. Each anchor has a **position** (where it is in space) and a **normal** (which direction the surface faces there), plus optional **surface metadata** (kind + geometric parameters) that lets `attach()` and `add_text()` compute parametric placements on curved surfaces.

This page covers the anchor data type and how to declare your own. For placing one shape against another with anchors, see [Attaching shapes](attach.md). For text on a surface, see [add_text](add_text.md).

Imports used on this page:

```python
from scadwright import Component, anchor
from scadwright.primitives import cube, cylinder
```

## The six standard faces

Every shape gets six standard anchors derived from its axis-aligned bounding box:

| Name     | Axis-sign | Normal    | Position                  |
|----------|-----------|-----------|---------------------------|
| `top`    | `+z`      | (0,0,1)   | center of top face        |
| `bottom` | `-z`      | (0,0,-1)  | center of bottom face     |
| `front`  | `-y`      | (0,-1,0)  | center of front face      |
| `back`   | `+y`      | (0,1,0)   | center of back face       |
| `lside`  | `-x`      | (-1,0,0)  | center of left face       |
| `rside`  | `+x`      | (1,0,0)   | center of right face      |

The friendly names (`top`, `bottom`, etc.) and axis-sign names (`+z`, `-z`, etc.) both work everywhere. Friendly names are preferred in code.

Bbox-derived face anchors always survive boolean operations — they're tied to the result's conservative bbox, not to specific geometry. Custom anchors (next section) follow different rules.

## Surface metadata: `kind` and `surface_params`

Every `Anchor` carries a `kind` field describing the surface it lies on. The default is `"planar"`. Other kinds are `"cylindrical"`, `"conical"`, `"spherical"`, and `"meridional"` (curved-meridian walls, e.g. `Barrel`). Curved kinds carry geometric parameters so `attach(angle=, at_z=, at_radial=, polar=)` and `add_text(angle=, at_z=, at_radial=)` can compute parametric placements on the surface.

`cylinder()` carries an `outer_wall` anchor (cylindrical when `r1 == r2`, conical when tapered). `Tube` and `Funnel` carry `outer_wall` and `inner_wall` anchors. `sphere()` carries a `surface` anchor. `Barrel` carries `outer_wall` and `inner_wall` anchors of kind `"meridional"`.

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

### Required fields by kind

| Kind          | Required surface parameters |
|---------------|-----------------------------|
| `planar`      | (none) |
| `cylindrical` | `axis`, `radius`, `length` |
| `conical`     | `axis`, `r1`, `r2`, `length` |
| `spherical`   | `axis`, `axis_origin`, `meridian_zero`, `radius` |
| `meridional`  | `axis`, `axis_origin`, `meridian_zero`, `meridian_r`, `mid_r`, `meridian_s`, `length` |

Planar cap anchors (cylinder/cone/Barrel `top` and `bottom`) are kind `"planar"` but carry `axis`, `meridian_zero`, and `rim_radius` so `attach(angle=, at_radial=)` can place on the cap and `add_text()` can wrap arc text on the rim.

### Trust contract

The framework can't verify that a Component-declared anchor lies on the actual rendered geometry of the Component's `build()` output — that would require evaluating the CSG tree. If an author declares an anchor with internally-consistent geometry that nevertheless doesn't match the rendered shape (e.g., `kind="cylindrical"` with `radius=5` on a Component that builds a `cylinder(r=10)`), the framework happily uses the declared values.

What the framework *can* check, and does at user-input boundaries (Component class-scope `anchor()`, framework-internal `Component._set_anchor()`, `Node.with_anchor()`):

| Kind | Checks |
|---|---|
| `cylindrical` | `normal` is unit and perpendicular to `axis`; `radius` and `length` positive. |
| `conical` | `normal` is unit and perpendicular to `axis`; `r1`, `r2` non-negative (not both zero); `length` positive. |
| `spherical` | `position` lies at distance `radius` from `axis_origin`; `normal` is the radial direction (or its negation for `inner=True`); `radius` positive. |
| `meridional` | Required-fields presence only — full arc-evaluation consistency isn't checked. |
| `planar` | No curved-surface checks. |

These catch the most common author errors (typos in `at=` expressions that put the anchor far off the surface; declaring `kind="cylindrical"` with a normal that doesn't point radially). They don't catch declarations that are internally consistent but lie about the rendered geometry — that's the trust boundary.

After spatial transforms (`transform_anchors`), the geometric checks are *not* re-run: a non-uniform scale on a sphere produces an internally inconsistent anchor by design (we don't model ellipsoids), and that's an accepted internal artifact, not an author error.

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

Curved-surface anchors carry their geometry in `surface_params={...}`:

```python
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

See [Surface metadata](#surface-metadata-kind-and-surface_params) for which fields each kind requires.

**Class-load validation.** Anchor `at=`, string-form `normal=`, and string values inside `surface_params={...}` are AST-checked when the Component class is defined. Every name referenced must resolve to a declared `Param` or an equation-derived symbol — typos surface at module-import time with an error naming the anchor and the offending name, instead of at downstream user instantiation. The runtime `eval` is unchanged; this just moves the check forward.

## One-off anchors on any node: `with_anchor()`

When you want a named point on a primitive (or any other Node) without writing a Component, use the chained `with_anchor()` method:

```python
peg = (
    cube([5, 5, 10])
    .with_anchor("base", at=(2.5, 2.5, 0), normal=(0, 0, -1))
)

placed = peg.attach(plate, on="top", using_anchor="base")
```

`at=` and `normal=` are 3-tuples in the wrapped node's local frame. Curved-surface kwargs (`axis`, `radius`, `r1`/`r2`, `length`, `rim_radius`, `axis_origin`, `meridian_zero`, `inner`, etc.) carry the geometry that `add_text` and the bridge dispatch need on curved kinds.

Spatial transforms applied after `with_anchor()` propagate to the anchor's position and normal exactly the same way Component custom anchors propagate. Custom anchors with the same name as a bbox-derived face override the default. Boolean operations drop them, like all custom anchors.

`with_anchor()` is the lightweight escape hatch for "I want one named point on this shape" — for a parametric family with multiple anchors, write a Component.

## Anchor propagation

Anchors (including custom ones) propagate through transforms:

```python
bracket = Bracket(w=20, thk=3, depth=15).right(20).up(10)
sensor = cube([8, 8, 4]).attach(bracket, on="mount_face")
# mount_face position is correctly shifted by both transforms
```

Boolean operations follow these rules for **custom** anchors:

- **`union` and `intersection`** drop all custom anchors. The semantic ambiguity is real — there's no clear "this anchor still means the same thing" rule when two shapes are combined.
- **`difference`** propagates custom anchors from the first child (the thing being subtracted from), with one defensive check: any custom anchor whose position falls inside a cutter's bounding box is dropped, since the cutter may have removed material at the anchor's face. The 80% case — drilling a hole through a bracket far from `mount_face` — keeps `mount_face`. The breaking case — drilling through `mount_face` itself — drops it, and the next `attach()` to that name raises a clear missing-anchor error rather than silently producing wrong-looking output.

Bbox-derived face anchors (`top`, `bottom`, etc.) always survive booleans — they're tied to the result's conservative bbox, not to specific geometry.

Non-spatial wrappers (`.color()`, `.highlight()`, etc.) pass anchors through unchanged.

## Shape-library anchors

Shape-library Components ship with useful custom anchors:

| Component      | Anchor name       | Description                     |
|----------------|-------------------|---------------------------------|
| `UShapeChannel`| `channel_opening` | Center of the open face         |
| `Standoff`     | `mount_top`       | Top of the standoff column      |
| `Bolt`         | `tip`             | Bottom of the shaft             |
| `Counterbore`  | `tip`             | Bottom of the shaft, points -z (mates to `Bolt.tip`) |

## Manifold-clean unions: `fuse=True`

When two solids meet at exactly-coincident planar faces, OpenSCAD's preview can show wavering or missing surfaces — the renderer can't classify points on a coincident boundary. The fix is a tiny overlap.

Pass `fuse=True` to `attach()` to add that overlap:

```python
pylon = cube([5, 5, 10]).attach(floor, fuse=True)
```

`attach(fuse=True)`, the standalone `fuse(a, b, ...)`, `bond="overlap"`/`"shift"`, `disable_eps_fuse()`, and `through()` are documented together in [Eliminating manual epsilon overlap](auto-eps_fuse_and_through.md). The sections below describe the planar-extension mechanism, the cross-section fallback, and the trust contract — they live here because they're consequences of how anchors are declared.

### When local extension applies

Local extension activates only when **both** anchors have `kind="planar"` AND the side being extended is a shape the framework knows how to extend parametrically. Specifically:

- `Cube` (any of the six bbox face anchors).
- `Cylinder` planar caps (`top`, `bottom`).
- `linear_extrude` end-cap anchors (`top`, `bottom`).

These rules also apply through `Translate`, `Rotate`, and `Mirror` wrappers — `Cube.up(5).rotate([0, 90, 0])` still qualifies because the framework recurses through transforms to find the underlying primitive.

When local extension applies:

- `pylon.attach(floor, fuse=True)` — pylon's bottom extends into floor by eps; pylon's top stays exactly at the user-specified `z=10`.
- `Counterbore(...).through(plate)` — the cutter's outer dimensions are preserved exactly, so `through()`'s coincidence detection on the plate's faces still works.

### Cross-section extension for non-parametric shapes

For planar anchors on shapes without a parametric extension lever — `rotate_extrude` end-caps, `Polyhedron` faces, results of `difference()` / `union()` / `intersection()`, custom Components without intrinsic extension — the framework falls back to a generic cross-section construction:

1. Aligns the anchor plane to z=0 with normal +Z.
2. Takes `projection(cut=True)` to extract the 2D cross-section.
3. `linear_extrude`s the cross-section by `eps`.
4. Inverse-aligns and unions the slab into the shape.

The result preserves the user-facing dimensions of the shape exactly — only the contact face moves by `eps`. The cost is one CGAL evaluation per fuse; for assemblies where this matters, use `disable_eps_fuse()` to opt out.

The framework validates the anchor before constructing the slab. The anchor must lie on the shape's outermost face along its normal direction (a dot-product check that works for axis-aligned and slanted normals); the bbox must have non-zero extent in at least two axes. Failures raise a clear `ValidationError`. Shape-specific overrides catch degeneracies the bbox check can't see — `Cylinder.cross_section_extend` raises on cone-apex (`r=0`) cases.

`Sphere`'s bbox-derived anchors carry `kind="spherical"`, not `kind="planar"`, so they aren't reachable by the planar cross-section path. Attaching to a sphere uses `bridge=True` instead (next section).

Documented limitations the bbox check can't catch:

- **Non-convex shapes with empty cross-sections.** A torus tangent point, two separated parts whose union bbox includes the gap, an anchor placed where a `difference()` removed all the material at that plane. Bbox check passes but the cross-section is empty; the fuse silently becomes a no-op (geometrically the same as `fuse=False`).

- **Polyhedra with degenerate end caps at the bbox extreme.** A path_extrude'd helix or other polyhedron whose top/bottom face lies exactly at the bbox max or min along the normal can cause OpenSCAD's CGAL to fail at render time with an opaque "given mesh is not closed" / "Projection() failed" error. The scadwright build succeeds but the rendered output is broken.

Workarounds for all the limitations: restructure the geometry so the fuse anchor is on a clean convex planar face, use `fuse=False` on that one attach, wrap the assembly in `disable_eps_fuse()`, or hand-craft the eps overlap.

### Curved-host attach: `bridge=True`

Bridging is a separate verb from fusing. Where `fuse=True` is the planar-contact eps mechanism (an aesthetic adjustment to keep OpenSCAD's preview clean), **`bridge=True` adds a structural piece of material** that fills the air gap between a peg's planar near-face and a convex-outer curved host (cylinder, cone, sphere). The bridge is part of the design — it's what makes the peg look (and print) merged into the curved surface, rather than balanced on a thin tangent line.

Pass `bridge=True` to `attach()` for any convex-outer curved on-anchor (`kind` in `cylindrical`, `conical`, `spherical`, `inner=False`):

```python
peg = cube([2, 2, 5])
hub = cylinder(h=20, r=10)
mount = peg.attach(hub, on="outer_wall", angle=30, orient=True, bridge=True)
# Returns union(placed_peg, bridge). Bridge fills the inscription gap
# between peg's flat near-face and the cylinder's curved surface.
```

The bridge is the peg's cross-section extruded along the contact normal by the analytical inscription depth (`R - sqrt(R² - r²)` where `R` is host radius and `r` is peg's max radial extent in the tangent plane), differenced with the host.

**Add `fuse=True` for a manifold-clean peg/bridge join.** By default `bridge=True` produces a bridge prism flush with the peg's near-face. The peg and bridge share a coincident plane there, which OpenSCAD's preview classifies the same way it would any other coincident boundary. Pass `fuse=True` alongside to extend the bridge prism by `eps` past the peg's near-face on the peg side — same machinery as planar `fuse=True`, just built into the bridge:

```python
peg.attach(hub, on="outer_wall", angle=30, orient=True,
           bridge=True, fuse=True)   # bridge + eps overlap on peg side
```

`bridge=True` and `bond=` don't combine — `bond=` controls the planar eps mechanism, `bridge=True` is the curved-host fill. Passing both raises.

**`fuse=True` alone on a curved host raises.** Bare `fuse=True` is the planar eps machinery; on a curved host it can't apply, and the validator points at `bridge=True` rather than silently doing nothing useful.

**Peg-anchor validation.** Like the planar cross-section path, the bridge dispatch validates the peg's at-anchor against the peg's bbox before building the prism: the anchor must lie on the peg's outermost face along its normal direction, and the peg must have non-zero extent in at least two axes. Failures raise a clear `ValidationError` rather than silently producing an empty bridge. The check unwraps `Translate` / `Rotate` / `Mirror` so a peg rotated by `orient=True` is validated against its underlying primitive's local frame.

**Coaxial requirement.** The bridge dispatch requires the peg's at-anchor normal to be anti-parallel to the host's on-anchor normal (within tolerance). Without `orient=True` or manual peg alignment, the call raises `ValidationError("requires coaxial normals")` rather than silently producing geometry that doesn't match user intent.

**Concave inner surfaces** (anchors with `surface_params["inner"]=True`, e.g., `Tube.inner_wall`): the peg's corners naturally inscribe into the wall material as soon as the peg is placed tangent — no bridge needed. `bridge=True` on an inner wall raises. For inner-wall attachment with eps cleanup, use `bond="shift"`.

**Under `disable_eps_fuse()`:** the bridge structural geometry persists, but the peg-side `-eps` slice (gated on `fuse=True`) drops. Precision builds get exact structural geometry.

**Inherited limitations from the cross-section primitive** (same set as the planar cross-section path):

- **Non-convex peg with empty cross-section at contact.** Bridge is empty; fuse is silently a no-op.
- **Polyhedron peg with degenerate cap.** `projection()` may fail at CGAL render with "given mesh is not closed". The scadwright build succeeds but the rendered output errors. Use `fuse=False` for that one attach (the rocket fin example does this with a manual `.left(fin_fillet)` workaround).

### When neither path applies

`fuse=True` raises when neither planar extension nor a fall-through applies — concave inner walls, non-planar contacts that aren't curved hosts, and shapes with anchors that can't be extended cleanly. The error message names the available alternatives:

- `bond="shift"` — bilateral translate of `self` by `eps` along the contact normal. The shift moves the entire shape, so the opposite face also drifts by `eps`. Coincidence-sensitive operations like `through()` should run *before* a shift, not after.
- `fuse=False` — exact contact, no eps.
- `bridge=True` — only on convex-outer curved hosts.

### `attach(fuse=True)` only extends `self`

`attach()` returns `self` translated to land on `other`. When `fuse=True`, the framework tries to locally extend `self` along the contact face. It does **not** try to extend `other` — `other` isn't part of the returned value, so an extension on `other` would be invisible to downstream operations.

For symmetric side selection — try one side, fall back to the other if the first doesn't qualify — use the standalone `fuse(a, b, on=..., using_anchor=..., eps=0.01)` function in `scadwright.boolops`. It returns the union directly, so an extension on `b` lives in the returned value where it can be used. When both sides qualify, `fuse()` picks the side whose extension produces simpler output.

### Disabling fuse in a scope: `disable_eps_fuse()`

Two cases need a way to turn fuse-mechanism eps adjustments off without rewriting individual call sites:

- **Precision builds.** Final dimensions or anchor positions need to match the source declarations exactly — no eps sneaking in anywhere.
- **Performance debugging.** Many fuses in a complex assembly add up; disabling the entire mechanism in a sub-tree lets you compare frame rates or isolate a slow path.

Wrap the affected block in `with disable_eps_fuse():`:

```python
from scadwright import disable_eps_fuse

@variant
def precise(self):
    with disable_eps_fuse():
        return self.assembly()    # all fuse=True calls become exact contacts

@variant
def normal(self):
    return self.assembly()        # all fuse=True calls get eps overlap as usual
```

Inside the block, `attach(fuse=True)` and the standalone `fuse(...)` behave as if `fuse` were `False`: exact anchor coincidence, no parametric extension, no shift. Anchor lookup, placement, `orient=True`, `angle=`, `at_z=`, `at_radial=`, and `through()` composition all continue to work — only the eps geometry is suppressed.

The flag is scope-bounded; nested blocks are no-ops, and exiting any block restores the prior state.
