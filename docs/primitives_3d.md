# 3D primitives

The four building-block 3D shapes. Each returns a shape you can transform, combine with others, or render directly.

Import from `scadwright.primitives`:

```python
from scadwright.primitives import cube, sphere, cylinder, polyhedron
```

## `cube`

Creates a rectangular box.

```python
cube([10, 20, 30])                          # 10 wide, 20 deep, 30 tall
cube(5)                                     # cube with all sides 5
cube([10, 20, 30], center=True)             # centered on the origin
cube([10, 20, 30], center="xy")             # centered on X and Y; sits on Z=0
cube([10, 20, 30], center=[True, True, False])  # same as "xy"
```

**Parameters:**

- `size` — either a single number (cube with equal sides) or a 3-element list `[x, y, z]`.
- `center` — controls which axes are centered. Four accepted forms, all equivalent where they overlap:
  - `center=True` — centered on all three axes.
  - `center=False` (default) — corner at the origin; cube grows into +X, +Y, +Z.
  - `center="xy"` — string listing axes to center. `"xy"` centers X and Y but sits on Z=0; `"z"` centers Z only, etc.
  - `center=[True, True, False]` — per-axis bool list, same effect as `"xy"`.

**About `center`:** OpenSCAD's `center` is all-or-nothing. scadwright lets you center on individual axes. Pass a string of axis letters (`"x"`, `"xy"`, `"xyz"`) or a list of three booleans. When the centering is mixed, scadwright wraps the cube in a `translate(...)` automatically.

## `sphere`

Creates a sphere centered at the origin.

```python
sphere(r=5)
sphere(d=10)            # diameter form
sphere(r=5, fn=64)      # smoother (more facets)
```

**Parameters:**

- `r` — radius, or `d` — diameter. Pass exactly one; passing both raises `ValidationError`.
- `fn`, `fa`, `fs` — facet controls (smoothness). See [Resolution](resolution.md).

A sphere with no facet control uses OpenSCAD's defaults, which gives a fairly low-poly result. Pass `fn=` or wrap the call in `with resolution(fn=64):` for smoother output.

## `cylinder`

Creates a cylinder (or a truncated cone) along the Z axis.

```python
cylinder(h=10, r=3)                         # cylinder
cylinder(h=10, d=6)                         # diameter form
cylinder(h=10, r1=5, r2=2)                  # cone (different radii at each end)
cylinder(h=10, r=3, center=True)            # centered on Z; otherwise sits on Z=0
cylinder(h=10, r=3, fn=64)                  # smoother
```

**Parameters:**

- `h` — height along Z.
- `r` — uniform radius, or `d` — uniform diameter. Pass at most one.
- `r1`, `r2` (or `d1`, `d2`) — bottom and top radius for a cone. Each pair is independent: pass `r1` or `d1` (not both), and `r2` or `d2` (not both). Mixing across the taper (`r1=..., d2=...`) is fine. When `r1`/`r2` are set they override the uniform `r`.
- `center` — `True` straddles the XY plane; `False` (default) puts the base on Z=0.

Passing both a radius and its matching diameter (e.g. `cylinder(r=3, d=6)`) raises `ValidationError` — the intent is ambiguous, so we refuse to guess.

## `polyhedron`

Defines an arbitrary 3D shape from a list of points and the faces that connect them.

```python
polyhedron(
    points=[
        [0, 0, 0],
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
    ],
    faces=[
        [0, 1, 2],          # bottom
        [0, 2, 3],          # left
        [0, 3, 1],          # back
        [1, 3, 2],          # slanted front
    ],
)
```

**Parameters:**

- `points` — list of `[x, y, z]` coordinates.
- `faces` — list of faces; each face lists the indices into `points` that form its corners. A face must have at least 3 corners.
- `convexity` — optional integer hint to OpenSCAD for rendering complex shapes; you usually don't need it.

scadwright checks that every index in `faces` refers to a real point. Out-of-range indices raise a `ValidationError` with the offending line.

## `surface`

