# Text on a surface — `add_text`

`.add_text(...)` puts raised or inset text on any flat face, cylindrical wall, or conical wall of a shape. After `add_text`, chaining more labels or calling `attach()` still works — the host's anchors are still there.

```python
from scadwright.primitives import cube
from scadwright.shapes import Tube
```

## The 30-second version

```python
plate = cube([40, 15, 2], center="xy")

plate.add_text(label="HELLO", relief=0.5, on="top", font_size=8)   # raised
plate.add_text(label="v1.0",  relief=-0.3, on="top", font_size=4)  # inset
```

`relief` is signed: positive raises text outward by that amount, negative cuts it that deep into the host. `on=` picks a face by name (any of `top`, `bottom`, `front`, `back`, `lside`, `rside`, the `+x`/`-x`/etc. axis-sign aliases, or any custom anchor declared on a Component).

## Where the text goes

Three ways to say where the text goes — pick the one that fits.

### Named face

The usual case. Pass `on=` as a face name:

```python
plate.add_text(label="HELLO", relief=0.5, on="top",   font_size=8)
plate.add_text(label="SIDE",  relief=0.3, on="rside", font_size=4)

# Custom Component anchor:
class Bracket(Component):
    equations = ["w, thk > 0"]
    badge = anchor(at="w/2, w/2, thk", normal=(0, 0, 1))
    def build(self):
        return cube([self.w, self.w, self.thk])

Bracket(w=20, thk=3).add_text(label="A1", relief=0.4, on="badge", font_size=4)
```

The text is centered on the face. Use `halign=` and `valign=` to align inside the face.

### Named face + offset

Use `at=(u, v)` (a 2-tuple, in mm) to nudge the text away from face center:

```python
plate.add_text(label="HI", relief=0.5, on="top",   font_size=4, at=(5, -3))    # 5mm right, 3mm forward
plate.add_text(label="HI", relief=0.5, on="rside", font_size=4, at=(2, 1))     # 2mm "right" (-Y), 1mm up (+Z)
```

The `(u, v)` axes are picked per face so they read intuitively when the face is viewed from outside:

| Face | u (right) | v (up) |
|---|---|---|
| `top` (`+z`) | +X | +Y |
| `bottom` (`-z`) | +X | -Y |
| `front` (`-y`) | +X | +Z |
| `back` (`+y`) | -X | +Z |
| `rside` (`+x`) | -Y | +Z |
| `lside` (`-x`) | +Y | +Z |

Custom Component anchors and `Anchor` objects with non-axis-aligned normals get a sensible `(u, v)` frame in the face's plane.

`at=(u, v)` doesn't apply to cylindrical or conical walls — those use `meridian=` and `at_z=`.

### Anchor object

Pass an explicit `Anchor` for full control of position and normal:

```python
from scadwright import Anchor

plate.add_text(
    label="X", relief=0.4, font_size=5,
    on=Anchor(position=(5, 5, 5), normal=(0, 0, 1)),
)
```

The `Anchor` must be planar.

### Ad-hoc `at=` + `normal=`

A shorthand for the Anchor-object form when you just want to drop coordinates inline:

```python
plate.add_text(
    label="X", relief=0.4, font_size=5,
    at=(5, 5, 5), normal=(0, 0, 1),
)
```

`at=` and `normal=` must come together; pass neither (and use `on=`) or both.

## Cylindrical walls

`cylinder()` and `Tube` have an `outer_wall` anchor. `add_text` wraps the label around the cylinder:

```python
from scadwright.primitives import cylinder
from scadwright.shapes import Tube

cyl = cylinder(h=20, r=10)
cyl.add_text(label="BRAND", relief=0.4, on="outer_wall", font_size=4)               # default meridian +X, mid-wall
cyl.add_text(label="ON",   relief=0.4, on="outer_wall", font_size=4, meridian="front")
cyl.add_text(label="OFF",  relief=0.4, on="outer_wall", font_size=4, meridian="back")
cyl.add_text(label="LOT",  relief=-0.3, on="outer_wall", font_size=3, at_z=-7)      # 7mm below mid-wall

# Numeric meridian: tick marks at arbitrary angles.
for a in (0, 30, 60, 90, 120, 150):
    cyl = cyl.add_text(label=f"{a}", relief=0.3, on="outer_wall", font_size=2,
                       meridian=a, at_z=8)
```

### `meridian=`

The angular position around the cylinder axis. Accepts either:

- A string: `"+x"` / `"+y"` / `"-x"` / `"-y"` (or the friendly aliases `"rside"` / `"back"` / `"lside"` / `"front"`). Default: `"+x"`.
- A number: degrees CCW from `+X`.

`meridian` applies on cylindrical, conical, and rim-arc placements.

### `at_z=`

Axial offset from the wall's midpoint, in mm. Default `0` (mid-wall). Positive moves the label up the axis, negative down.

### `halign=` on cylindrical surfaces

- `"center"` (default): label centered on the meridian.
- `"left"`: label starts at the meridian, extending CCW.
- `"right"`: label ends at the meridian, extending CW.

