# Transformations

Transformations move, rotate, scale, mirror, or color a shape. In SCADwright they're methods you call on the shape itself; each returns a new shape with the transform applied. The original shape is unchanged, so you can reuse it.

Imports used on this page:

```python
# Transforms are available as chained methods on every shape
# (e.g. cube(10).translate([5, 0, 0])) — the usual form used in
# these examples. The same operations are available as standalone
# functions too:
from scadwright.transforms import translate, rotate, scale, mirror, color, resize, offset
from scadwright.transforms import multmatrix, projection
from scadwright.transforms import highlight, background, disable, only
```

```python
moved = cube(10).translate([5, 0, 0])
red_box = cube(10).red()
chain = cube(10).translate([5, 0, 0]).rotate([0, 45, 0]).red()
```

Vector arguments accept either a list or keyword form:

```python
node.translate([5, 0, 0])
node.translate(x=5)             # equivalent
```

## `translate`

Moves a shape by an offset.

```python
node.translate([5, 10, 0])
node.translate(z=20)
```

**Parameters:**

- A 3-vector `[x, y, z]`, or any combination of `x=`, `y=`, `z=` keyword arguments. Unspecified axes default to 0.

## `rotate`

Rotates a shape. Two forms:

```python
node.rotate([0, 45, 0])                       # Euler angles in degrees
node.rotate(x=90)                             # same idea, keyword form
node.rotate(angle=30, axis=[0, 0, 1])         # readable axis-angle form
node.rotate(a=30, v=[0, 0, 1])                # same, SCAD-style short names
```

**The two forms:**

- **Euler angles**: pass a 3-vector `[x, y, z]` of rotations in degrees. OpenSCAD applies these in ZYX order — i.e. rotate around X first, then Y, then Z.
- **Axis–angle**: pass `angle=` (degrees) and `axis=` (3-vector) to rotate around an arbitrary axis. The SCAD-native short names `a=` / `v=` are also accepted; use whichever you prefer. Mixing the aliases (e.g. `a=30, angle=45`) raises.

## `scale`

Stretches a shape along each axis.

```python
node.scale(2)                            # 2× in every direction
node.scale([2, 3, 1])                    # 2× wide, 3× deep, no change in height
node.scale(x=2, y=3, z=1)
```

**Parameters:**

- A scalar (broadcast to all axes) or a 3-vector `[x, y, z]`. Keyword form also works.

## `mirror`

Mirrors a shape across a plane through the origin.

```python
node.mirror([1, 0, 0])                   # mirror across the YZ plane (flip in X)
node.mirror(x=1)
```

**Parameters:**

