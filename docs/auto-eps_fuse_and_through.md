# Eliminating manual epsilon overlap

OpenSCAD's F5 preview shows wavering or missing surfaces when two shapes share a face in a boolean operation. The fix is a tiny overlap (epsilon). SCADwright handles that overlap automatically: pass `fuse=True` to `attach()` for clean unions, or chain `through()` for clean cuts inside `difference()`. You don't have to define `eps` constants or manually adjust cutter sizes.

Everything on this page works on flat-face contacts. For attaching things to the outside of a cylinder, cone, or sphere, see [`bridge=True`](anchors.md#putting-things-on-curved-surfaces-bridgetrue) in `anchors.md`.

## Quick reference

| Need | Use |
|---|---|
| Position a part flush against another flat face, with overlap so `union()` is preview-clean | `part.attach(other, fuse=True)` |
| Same, but pick the bond explicitly | `part.attach(other, bond="overlap" | "shift")` |
| Mate two parts already in place (concentric cylinders, lid on a matching tube, etc.) | `part.fuse(host)` — see [attach.md](attach.md#mating-without-placement-nodefuse) |
| Drill a cutter through a parent shape | `cutter.through(parent)` inside `difference()` |
| Combine two parts symmetrically — either side may carry the eps lever | `fuse(a, b)` from `scadwright.boolops` (peer auto-match form) |
| Same, with explicit anchors and bond/bridge control | `fuse(a, b, on=..., using_anchor=..., bond=..., bridge=...)` |
| Fuse a whole set of positioned parts into one body | `fuse(a, b, c, ...)` — raises if they don't all touch |
| Stack parts along an axis and fuse them | `stack(a, b, c, axis="z")` — see [composition_helpers.md](composition_helpers.md#stack) |
| Disable all auto-eps inside a scope (precision builds, performance debugging) | `with disable_eps_fuse(): ...` |
| Override the default `eps` value across a scope | `with tolerances(eps=0.001): ...` |
| Override `through()`'s face-matching tolerance | `with tolerances(coincidence=1e-5): ...` |

## Clean unions with `attach(fuse=True)`

When two parts sit flush against each other (a pylon on a floor, a peg on a plate), `fuse=True` on `attach()` adds a small overlap at the contact face. That removes the wavering-surface seam from OpenSCAD's preview:

```python
from scadwright.boolops import union
from scadwright.primitives import cube
from scadwright.shapes import Tube

floor = cube([40, 40, 2])
pylon = Tube(od=7, id=3, h=8).attach(floor, fuse=True)
part = union(floor, pylon)
```

The default overlap is 0.01 mm. Override with `eps=`:

```python
Tube(od=7, id=3, h=8).attach(floor, fuse=True, eps=0.05)
```

The overlap goes at the contact face only. The rest of the moving shape stays exactly where you put it; only the contact face shifts by `eps`.

`fuse=True` only applies to flat-face contact. On a cylinder, cone, or sphere it raises an error and points you at `bridge=True` instead (see [anchors.md](anchors.md#putting-things-on-curved-surfaces-bridgetrue)). On other contact shapes that can't be cleanly extended, the error message suggests `bond="shift"` for a fallback or `fuse=False` for no overlap; see [Advanced notes](#advanced-notes) for the details.

## Clean cuts with `through()`

When you drill a hole through a shape, the cutter (the hole-shaped cylinder you subtract) needs to stick out slightly past the surface so OpenSCAD's preview doesn't show a flickering boundary. `through(parent)` does that for you. It extends the cutter through any face of `parent` it touches, by a small overlap:

```python
from scadwright.boolops import difference
from scadwright.primitives import cube, cylinder

box = cube([20, 20, 10])
part = difference(box, cylinder(h=10, r=3).through(box))
```

The cylinder's top and bottom both sit flush with the box, so `through()` extends both ends by 0.01 mm (the default overlap). No manual `EPS` constant needed.

### Three common cases

`through()` checks which faces of the cutter line up with faces of the parent and extends only those. Faces that don't line up are left alone, so the same call works whether you're drilling all the way through, only partway, or making a blind pocket:

```python
# Through-hole: both ends flush -> both extended.
cylinder(h=10, r=3).through(box)

# Counterbore: only top is flush -> only top extended.
cylinder(h=5, r=6).up(5).through(box)

# Blind pocket: neither end flush -> no change (harmless to call).
cylinder(h=4, r=3).up(3).through(box)
```

### Specifying the cut axis

`through()` figures out the cut axis automatically by looking for faces that line up. When it can't tell (for example, a cube-shaped cutter where any axis would work), pass `axis=` explicitly:

```python
cube([20, 20, 3]).up(3).through(box, axis="z")
```

### Custom overlap distance

The default overlap is 0.01 mm. Override with `eps=`:

```python
cylinder(h=10, r=3).through(box, eps=0.1)
```

### Call order

Call `through()` after positioning the cutter. It needs to see the final position to find which faces line up with the parent:

```python
cylinder(h=10, r=3).up(5).right(8).through(box)   # position first, then through
```

### Rotated cutters

For angled drill holes, chamfered countersinks on non-vertical faces, draft-angled inserts, and other rotated-cutter patterns, the automatic face matching doesn't work. A rotated cutter's bounding box is bigger than the cutter itself, so the framework can't tell from the world-space bounding box which faces line up. Pass `axis="local"` (or `"local_x"` / `"local_y"` / `"local_z"`) to do the matching in the cutter's local frame:

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

If you forget `axis="local"` on a rotated cutter, `through()` raises with a clear pointer rather than silently doing nothing. Cutters rotated by a clean 90° (like `rotate([0, 90, 0])`) keep an axis-aligned bounding box, so the default automatic matching handles them and no error is raised.

Non-rotation transforms (anisotropic scale, mirror) in the cutter's chain raise an error. The local-frame matching needs a pure rotation; apply scale to the underlying primitive's parameters instead.

## Skipping the overlap: `disable_eps_fuse()`

Two cases need a way to turn off the auto-eps overlap without rewriting individual calls:

- **Precision builds.** Final dimensions or anchor positions need to match the source exactly. The default 0.01 mm overlap would otherwise shift fits or measured geometry by that amount.
- **Performance debugging.** Many fuses in a complex assembly add up. Disabling the overlap in a sub-tree lets you compare frame rates or isolate a slow path.

Wrap the block in `with disable_eps_fuse():`:

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

Inside the block, `attach(fuse=True)` and the standalone `fuse(...)` give exact contact instead of an overlap. `bond=` is dropped. The small peg-side overlap that `bridge=True` adds when paired with `fuse=True` also drops. The bridge geometry itself stays, because that's part of the design, not eps. Everything else (anchor lookup, placement, `angle=`, `at_z=`, `at_radial=`, `orient=True`, `through()`) keeps working.

Nested blocks compose, and exiting any block restores the previous state.

## Custom tolerances with `tolerances()`

The default overlap is 0.01 mm. The default face-matching tolerance for `through()` is 1e-4 mm. Override either or both across a scope with `tolerances()`:

```python
from scadwright import tolerances

with tolerances(eps=0.001):
    return self.precision_assembly()

with tolerances(eps=0.001, coincidence=1e-5):
    return self.tight_fit_assembly()
```

Common uses: precision builds where the default 0.01 mm is too coarse for the fits involved; models converted from non-standard units where the natural eps differs; tight-tolerance assemblies where `through()`'s face-matching needs to be stricter.

`tolerances()` overrides the defaults only when you don't pass an explicit `eps=` on the call. Calls like `attach(fuse=True, eps=0.05)` still use the explicit value. Nested `tolerances()` blocks compose, and exiting any block restores the previous defaults.

## Known limits

Auto-eps handles the common cases. Three patterns can still fail to fix the preview artifact:

1. **Non-convex shapes where the contact face is empty.** A torus tangent point, two separate parts whose combined bounding box covers a gap between them, or an anchor placed where a `difference()` removed all the material at that plane. The framework's bounding-box check says the anchor is on the surface, but the actual contact cross-section is empty. The fuse silently becomes a no-op (same result as `fuse=False`).

2. **Polyhedron with a degenerate cap at the bounding-box extreme.** A `path_extrude`'d helix or other polyhedron whose top or bottom face sits exactly at the bbox extreme can cause OpenSCAD's CGAL renderer to fail at render time with an opaque `"given mesh is not closed"` or `"Projection() failed"` error. The SCADwright build succeeds; the render doesn't.

3. **Peg larger than a tube's wall thickness.** When you attach a peg to a hollow cylinder's inner wall *without* `bridge=True`, the peg's corners can punch through the outer wall. The framework can't see the wall thickness and doesn't try; the result is chunks of peg material sticking out the back of the host. Pass `bridge=True` on the inner-wall attach to clip the peg to the bore — the corners get curved away to match the bore radius, so they never reach the outer surface.

Recovery options, in priority order:

- **Restructure the geometry** so the contact is on a clean flat face. Often the cleanest fix.
- **Pass `fuse=False` on that one attach.** You get exact contact with no overlap, but no silent failure either.
- **Wrap the block in `disable_eps_fuse()`.** Scope-wide opt-out: useful when you're debugging, or when many fuses are misbehaving.
- **Hand-craft the eps overlap inside the affected shape's `build()`.** Last resort.

## Advanced notes

### How `fuse=True` adds the overlap

The overlap is added in one of two ways.

**For primitives** (`Cube`, `Cylinder` planar caps, `linear_extrude` end-caps), the framework adjusts the shape's parameters directly: a `Cube` gets its `size[axis]` bumped by `eps`, a `Cylinder` cap gets `h` bumped, and so on. This works through `Translate`, `Rotate`, and `Mirror` wrappers too, so `cube(...).up(5).rotate([0, 90, 0])` still takes this fast path. No CGAL evaluation needed.

**For other shapes** (`rotate_extrude` end-caps, `Polyhedron` faces, results of `difference()` / `union()` / `intersection()`, custom Components without their own extension method), the framework falls back to a more general construction:

1. Aligns the anchor plane so the normal points along `+Z` and the anchor sits at `z=0`.
2. Takes `projection(cut=True)` to extract the 2D cross-section at that plane.
3. `linear_extrude`s the cross-section by `eps`.
4. Inverse-aligns the slab and unions it back into the shape.

The result preserves the user-facing dimensions of the shape; only the contact face shifts. The cost is one CGAL evaluation per fuse, so heavy use can slow down rendering. `disable_eps_fuse()` skips both paths.

Before building the slab, the framework validates the anchor: it must lie on the shape's outermost face along its normal direction, and the bounding box must have non-zero extent in at least two axes. Failures raise a clear `ValidationError`. `Cylinder.cross_section_extend` also raises when the contact face is at the apex of a cone (`r=0`).

If neither method applies (concave inner walls, contacts that aren't flat-on-flat, shapes whose anchors can't be cleanly extended), `fuse=True` raises with the alternatives:

- `bond="shift"` translates the moving shape by `eps` along the contact normal. The opposite face drifts by `eps` too, so don't combine with `through()` (run `through()` first).
- `fuse=False` for exact contact, no overlap.
- `bridge=True` for the curved-host case.

### Curved-surface fuses

`node.fuse(host)` and `fuse(a, b)` extend the same way as `attach(fuse=True)` for planar contact. On curved concentric contact (cylindrical, conical, spherical, meridional), the framework picks the side whose `fuse_extend` carries the radial lever, preferring `inner=False` (the convex/outer side) first.

Standard-library shapes that ship with a curved lever:

- `Cylinder` primitive — bumps `r1` and `r2`.
- `Sphere` primitive — bumps `r`.
- `Tube` — rebuilds with `od + 2*eps` (outer wall) or `id - 2*eps` (inner wall).
- `Funnel` — rebuilds with both ends' `od` (outer) or `id` (inner) bumped.
- `Barrel` — rebuilds with `end_d`/`mid_d` (outer) or `thk += eps` (inner).
- `SphericalShell` — rebuilds with `od + 2*eps` (outer) or `id - 2*eps` (inner).

Component authors who want their Component to act as the extending side override `fuse_extend(anchor, eps)` and return the rebuilt Component. Authors without an override rely on the other side — an `ElementHolder` inside a `Tube` works without overriding because `Tube` carries the inner-wall lever. If neither side has a lever, the call raises with both class names and points at the override.

On curved concentric contact the framework does not translate self: the matched anchor positions are reference points on the contact surfaces, not the contact location, and translating would slide self off the placement the user already chose. On planar contact the auto-match guarantee means positions already coincide, so no translate runs there either. Only the explicit-placement form at non-coincident planar anchors shifts self.

### `bond=` for explicit control

`fuse=True` picks `bond="overlap"` when it applies. Pass `bond=` directly when you want explicit control:

| `bond=` | What it does | When it raises |
|---|---|---|
| `"overlap"` | Local face extension at a flat-face contact (uses the parametric path first, the cross-section fallback otherwise). Preserves the user-facing dimensions of the extended side. | Either anchor isn't planar; the cross-section is degenerate. |
| `"shift"` | Bilateral translate of the moving shape by `eps` along the contact normal. The opposite face drifts by `eps`. | Never raises on geometry; always works. |

```python
peg.attach(plate, bond="overlap")              # explicit flat-face extension
peg.attach(plate, bond="shift")                # explicit bilateral shift
```

`bond="..."` implies `fuse=True`. Passing `fuse=False` with a bond raises (contradiction). `bond=` and `bridge=True` can't combine; `bond=` is for the flat-face overlap, `bridge=True` is the curved-surface fill. The default cascade for `fuse=True` doesn't silently fall through to `shift`. If you want the bilateral shift, ask for it with `bond="shift"`. The standalone `fuse(a, b, ..., bond=...)` accepts the same values.

### Symmetric form: `fuse(a, b, ...)`

`attach(fuse=True)` only extends `self`; the framework can't extend `other` because `other` isn't part of the returned value, so an extension on it would be invisible. The standalone `fuse(a, b)` from `scadwright.boolops` returns the union directly, so either side can carry the extension.

`fuse(a, b)` with no anchors auto-matches the contact, same rules as `node.fuse(host)`. With explicit `on=` / `using_anchor=` / `bond=` / `bridge=`, it falls back to placement-style behavior — useful when you want symmetric side-selection paired with an explicit bond.

### Fusing several parts: `fuse(*parts)`

`fuse(a, b, c, ...)` fuses a whole set of already-positioned parts into one body. It finds each touching pair's contact the same way the two-part form does, and adds the overlap at every contact without moving any part.

It treats the call as an assertion that the parts form one connected body. If they split into groups with no contact between them, it raises and names them — which catches a dimension that has drifted just far enough that two faces no longer meet. For parts meant to sit apart, use `union(*parts)` instead.

The single-contact selectors (`on=`, `using_anchor=`, `from_anchor=`, `bond=`, `bridge=`) don't apply with more than two parts, because each names one contact and there are now many. To fuse a specific pair at a named contact, call the two-part form on that pair.

### How `through()` handles rotated cutters internally

`through()` walks the cutter's outer rotations and translations to compute the full local-to-world transform, projects the cutter's end-face centers (at the cutter's local origin on the cut axis) into world space, and checks them against the parent's bounding-box face planes. The extension applies as a `Translate(Scale(...))` inserted at the leaf level, so the emitted SCAD keeps the original `rotate(...)` calls plus a leaf-level `translate + scale` rather than collapsing the whole stack into an opaque `multmatrix`.