### Long labels

A label longer than the cylinder's circumference still works, but you get a warning that it wraps all the way around and glyphs will overlap.

## Disk rims (cylinder/Tube/Funnel top and bottom)

The flat top and bottom faces of `cylinder()`, `Tube`, and `Funnel` are circular rims. By default, text on a rim wraps along the circle:

```python
cyl = cylinder(h=10, r=15)
cyl.add_text(label="MAX 5L", relief=0.4, on="top", font_size=3)              # wraps along the rim (default)
cyl.add_text(label="MAX 5L", relief=0.4, on="top", font_size=3,
             text_curvature="flat")                                          # straight text across the disk

# Place the path closer to the rim's edge or its center:
cyl.add_text(label="EDGE",  relief=0.4, on="top", font_size=2, at_radial=14)
cyl.add_text(label="HUB",   relief=0.4, on="top", font_size=2, at_radial=4)

# Rotate the label around the rim center:
cyl.add_text(label="N",  relief=0.4, on="top", font_size=2, meridian="+y")   # north
cyl.add_text(label="SE", relief=0.4, on="top", font_size=2, meridian=-45)    # numeric degrees CCW
```

### `text_curvature=`

- `None` (default): arc on rim anchors, flat on flat-face anchors.
- `"arc"`: explicit arc — error if the anchor isn't a rim.
- `"flat"`: straight text — works on rims and flat faces; lets you opt out of arc-wrap on a cylinder rim.

Passing `text_curvature` on a cylindrical or conical side wall is an error: side walls always wrap.

### `at_radial=`

The radius of the circle the text follows, in mm. Defaults to leave a small font-sized margin inside the rim. Passing `at_radial` larger than the rim radius gives a warning — the text path runs outside the rim.

## Conical walls (Funnel and tapered cones)

`Funnel` and any tapered `cylinder()` (where `r1 != r2`) have a conical `outer_wall` anchor. `meridian=` and `at_z=` work the same as on cylindrical walls. One extra option, `text_orient=`, controls glyph orientation.

```python
from scadwright.shapes import Funnel
from scadwright.primitives import cylinder

f = Funnel(h=30, bot_od=20, top_od=40, thk=2)
f.add_text(label="0.5L", relief=0.4, on="outer_wall", font_size=4)              # glyphs vertical (default)
f.add_text(label="0.5L", relief=0.4, on="outer_wall", font_size=4,
           text_orient="slant")                                                  # tilted to follow the slope

cone = cylinder(h=30, r1=10, r2=4).add_text(
    label="MAX", relief=0.4, on="outer_wall", font_size=3, at_z=10,             # 10 mm above mid-wall
)
```

### `text_orient=`

- `"axial"` (default): glyphs stay vertical, parallel to the cone's axis. Most legible.
- `"slant"`: glyphs tilt with the cone's slope so they lie flat against the surface. Looks tilted, but follows the surface.

