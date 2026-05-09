# Eliminating manual epsilon overlap

OpenSCAD requires a small overlap (epsilon) whenever two shapes share a face in a boolean operation. Without it, F5 preview shows wavering, missing, or flickering surfaces — the GL renderer can't classify points on a coincident boundary. SCADwright handles this automatically so you don't have to define `eps` constants and manually adjust cutter sizes.

## How to reach the auto-eps mechanisms

| Need | Use |
|---|---|
| Position a part flush against another, with overlap so `union()` is preview-clean | `part.attach(other, fuse=True)` |
| Same, but pick the bond explicitly | `part.attach(other, bond="overlap" | "bridge" | "shift")` |
| Drill a cutter through a parent shape | `cutter.through(parent)` inside `difference()` |
| Combine two parts symmetrically with overlap (no "self" / "other" asymmetry) | `fuse(a, b, on=..., using_anchor=..., bond=..., eps=...)` from `scadwright.boolops` |
| Disable all auto-eps inside a scope (precision builds, perf debugging) | `with disable_eps_fuse(): ...` |
| Override the default `eps` value across a scope (precision / unit-conversion / tight-tolerance models) | `with tolerances(eps=0.001): ...` |
| Override `through()`'s coincident-face matching tolerance | `with tolerances(coincidence=1e-5): ...` |

## Bonds: explicit control over how the overlap is constructed

`fuse=True` runs a smart cascade that picks the right mechanism based on the contact geometry. When you want explicit control, pass `bond=` instead:

| `bond=` | What it does | When it raises |
|---|---|---|
| `"overlap"` | Local face extension at a planar contact (parametric `fuse_extend` first, cross-section fallback). Preserves the user-facing dimensions of the extended side. | Either anchor isn't planar; cross-section is degenerate. |
| `"bridge"` | Inscription bridge for a curved convex-outer host (cylindrical / conical / spherical). Fills the air gap between the peg's flat face and the host's curved surface. | Host isn't convex-outer curved; contact normals aren't coaxial; host has no analytical radius. |
| `"shift"` | Bilateral translate of the moving shape by `eps` along the contact normal. The opposite face drifts by `eps`. | Never raises on geometry — always works. |

```python
peg.attach(plate, bond="overlap")              # explicit planar extension
peg.attach(hub, on="outer_wall", angle=0,
           orient=True, bond="bridge")          # explicit curved-host bridge
peg.attach(plate, bond="shift")                 # explicit bilateral shift
```

`bond="..."` implies `fuse=True`; passing `fuse=False` with a bond raises (contradiction). `fuse=True` without a bond uses the smart cascade: `bridge` if applicable, else `overlap` if applicable, else **raises** with both reasons and a workaround pointer. The cascade does not silently fall through to `shift` — the user who actually wants the bilateral shift writes `bond="shift"` explicitly. The free function `fuse(a, b, ..., bond=...)` accepts the same vocabulary.

`disable_eps_fuse()` short-circuits everything to exact contact, even explicit `bond=...` values — the scope-wide opt-out wins by design (precision builds shouldn't have eps geometry sneaking in anywhere).

## Known limits — what to do when preview still flickers

Auto-eps works for the common cases. There are three patterns where it can silently fail to fix the preview artifact:

1. **Non-convex peg or host with empty cross-section at the contact face.** A torus tangent point, two separated parts whose union bbox includes the gap, an anchor placed where a `difference()` removed all the material at that plane. The framework's bbox-projection check passes, but the actual cross-section is empty — only OpenSCAD's CGAL evaluator can detect this, and we don't pay that cost at build time. The fuse becomes a no-op; you see the same artifact as `fuse=False`.

2. **Polyhedron with degenerate end caps at the bbox extreme.** A `path_extrude`'d helix or other polyhedron whose top/bottom face lies exactly at the bbox max or min along the normal can cause CGAL to fail at *render* time with an opaque "given mesh is not closed" / "Projection() failed" error. The build succeeds; the rendered output is broken.

3. **Concave-inner curved surfaces (cylinder bore, hollow-sphere inside) with a peg larger than the wall thickness.** The peg's corners would punch through the outer wall. The framework can't see the wall thickness and doesn't try; the result is visible chunks of peg material outside the host.

If you hit any of these, the recovery paths in priority order:

- **Restructure the geometry** so the fuse anchor is on a clean convex planar face. Often the cleanest fix.
- **Use `fuse=False` on that one attach** — exact contact, no auto-eps, but no silent failure either.
- **Wrap the assembly in `disable_eps_fuse()`** — scope-wide opt-out, useful when you're debugging or when many fuses in an assembly are all having trouble.
- **Hand-craft the eps overlap inside the affected shape's `build()`** — last resort.

```python
from scadwright import disable_eps_fuse

with disable_eps_fuse():
    return self.assembly()    # all fuse=True calls become exact contacts
```

`disable_eps_fuse()` is also useful for **precision builds** (where any eps would shift fits or measured-on-bed geometry by 0.01mm) and **performance debugging** (where you want to compare frame rates with/without the eps machinery active).

---

## `through(parent)` -- for cutters in `difference()`

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

## `attach(fuse=True)` -- for joints in `union()`

When two parts sit flush against each other (e.g. a pylon on a floor), `fuse=True` on `attach()` pushes self slightly into the contact face, eliminating the coincident-surface seam:

```python
from scadwright.boolops import union
from scadwright.shapes import Tube

floor = cube([40, 40, 2])
pylon = Tube(od=7, id=3, h=8).attach(floor, fuse=True)
part = union(floor, pylon)
```

The pylon overlaps the floor by 0.01 at the contact face. Override with `eps=`:

```python
Tube(od=7, id=3, h=8).attach(floor, fuse=True, eps=0.05)
```
