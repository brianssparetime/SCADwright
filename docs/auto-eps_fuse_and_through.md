# Eliminating manual epsilon overlap

OpenSCAD requires a small overlap (epsilon) whenever two shapes share a face in a boolean operation. Without it, F5 preview shows wavering, missing, or flickering surfaces — the GL renderer can't classify points on a coincident boundary. SCADwright handles this automatically so you don't have to define `eps` constants and manually adjust cutter sizes.

`fuse=` is the eps mechanism for **planar** contacts. For convex-outer curved hosts (cylinder, cone, sphere), use `bridge=True` instead — that's a separate, structural verb covered in [anchors.md](anchors.md#curved-host-attach-bridge-true).

## Quick reference

| Need | Use |
|---|---|
| Position a part flush against another planar face, with overlap so `union()` is preview-clean | `part.attach(other, fuse=True)` |
| Same, but pick the bond explicitly | `part.attach(other, bond="overlap" | "shift")` |
| Drill a cutter through a parent shape | `cutter.through(parent)` inside `difference()` |
| Combine two parts symmetrically with overlap (no "self" / "other" asymmetry) | `fuse(a, b, on=..., using_anchor=..., bond=..., eps=...)` from `scadwright.boolops` |
| Disable all auto-eps inside a scope (precision builds, perf debugging) | `with disable_eps_fuse(): ...` |
| Override the default `eps` value across a scope (precision / unit-conversion / tight-tolerance models) | `with tolerances(eps=0.001): ...` |
| Override `through()`'s coincident-face matching tolerance | `with tolerances(coincidence=1e-5): ...` |

## `attach(fuse=True)` — joints in `union()`

When two parts sit flush against each other (e.g. a pylon on a floor), `fuse=True` on `attach()` adds a small overlap (default 0.01 mm, override with `eps=`) at the contact face, eliminating the coincident-surface seam:

```python
from scadwright.boolops import union
from scadwright.primitives import cube
from scadwright.shapes import Tube

floor = cube([40, 40, 2])
pylon = Tube(od=7, id=3, h=8).attach(floor, fuse=True)
part = union(floor, pylon)
```

The overlap is added in one of two ways, depending on whether the framework can extend the contact face parametrically. Either way, the user-facing dimensions of the extended side stay exact — only the contact face moves by `eps`.

### Tier 1: parametric extension

Local extension activates only when **both** anchors have `kind="planar"` AND the side being extended is a shape the framework knows how to extend parametrically:

- `Cube` (any of the six bbox face anchors).
- `Cylinder` planar caps (`top`, `bottom`).
- `linear_extrude` end-cap anchors (`top`, `bottom`).

These rules also apply through `Translate`, `Rotate`, and `Mirror` wrappers — `cube(...).up(5).rotate([0, 90, 0])` still qualifies because the framework recurses through transforms to find the underlying primitive.

When Tier 1 applies:

- `pylon.attach(floor, fuse=True)` — pylon's bottom extends into floor by eps; pylon's top stays exactly at the user-specified `z=10`.
- `Counterbore(...).through(plate)` — the cutter's outer dimensions are preserved exactly, so `through()`'s coincidence detection on the plate's faces still works.

### Tier 2: cross-section fallback

For planar anchors on shapes without a parametric extension lever — `rotate_extrude` end-caps, `Polyhedron` faces, results of `difference()` / `union()` / `intersection()`, custom Components without intrinsic extension — the framework falls back to a generic cross-section construction:

1. Aligns the anchor plane to z=0 with normal +Z.
2. Takes `projection(cut=True)` to extract the 2D cross-section.
3. `linear_extrude`s the cross-section by `eps`.
4. Inverse-aligns and unions the slab into the shape.

The result preserves the user-facing dimensions of the shape exactly — only the contact face moves by `eps`. The cost is one CGAL evaluation per fuse; for assemblies where this matters, use `disable_eps_fuse()` to opt out.

The framework validates the anchor before constructing the slab. The anchor must lie on the shape's outermost face along its normal direction (a dot-product check that works for axis-aligned and slanted normals); the bbox must have non-zero extent in at least two axes. Failures raise a clear `ValidationError`. Shape-specific overrides catch degeneracies the bbox check can't see — `Cylinder.cross_section_extend` raises on cone-apex (`r=0`) cases.