- A 3-vector that's the *normal* to the mirror plane. `[1, 0, 0]` flips X, `[0, 0, 1]` flips Z, etc. A scalar isn't allowed (it'd be ambiguous which axis you meant).

## `color`

Colors a shape (visible in OpenSCAD's preview; doesn't affect the rendered geometry).

```python
node.color("red")
node.color("#3399ff")
node.color([0.2, 0.8, 0.3])
node.color([0.2, 0.8, 0.3], alpha=0.5)
```

**Parameters:**

- `c` — any [W3C SVG / X11 color name](https://www.w3.org/TR/css-color-3/#svg-color) (`"red"`, `"steelblue"`, `"crimson"`, …), a hex string (`"#3399ff"`), or an RGB list `[r, g, b]` with values in 0–1.
- `alpha` — opacity from 0 (transparent) to 1 (solid). Defaults to 1.

## `resize`

Stretches a shape so its bounding box matches a target size.

```python
node.resize([10, 10, 10])                # forces the shape to fit a 10-cube
node.resize([10, 0, 10], auto=True)      # 0 means "scale this axis proportionally"
```

**Parameters:**

- `new_size` — target size as `[x, y, z]`.
- `auto` — when `True` (or per-axis bool list), axes set to 0 in `new_size` are scaled proportionally to keep the shape's aspect ratio.

## `multmatrix`

Apply an arbitrary 4×4 transform matrix to a shape. Use this when one of the named transforms isn't enough — for example, shears, or when you have a precomputed placement matrix. See [the Matrix reference](matrix.md) for constructors and operations.

```python
from scadwright import Matrix

# Equivalent to cube(10).translate([5, 0, 0]):
cube(10).multmatrix(Matrix.translate(5, 0, 0))

# A shear: x' = x + 0.5*y
shear = Matrix((
    (1, 0.5, 0, 0),
    (0, 1,   0, 0),
    (0, 0,   1, 0),
    (0, 0,   0, 1),
))
sheared = cube(10).multmatrix(shear)

# Accepts a plain list of lists too (4x4, 3x4, or 4x3; the fourth row/column
# is padded with [0, 0, 0, 1] when needed):
cube(10).multmatrix([
    [1, 0, 0, 5],
    [0, 1, 0, 0],
    [0, 0, 1, 0],
    [0, 0, 0, 1],
])
```

The bounding box transforms through the matrix exactly like the other rigid transforms do.

## `projection` (3D → 2D)

Flattens a 3D shape to a 2D shape. Two modes:

- `cut=False` (default) — project onto the XY plane, like a shadow cast straight down.
- `cut=True` — take the cross-section at z=0.

```python
# Outline of a 3D part, useful for laser-cut templates:
outline = my_part.projection()

# Cross-section of a sphere at its equator (shifted so the cut happens at z=0):
disc = sphere(r=10, fn=32).translate([0, 0, -5]).projection(cut=True)
```

The result is 2D (Z extent is zero) and can be extruded, offset, booleaned with other 2D shapes, etc.

The bbox of a projection is conservatively the XY footprint of the child — for `cut=True` the actual cross-section may be smaller, but `assert_fits_in` checks stay on the safe side.

## `offset` (2D only)

Expands or contracts a 2D shape. The usual tool for walls and shells: `circle(r=10).offset(r=-2)` gives you a ring 2 units thick.

```python
circle(r=10).offset(r=2)                # rounded +2 expansion
square([10, 10]).offset(delta=1)        # sharp +1 expansion
square([10, 10]).offset(delta=1, chamfer=True)   # chamfered corners
circle(r=10).offset(r=-3)               # contract by 3
```

**Parameters:**

- Pass exactly one of `r` or `delta`. `r` rounds the corners; `delta` keeps them sharp (or chamfered if `chamfer=True`).
- `r` / `delta` may be negative (contract).
- `chamfer` is only meaningful with `delta`; combining `r` and `chamfer` raises `ValidationError`.
- `fn` / `fa` / `fs` — facet controls for the rounded form.

Offset operates in the XY plane; use it before `linear_extrude` to build variable-thickness walls and shells.

## Placement helpers

### `center_bbox`

Moves a shape so its axis-aligned bounding box is centered at the origin. Handy when a part was built in its natural coordinates and you need it centered for further composition.

```python
part = my_complicated_thing.center_bbox()
```

Works on any shape (primitives, Components, CSG trees). The extent is unchanged; only the position shifts.

### `attach`

Positions a shape so one of its anchors touches an anchor on another shape. The most common use is stacking one part on top of another:

```python
plate = cube([40, 40, 2])
peg   = cube([10, 10, 5]).attach(plate)              # bottom of peg on top of plate
```

`face` names which anchor on the other shape to attach to; `at` names which anchor on self to use as the contact point:

```python
cube([10, 10, 5]).attach(plate, face="top")                    # default
cube([10, 10, 5]).attach(plate, face="bottom", at="top")       # peg underneath
cube([5, 5, 5]).attach(plate, face="rside", at="lside")        # side-by-side
```

Both `face` and `at` accept friendly names or axis-sign names:

| Friendly | Axis-sign | Direction   |
|----------|-----------|-------------|
| `top`    | `+z`      | up          |
| `bottom` | `-z`      | down        |
| `front`  | `-y`      | toward you  |
| `back`   | `+y`      | away        |
| `lside`  | `-x`      | left        |
| `rside`  | `+x`      | right       |

By default the placed shape is centered on the target face. For off-center placement, chain a translate:

```python
cube([5, 5, 5]).attach(plate).right(10)               # offset 10 in +X
```

Pass `orient=True` to also rotate self so the two anchors' normals oppose each other (faces touching). Without it, only translation is applied:

```python
peg.attach(plate, face="rside", at="bottom", orient=True)  # rotate to face outward
```

Components can declare custom anchors at class scope — see [Anchors and attachment](anchors.md) for the full reference.

### `through`

Extends a cutter through any coincident face of a parent shape, adding epsilon overlap for clean `difference()` operations:

```python
part = difference(box, cylinder(h=10, r=3).through(box))
```

See [Eliminating epsilon overlap](auto-eps_fuse_and_through.md) for details.

## Preview modifiers

OpenSCAD's debug sigils (`#`, `%`, `*`, `!`) — they affect the *preview* only (F5), not the rendered output (F6). Useful for visualizing construction without changing geometry.

```python
cube(10).highlight()      # `#` — show in translucent red (debug)
cube(10).background()     # `%` — show but exclude from render
cube(10).disable()        # `*` — treat as absent
cube(10).only()           # `!` — render only this subtree, ignore siblings
```

Bbox effect: `highlight`, `background`, and `only` pass through the child's bbox. `disable` reports a zero bbox (the shape is semantically absent).

## Shorthand methods

These are convenience wrappers around `translate`, `mirror`, and `color`. They make common operations more readable.

**Move along one axis:**

```python
node.up(5)         # translate(z=+5)
node.down(5)       # translate(z=-5)
node.left(5)       # translate(x=-5)
node.right(5)      # translate(x=+5)
node.forward(5)    # translate(y=+5)
node.back(5)       # translate(y=-5)
```

**Mirror across an axis plane:**

```python
node.flip("z")     # mirror across the XY plane (flip in Z)
node.flip("x")     # mirror across the YZ plane (flip in X)
```

**Color shorthand methods:**

Every [W3C SVG / X11 color name](https://www.w3.org/TR/css-color-3/#svg-color) is available as a method on any shape — the same set OpenSCAD's `color()` accepts.

```python
node.red()
node.crimson()
node.steelblue(alpha=0.5)
node.darkolivegreen()
node.papayawhip()
```

The full list (147 colors) lives in `scadwright.colors.SVG_COLORS`. Each method takes an optional `alpha` argument (0–1).

---

### Advanced notes

- Each transform method records the file and line of the call. When you turn on `--debug` in the CLI, those locations appear as comments in the generated SCAD.
- `mirror`'s vector doesn't have to be axis-aligned — you can mirror across an arbitrary plane through the origin by passing any 3-vector as the normal.
- See [composition helpers](composition_helpers.md) for `mirror_copy`, `rotate_copy`, and `linear_copy` — variants that keep the original shape and add transformed copies.