Imports a heightmap from a PNG or DAT file and produces 3D surface geometry. OpenSCAD reads the file at render time.

```python
from scadwright.primitives import surface

terrain = surface("heightmap.png", center=True, invert=False, convexity=5)
```

**Parameters:**

- `file` — path to the image or data file. Passed through to SCAD verbatim; resolution is relative to the SCAD file's working directory at render time.
- `center` — if `True`, the surface is centered on the XY origin. Default `False`.
- `invert` — for PNG input, inverts the brightness-to-height mapping. Ignored for DAT files.
- `convexity` — optional render-complexity hint.

**Bounding box note:** because the surface's extent depends on the file contents (which scadwright doesn't parse), `bbox(surface(...))` returns a degenerate zero-bbox. If you need a real bbox for assembly checks, wrap the surface with a known container (e.g. `intersection(surface(...), cube([W, H, Z], center=True))`) so the intersection's bbox reflects your intended bounds.

## `scad_import`

Imports external geometry — STL, SVG, DXF, 3MF, OFF, AMF. The typical scenario: you have a fastener model as an STL that you want to drop into an assembly, or an SVG profile you want to `linear_extrude` into a 3D shape.

```python
from scadwright.primitives import scad_import
from scadwright.extrusions import linear_extrude

# Bring an STL fastener into your assembly — position and combine as usual:
fastener = scad_import("m3_screw.stl").rotate([0, 0, 45]).translate([10, 0, 5])

# Extrude an SVG profile to 3D:
profile = scad_import("gasket_profile.svg", bbox=((0, 0, 0), (60, 40, 0)))
gasket = linear_extrude(profile, height=3)
```

**Parameters:**

- `file` — path to the file. Passed to SCAD verbatim; resolution happens at OpenSCAD render time relative to the `.scad` file's working directory.
- `bbox` — optional `((min_x, min_y, min_z), (max_x, max_y, max_z))` hint for assembly bbox checks. See "Bounding box" below.
- `convexity` — optional render-complexity hint.
- `layer`, `origin`, `scale` — DXF-specific parameters passed through to SCAD.
- `fn`, `fa`, `fs` — smoothness controls for DXF arcs.

### Bounding box

SCADwright resolves the imported shape's bbox in this order:

1. **Explicit `bbox=` hint** wins if you provide one.
2. **STL files are auto-parsed** — if the path ends in `.stl` and the file exists, scadwright reads the triangle vertices to compute the real bbox. No hint needed.
3. **Otherwise, degenerate zero-bbox.** `assert_fits_in` and similar checks will treat the shape as a point at the origin.

For non-STL formats (SVG/DXF/3MF/OFF/AMF), scadwright doesn't parse the file, so provide the `bbox=` hint when you need assembly checks:

```python
# Hint required for bbox-aware operations on non-STL inputs:
svg_part = scad_import("profile.svg", bbox=((0, 0, 0), (100, 50, 0)))
assert_fits_in(svg_part, ((0, 0, 0), (200, 100, 0)))   # works with the hint

# Without the hint, the bbox is degenerate:
svg_part = scad_import("profile.svg")
bbox(svg_part)        # BBox(min=(0,0,0), max=(0,0,0))
```

If you change an STL file mid-session and want scadwright to re-read it:

```python
from scadwright._stl import stl_bbox
stl_bbox.cache_clear()
```

---

### Advanced notes

- `cube` per-axis centering emits SCAD as `translate([offsets]) cube(size, center=false);` rather than touching OpenSCAD's `center` flag. The wrapping is automatic; the bounding box reflects the post-translation position.
- `polyhedron` doesn't validate that faces form a closed solid — that's OpenSCAD's job at render time. scadwright only checks index ranges.

### See also

- [Tubes and shells](shapes/tubes_and_shells.md) -- `Tube`, `Funnel`, `RoundedBox` built on these primitives, with equation-driven dimensions
- [Polyhedra](shapes/polyhedra.md) -- `Prism`, `Pyramid`, `Torus`, `Dome`, Platonic solids