`Sphere`'s bbox-derived anchors carry `kind="spherical"`, not `kind="planar"`, so they aren't reachable by this path. Attach to a sphere with [`bridge=True`](anchors.md#curved-host-attach-bridge-true).

### When neither tier applies

`fuse=True` raises when the contact isn't planar-planar and the cascade can't fall through — concave inner walls, non-planar contacts that aren't convex-outer curved hosts, shapes with anchors that can't be extended cleanly. The error message names the available alternatives:

- `bond="shift"` — bilateral translate of `self` by `eps` along the contact normal. The shift moves the entire shape, so the opposite face also drifts by `eps`. Coincidence-sensitive operations like `through()` should run *before* a shift, not after.
- `fuse=False` — exact contact, no eps.
- `bridge=True` — only on convex-outer curved hosts.

### `bond=` for explicit control

`fuse=True` runs the Tier-1 / Tier-2 cascade and picks `bond="overlap"` when it applies. Pass `bond=` directly when you want explicit control:

| `bond=` | What it does | When it raises |
|---|---|---|
| `"overlap"` | Local face extension at a planar contact (parametric `fuse_extend` first, cross-section fallback). Preserves the user-facing dimensions of the extended side. | Either anchor isn't planar; cross-section is degenerate. |
| `"shift"` | Bilateral translate of the moving shape by `eps` along the contact normal. The opposite face drifts by `eps`. | Never raises on geometry — always works. |

```python
peg.attach(plate, bond="overlap")              # explicit planar extension
peg.attach(plate, bond="shift")                # explicit bilateral shift
```

`bond="..."` implies `fuse=True`; passing `fuse=False` with a bond raises (contradiction). `bond=` and `bridge=True` don't combine — `bond=` is for planar contacts, `bridge=True` is for curved hosts. `fuse=True` without a bond on a planar host falls into `bond="overlap"`; on a curved host it raises and points at `bridge=True`. The cascade does not silently fall through to `shift` — the user who actually wants the bilateral shift writes `bond="shift"` explicitly. The standalone `fuse(a, b, ..., bond=...)` accepts the same vocabulary.

### `attach()` only extends `self` — use `fuse(a, b, ...)` for symmetric cases

`attach()` returns `self` translated to land on `other`. When `fuse=True`, the framework tries to locally extend `self` along the contact face. It does **not** try to extend `other` — `other` isn't part of the returned value, so an extension on `other` would be invisible to downstream operations.

For symmetric side selection — try one side, fall back to the other if the first doesn't qualify — use the standalone `fuse(a, b, on=..., using_anchor=..., eps=0.01)` function in `scadwright.boolops`. It returns the union directly, so an extension on `b` lives in the returned value where it can be used. When both sides qualify, `fuse()` picks the side whose extension produces simpler output.

## `through(parent)` — cutters in `difference()`

Extends a cutter through any face of `parent` that it touches, adding a small overlap so `difference()` produces a clean cut:

```python
from scadwright.boolops import difference
from scadwright.primitives import cube, cylinder

box = cube([20, 20, 10])
part = difference(box, cylinder(h=10, r=3).through(box))
```

The cylinder's top and bottom are both flush with the box, so `through()` extends both ends by 0.01 (the default epsilon). No manual `EPS` constant needed.

### How it works

`through()` computes bounding boxes of the cutter and parent, detects which faces are coincident (within floating-point tolerance), and extends only those faces. Faces that aren't coincident are left alone:

```python
# Through-hole: both ends flush -> both extended
cylinder(h=10, r=3).through(box)

# Counterbore: only top is flush -> only top extended
cylinder(h=5, r=6).up(5).through(box)

# Blind pocket: neither end flush -> no change (harmless to call)
cylinder(h=4, r=3).up(3).through(box)
```

### Cut axis

`through()` auto-detects the cut axis by finding which axis has coincident faces. For ambiguous cases (e.g. a cube-shaped cutter), specify explicitly:

```python
cube([20, 20, 3]).up(3).through(box, axis="z")
```

### Custom epsilon

Default is 0.01. Override with `eps=`:

```python
cylinder(h=10, r=3).through(box, eps=0.1)
```

### Call order

Call `through()` after positioning the cutter. It needs to see the final position to detect coincident faces:

```python
cylinder(h=10, r=3).up(5).right(8).through(box)   # position first, then through
```

### Rotated cutters

For angled drill holes, chamfered countersinks on non-vertical faces, draft-angled inserts, and other rotated-cutter patterns, the world-axis path can't detect coincidence (the cutter's world AABB is inflated by the rotation). Pass `axis="local"` (or `"local_x"` / `"local_y"` / `"local_z"`) to evaluate coincidence in the cutter's local frame:

```python
import math

# 30°-tilted cylindrical drill, sized to span a 2 mm plate exactly:
plate = cube([20, 20, 2])
h = 2 / math.cos(math.radians(30))
drill = (
    cylinder(h=h, r=2)
    .rotate([0, 30, 0])
    .translate([10, 5, 0])
)
part = difference(plate, drill.through(plate, axis="local_z"))
```

`axis="local"` is a synonym for `axis="local_z"` (the cylinder convention). For non-cylindrical cutters, specify the local axis explicitly: `local_x`, `local_y`, or `local_z`.

How it works: `through()` walks the cutter's outer rotations and translations to find the cumulative local-to-world transform, projects the cutter's end-face centers (at the cutter's local origin on the cut axis) into world space, and checks them against the parent's AABB face planes. The extension applies as a `Translate(Scale(...))` inserted at the leaf level, so the SCAD output keeps the original `rotate(...)` calls plus a leaf-level `translate + scale` rather than collapsing into an opaque `multmatrix`.

With `axis=None` and a rotated cutter that has no world-axis coincidence, `through()` raises pointing at the local-axis form rather than silently no-opping. Cutters whose rotation happens to be axis-permuting (90° around a single axis — `rotate([0, 90, 0])`) keep an axis-aligned world bbox, so the world-axis path handles them and no error is raised.

Anisotropic Scale, Mirror, or other non-rotation transforms in the cutter's stack raise — the local-axis path requires a pure rotation. Apply scale to the underlying primitive's parameters instead.

## Scope controls

### `disable_eps_fuse()`

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

Inside the block, `attach(fuse=True)` and the standalone `fuse(...)` behave as if `fuse` were `False`: exact anchor coincidence, no parametric extension, no shift. `bond=` is dropped. The peg-side `-eps` slice baked into a `bridge=True` result drops too — but **the bridge structural geometry itself persists**, because it's design geometry, not eps. Anchor lookup, placement, `orient=True`, `angle=`, `at_z=`, `at_radial=`, and `through()` composition all continue to work — only the eps geometry is suppressed.

The flag is scope-bounded; nested blocks compose, and exiting any block restores the prior state.

## Known limits and recovery paths

Auto-eps works for the common cases. There are three patterns where it can silently fail to fix the preview artifact:

1. **Non-convex peg or host with empty cross-section at the contact face.** A torus tangent point, two separated parts whose union bbox includes the gap, an anchor placed where a `difference()` removed all the material at that plane. The framework's bbox-projection check passes, but the actual cross-section is empty — only OpenSCAD's CGAL evaluator can detect this, and we don't pay that cost at build time. The fuse becomes a no-op; you see the same artifact as `fuse=False`.

2. **Polyhedron with degenerate end caps at the bbox extreme.** A `path_extrude`'d helix or other polyhedron whose top/bottom face lies exactly at the bbox max or min along the normal can cause CGAL to fail at *render* time with an opaque "given mesh is not closed" / "Projection() failed" error. The build succeeds; the rendered output is broken.

3. **Concave-inner curved surfaces (cylinder bore, hollow-sphere inside) with a peg larger than the wall thickness.** The peg's corners would punch through the outer wall. The framework can't see the wall thickness and doesn't try; the result is visible chunks of peg material outside the host.

If you hit any of these, the recovery paths in priority order:

- **Restructure the geometry** so the fuse anchor is on a clean convex planar face. Often the cleanest fix.
- **Use `fuse=False` on that one attach** — exact contact, no auto-eps, but no silent failure either.
- **Wrap the assembly in `disable_eps_fuse()`** — scope-wide opt-out, useful when you're debugging or when many fuses in an assembly are all having trouble.
- **Hand-craft the eps overlap inside the affected shape's `build()`** — last resort.
