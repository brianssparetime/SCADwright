# 2D primitives

2D shapes that lie flat in the XY plane. By themselves, they're not very useful — you'd typically pass them to [`linear_extrude` or `rotate_extrude`](extrusions.md) to give them a third dimension.

Imports used on this page:

```python
from scadwright.primitives import square, circle, polygon, text
```

## `square`

Creates a rectangle in the XY plane.

```python
square([10, 20])                # 10 wide, 20 tall
square(5)                       # square with sides 5
square([10, 20], center=True)   # centered on the origin
square([10, 20], center="x")    # centered on X only
```

**Parameters:**

- `size` — a single number (square) or `[x, y]` pair.
- `center` — same idea as `cube`'s `center`. Pass a bool, an axis-letter string (`"x"`, `"y"`, `"xy"`), or a 2-element list of bools. By default the square sits in the +X, +Y quadrant.

## `circle`

Creates a disc in the XY plane, centered on the origin.

```python
circle(r=5)
circle(d=10)
circle(r=5, fn=64)              # smoother
```

**Parameters:**

- `r` — radius, or `d` — diameter. Pass exactly one; passing both raises `ValidationError`.
- `fn` / `fa` / `fs` — facet controls (smoothness). See [Resolution](resolution.md).

## `polygon`

Defines a 2D shape from a list of points (and optionally inner holes).

```python
polygon(points=[[0, 0], [10, 0], [10, 5], [0, 5]])

# A square with a square hole:
polygon(
    points=[
        [0, 0], [10, 0], [10, 10], [0, 10],   # outer
        [3, 3], [7, 3], [7, 7], [3, 7],       # inner (the hole)
    ],
    paths=[
        [0, 1, 2, 3],
        [4, 5, 6, 7],
    ],
)
```

**Parameters:**

- `points` — list of `[x, y]` coordinates.
- `paths` — optional. When omitted, all points form a single closed shape in declaration order. When given, each path lists indices into `points`; the first path is the outer boundary, the rest are holes.
- `convexity` — optional render hint; you usually don't need it.

SCADwright checks that every index in `paths` refers to a real point.

## `text`

Produces the 2D outline of a text string. Typically you'll extrude it into 3D with [`linear_extrude`](extrusions.md) to get an embossed or engraved label.

```python
text("Hello")
text("Label", size=5, halign="center", valign="center")
text("A", font="Liberation Sans", fn=32)

# Embossed label on a plate:
plate = cube([40, 20, 2])
label = text("MODEL", size=6, halign="center", valign="center").linear_extrude(height=1).translate([20, 10, 2])
part = union(plate, label)
```

**Parameters:**

- `text` — the string to render.
- `size` — nominal glyph height. Default 10.
- `font` — font family name, as OpenSCAD understands it (e.g. `"DejaVu Sans:style=Bold"`); not a file path. If omitted, OpenSCAD picks its default (Liberation Sans). scadwright resolves the name to a file via fontconfig for the bbox; see the bbox note below.
- `halign` — horizontal alignment: `"left"` (default), `"center"`, `"right"`.
- `valign` — vertical alignment: `"baseline"` (default), `"top"`, `"center"`, `"bottom"`.
- `spacing` — character spacing multiplier. Default 1.
- `direction` — `"ltr"` (default), `"rtl"`, `"ttb"`, `"btt"`.
- `language`, `script` — passed through to OpenSCAD for text shaping.
- `bbox` — optional `((min_x, min_y, 0), (max_x, max_y, 0))` hint. Overrides the built-in bbox. SCADwright-side metadata only; never emitted to SCAD.
- `fn` / `fa` / `fs` — facet controls for curved outlines.

**Bounding box reflects the real glyphs when the font is available.** With `freetype-py` installed (the `scadwright[curved-text]` extra) and the font resolvable, the bbox is read from the actual glyph outlines — so all-caps text with no descenders and lowercase text with no ascenders get correctly placed, content-aware extents (the box is expanded a few percent about the content center so it stays a conservative envelope of OpenSCAD's render). Without it, the bbox falls back to a conservative font-agnostic estimate (`0.6 * size * spacing` per character, `size` for height). Either way, for assembly checks against a specific font you can pin exact extents with a `bbox=` hint:

```python
# Known extents for this font at this size:
label = text("MODEL", size=6, font="Liberation Mono",
             bbox=((0, 0, 0), (34, 6, 0)))
```

---

### Advanced notes

- The 2D plane is treated as 3D with z=0 throughout the rest of the library. A 2D shape's bounding box has zero Z extent.
- `polygon` doesn't check winding direction; OpenSCAD handles that at render time.

### See also

- [2D profiles](shapes/profiles_2d.md) -- `rounded_rect`, `regular_polygon`, `Sector`, `Arc`, `RoundedSlot` built on these primitives