`text_orient` is also accepted on cylindrical walls (where it has no visible effect, since cylinders don't tilt).

### `at_z` on a cone

The cone's radius varies along its axis, so a label near the wide end of a funnel wraps less than the same label near the narrow end. If `at_z` puts the label past the cone's apex, that's an error. If the cone is very narrow at that height relative to `font_size`, you get a warning that glyphs may overlap.

## Inner walls (Tube and Funnel)

`Tube` and `Funnel` are hollow, so they have an inner surface as well as an outer one. Both have an `inner_wall` anchor:

```python
from scadwright.shapes import Tube, Funnel

# Tube — text on the inside surface, viewed from inside the hollow.
Tube(h=30, od=24, thk=2).add_text(
    label="LOT 7", relief=0.3, on="inner_wall", font_size=4, meridian="front",
)

# Funnel inner wall (conical), placed below mid-wall.
Funnel(h=30, bot_od=20, top_od=40, thk=2).add_text(
    label="0.5L", relief=0.3, on="inner_wall", font_size=4, at_z=-5,
)
```

`relief > 0` makes text protrude into the hollow (raised when viewed from inside). `relief < 0` cuts into the wall material from the inner surface. `meridian=`, `at_z=`, and `text_orient=` (conical only) work the same way as on the outer walls.

## Multi-line text

A `\n` in `label` splits the string into lines. Lines are stacked vertically on planar faces, axially on cylindrical/conical walls, and radially on rim arcs. Line 0 always ends up at the visual "top" — outermost ring on a rim, highest axial position on a wall, largest Y on a planar face.

```python
plate.add_text(label="LINE 1\nLINE 2",  relief=0.5, on="top", font_size=8)
plate.add_text(label="VERSION\n1.0",    relief=-0.3, on="top", font_size=4, valign="top")

cyl.add_text(label="BRAND\nMODEL X",    relief=0.4, on="outer_wall", font_size=4,
             meridian="front", line_spacing=1.4)

cyl.add_text(label="MAX\n5L",           relief=0.4, on="top", font_size=2)   # rim arc, two rings
```

### `line_spacing=`

Baseline-to-baseline distance, expressed as a multiple of `font_size`. Default `1.2`. Smaller values pack lines tighter; larger values spread them out.

### `valign=` with multi-line

For a multi-line label, `valign` positions the *whole block* on the face:

- `"center"` (default) — block center on the face center / wall mid / rim default radius.
- `"top"` — top of line 0 sits at the face anchor.
- `"bottom"` / `"baseline"` — bottom of the last line sits at the face anchor.

`halign=` is applied per-line as supplied.

### Empty lines

`"A\n\nB"` keeps the empty line's spacing slot (giving extra gap between A and B) but draws nothing in it. A label that's nothing but newlines is an error.

### Restrictions

- `direction="ttb"` or `"btt"` (column writing) is single-line only — combining with `\n` is an error.
- On cones, each line wraps at its own height; if any line falls past the cone tip you get an error pointing at which line.
- On rim arcs, the innermost line's circle must have positive radius. With many lines or a big `font_size`/`line_spacing`, this can fail; bump `at_radial` or shrink the spacing.

## Raised vs inset

- `relief > 0` raises text outward from the surface by `relief` mm.
- `relief < 0` cuts the text inward by `|relief|` mm. If `|relief|` is greater than the host's wall thickness, the cut punches all the way through.
- `relief = 0` isn't allowed.

## Chaining and `attach()` after `add_text`

`add_text` keeps the host's anchors intact. Multiple labels chain, and `attach()` after `add_text` still finds the host's named faces:

```python
# Chain two labels:
plate.add_text(label="A", relief=0.4, on="top",   font_size=4) \
     .add_text(label="B", relief=0.4, on="rside", font_size=4)

# Label, then attach:
labeled = bracket.add_text(label="A1", relief=0.3, on="top", font_size=3)
sensor = cube([8, 8, 4]).attach(labeled, face="badge")
```

If you wrap a labeled host in an explicit `union()` or `difference()`, the host's custom anchors do go away — at that point you've made a new combined shape.

## Overflow check

For text on a named face whose size scadwright can determine, you get a warning if the label would overflow the face. The estimate is conservative and font-agnostic, so it's a best-effort heads-up. Ad-hoc placements (no named face) skip the check.

## Other `text()` options

Anything `text()` takes passes through: `font`, `halign`, `valign`, `spacing`, `direction`, `language`, `script`, plus `fn`/`fa`/`fs` for resolution. For example:

```python
plate.add_text(
    label="brand",
    relief=0.4,
    on="top",
    font_size=6,
    font="DejaVu Sans:style=Bold",
    halign="left",
    valign="bottom",
)
```

## Argument reference

| Argument | Required | Meaning |
|---|---|---|
| `label` | yes | The string to render. |
| `relief` | yes | Signed depth in mm. Positive raised, negative inset. |
| `font_size` | yes | 2D text size in mm. |
| `on` | one of the four placement choices | Face name (str) or `Anchor` instance. |
| `at` | with `on=` (offset) or with `normal=` (ad-hoc) | 2-tuple `(u, v)` in-face offset (mm) when paired with `on=`; or 3-tuple `(x, y, z)` ad-hoc position when paired with `normal=`. |
| `normal` | with `at=` (ad-hoc only) | 3-tuple direction; combine with `at=`. |
| `meridian` | cylindrical/conical/rim arc | String name or numeric degrees CCW. Default `"+x"`. |
| `at_z` | cylindrical/conical | Axial offset from wall midpoint. Default `0`. |
| `at_radial` | rim arc only | Radius of the text path circle. Default leaves a font-size margin inside the rim. |
| `text_curvature` | planar only | `None` (default — arc on rims, flat elsewhere), `"arc"`, or `"flat"`. |
| `text_orient` | conical only (ignored on cylindrical) | `"axial"` (default) or `"slant"`. |
| `line_spacing` | multi-line only | Baseline-to-baseline distance as a multiple of `font_size`. Default `1.2`. |
| `font` | no | Font family/style. |
| `halign` | no | `"left" \| "center" \| "right"` (default `"center"`). |
| `valign` | no | `"top" \| "center" \| "baseline" \| "bottom"` (default `"center"`). |
| `spacing` | no | Glyph-advance multiplier (default `1.0`). |
| `direction` | no | `"ltr" \| "rtl" \| "ttb" \| "btt"`. |
| `language`, `script` | no | Same as on the 2D `text()` factory. |
| `fn`, `fa`, `fs` | no | Resolution overrides for the text rasterization. |

## Things that fail

- An unrecognized face name in `on=`.
- Mixing `on=` with `at=`+`normal=` (those are different placement choices).
- `relief = 0`.
- `meridian` or `at_z` on a flat planar face — those are for cylindrical and conical walls.
- `text_curvature="arc"` on a face that isn't a rim.
- `text_curvature` on a cylindrical or conical side wall — those always wrap.
- `at_z` (or a `line_spacing` for multi-line) that puts a glyph past the cone's apex.
</content>
</invoke>