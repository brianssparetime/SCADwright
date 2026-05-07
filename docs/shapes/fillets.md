# Fillets, chamfers, and hole profiles

Edge-rounding, edge-beveling, and screw-hole profiles.

```python
from scadwright.shapes import (
    ChamferedBox, FilletMask, ChamferMask,
    Countersink, Counterbore,
)
```

## `ChamferedBox(size, fillet= or chamfer=)`

Box with all edges rounded or beveled. Centered on the origin. Specify exactly one of `fillet` or `chamfer`.

```python
ChamferedBox(size=(30, 20, 10), fillet=2)     # rounded edges
ChamferedBox(size=(30, 20, 10), chamfer=2)    # 45-degree bevels
```

![Chamfered box](images/chamfered-box.png)

*`ChamferedBox(size=(30, 20, 10), fillet=2)` — box with every edge rolled to a 2 mm radius.*

## Shorthand: `.fillet()` and `.chamfer()` on `cube` and `cylinder`

For axis-aligned cube edges and cylinder rims, `.fillet(edges, r=...)` and `.chamfer(edges, size=...)` are sugar over `FilletMask` / `ChamferMask` / a custom `rotate_extrude` profile. Replaces the manual three-line pattern of constructing a mask, translating it to the edge, and subtracting.

```python
# Cube — single edge, list of edges, or group selector:
cube([10, 20, 30]).fillet("top_front", r=2)
cube([10, 20, 30]).fillet(["top_front", "top_back"], r=2)
cube([10, 20, 30]).fillet("top", r=2)              # all 4 top edges
cube([10, 20, 30]).fillet("vertical", r=2)         # all 4 z-axis edges
cube([10, 20, 30]).chamfer("top", size=1)          # 45° bevel instead

# Cylinder rim (non-cone only):
cylinder(h=10, r=5).fillet("top_rim", r=1)
cylinder(h=10, r=5).chamfer("bottom_rim", size=1)

# Chains naturally:
cube([10, 20, 30]).fillet("top", r=2).up(5).red()
```

The 12 cube edges are named by face-pair (same vocabulary as the framework's anchor faces): `top_front`, `top_back`, `top_lside`, `top_rside`, `bottom_front`, `bottom_back`, `bottom_lside`, `bottom_rside`, `front_lside`, `front_rside`, `back_lside`, `back_rside`. Group selectors: `"top"` / `"bottom"` (4 edges of that face) and `"vertical"` (4 z-axis edges).

This is sugar — scoped to the cases where edge identity is well-defined. Out of scope: edges of composed shapes (`union`/`difference` results), rotated primitives (`cube(...).rotate(...)` no longer has the method by design), cone cylinders (`r1 != r2`), and inside-corner concave fillets. For those, use `FilletMask` / `ChamferMask` directly.

Result preserves `tight_bbox()` — a fillet only carves inward, so a filleted cube/cylinder is interchangeable with the original in `pack_on_bed`, `assert_fits_in`, and other tight-bbox-consuming helpers.

## `FilletMask(r, length, axis="z")`

Quarter-cylinder fillet piece along an axis-aligned edge. Same geometry, two uses:

**Round an outside (convex) edge** — subtract from the parent:

```python
mask = FilletMask(r=3, length=20)
part = difference(box, mask.translate([box_x, box_y, 0]))
```

**Fill an inside (concave) corner** — union into the parent to smooth a re-entrant corner between two walls:

```python
bracket_inner_corner = FilletMask(r=2, length=40)
bracket = union(wall_a, wall_b, bracket_inner_corner.translate([0, 0, 0]))
```

`axis` is the edge direction: `"x"`, `"y"`, or `"z"`.

## `ChamferMask(size, length, axis="z")`

Subtractable 45-degree chamfer mask. Same usage as FilletMask.

```python
mask = ChamferMask(size=2, length=20, axis="z")
part = difference(box, mask)
```

## `Countersink(shaft_d, head_d, head_depth, shaft_depth)`

Conical countersink profile for flat-head screws. Shaft at z=0, cone on top. Use `.through(parent)` for clean cuts.

```python
hole = Countersink(shaft_d=3.2, head_d=6.3, head_depth=1.8, shaft_depth=10)
part = difference(plate, hole.through(plate))
```

## `Counterbore(shaft_d, head_d, head_depth, shaft_depth)`

Stepped cylinder for socket-head screws. Shaft at z=0, wider bore on top.

```python
hole = Counterbore(shaft_d=3.2, head_d=5.5, head_depth=3, shaft_depth=10)
part = difference(plate, hole.through(plate))
```

![Counterbore](images/counterbore.png)

*`Counterbore(shaft_d=4, head_d=7, head_depth=4, shaft_depth=12)` — the solid mask; subtract it from a part for a socket-head pocket.*

## `counterbore_for_screw(size, shaft_depth, head="socket")` and `countersink_for_screw(...)`

Factories that build a `Counterbore` / `Countersink` sized for a standard ISO metric screw. Pulls `clearance_d`, `head_d`, and `head_h` from the [ScrewSpec](fasteners.md) for the given size.

```python
from scadwright.shapes import counterbore_for_screw, countersink_for_screw

pocket = counterbore_for_screw("M3", shaft_depth=10)
sink = countersink_for_screw("M5", shaft_depth=20, head="button")
part = difference(plate, pocket.through(plate))
```

## `FilletRing(id, od, base_angle)`

Right-triangle-cross-section ring for flange fillets. `slant="outwards"` (default) slopes the outer wall; `"inwards"` slopes the inner wall.

```python
FilletRing(id=10, od=20, base_angle=30)
FilletRing(id=10, od=20, base_angle=30, slant="inwards")
```

Both variants have the same height and slope for matched (id, od, base_angle), so they mate when one part's outer fillet meets another's inner fillet.

### See also

- [Fasteners](fasteners.md) -- bolts and nuts (Countersink/Counterbore pair with clearance holes for screw assemblies)
