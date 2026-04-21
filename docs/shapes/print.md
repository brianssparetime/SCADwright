# Print-oriented shapes

Infill panels, text plates, vent slots, and print-process helpers. Mechanical joints (tabs, snaps, locators) live in their own page — see [Joints](joints.md).

```python
from scadwright.shapes import (
    HoneycombPanel, GridPanel, TriGridPanel,
    TextPlate, EmbossedLabel,
    VentSlots,
    PolyHole,
)
```

## Infill panels

### `HoneycombPanel(size, cell_size, wall_thk)`

Hex grid of holes in a rectangular slab. `size` is `(x, y, z)`.

```python
HoneycombPanel(size=(80, 60, 3), cell_size=8, wall_thk=1)
```

![Honeycomb panel](images/honeycomb-panel.png)

*`HoneycombPanel(size=(80, 60, 3), cell_size=8, wall_thk=1)` — hex-grid pierced slab for ventilation or weight reduction.*

### `GridPanel(size, cell_size, wall_thk)`

Square grid of holes.

```python
GridPanel(size=(60, 40, 2), cell_size=5, wall_thk=1)
```

### `TriGridPanel(size, cell_size, wall_thk)`

Triangular grid of holes.

```python
TriGridPanel(size=(60, 40, 2), cell_size=6, wall_thk=1)
```

## Text

### `TextPlate(label, plate_w, plate_h, plate_thk, depth, font_size)`

Plate with raised text on the surface.

```python
TextPlate(label="HELLO", plate_w=40, plate_h=15, plate_thk=2, depth=0.5, font_size=8)
```

![Text plate](images/text-plate.png)

*`TextPlate(label="HELLO", plate_w=40, plate_h=15, plate_thk=2, depth=0.8, font_size=8)` — raised text on a flat plate, useful for labels and tags.*

### `EmbossedLabel(label, plate_w, plate_h, plate_thk, depth, font_size)`

Plate with engraved (recessed) text.

```python
EmbossedLabel(label="v1.0", plate_w=30, plate_h=10, plate_thk=2, depth=0.3, font_size=6)
```

Both accept an optional `font` parameter (default `"Liberation Sans"`).

## `VentSlots(width, height, thk, slot_width, slot_height, slot_count)`

Rectangular panel with evenly-spaced horizontal vent slots.

```python
VentSlots(width=30, height=20, thk=2, slot_width=20, slot_height=1.5, slot_count=5)
```

## Print aids

Shapes that compensate for FDM print-process artifacts.

### `PolyHole(d, h, sides=8)`

Laird-compensated polygonal hole cutter. OpenSCAD renders circles as n-gons, so a plain `cylinder(d=d)` used as a hole prints to an *inscribed* diameter smaller than `d`. `PolyHole` scales the polygon's circumradius so the inscribed circle matches the requested `d` exactly — the standard FDM drilled-fit fix. `sides` pins the cutter's `$fn` locally so a higher ambient resolution doesn't undo the compensation.

```python
part = difference(plate, PolyHole(d=6, h=10).through(plate))
```

Publishes `circumradius`.
