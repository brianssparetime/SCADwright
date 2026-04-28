# Print-oriented shapes

Infill panels, vent slots, and print-process helpers. Mechanical joints (tabs, snaps, locators) live in their own page — see [Joints](joints.md). Text decoration is a chained method on any shape: see [`add_text()`](../add_text.md).

```python
from scadwright.shapes import (
    HoneycombPanel, GridPanel, TriGridPanel,
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

Text decoration is a chained method on any host shape, not a dedicated Component. Use `.add_text(label=..., relief=..., font_size=..., on=...)`:

```python
plate = cube([40, 15, 2], center="xy")
plate.add_text(label="HELLO", relief=0.5, on="top", font_size=8)   # raised
plate.add_text(label="v1.0",  relief=-0.3, on="top", font_size=4)  # inset
```

`relief` is signed: positive raises text outward, negative cuts it into the host. See the [`add_text()` page](../add_text.md) for cylindrical and conical walls, rim arcs, multi-line text, and the rest.

## `VentSlots(width, height, thk, slot_width, slot_height, slot_count)`

Rectangular panel with evenly-spaced horizontal vent slots.

```python
VentSlots(width=30, height=20, thk=2, slot_width=20, slot_height=1.5, slot_count=5)
```

## Print aids

Shapes that compensate for FDM print-process artifacts.

### `PolyHole(d, h, sides)`

Laird-compensated polygonal hole cutter. OpenSCAD renders circles as n-gons, so a plain `cylinder(d=d)` used as a hole prints to an *inscribed* diameter smaller than `d`. `PolyHole` scales the polygon's circumradius so the inscribed circle matches the requested `d` exactly — the standard FDM drilled-fit fix. `sides` pins the cutter's `$fn` locally so a higher ambient resolution doesn't undo the compensation. Typical FDM values are 6 or 8.

```python
part = difference(plate, PolyHole(d=6, h=10, sides=8).through(plate))
```

`self.d` is the as-printed (inscribed) diameter; `self.circumradius` is the internal polygon measure.
