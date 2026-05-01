# Coming from OpenSCAD

If you know OpenSCAD and you're looking for a feature by name, this page maps the common ones to their SCADwright equivalent. SCADwright deliberately doesn't implement SCAD's language-level features (loops, conditionals, let-bindings, functions, modules) at the emit layer — you get those from Python instead, and the result is usually shorter and more expressive.

Not exhaustive; covers what SCAD users commonly stumble over.

## Side-by-side: migrating a script

Here's a small OpenSCAD file and its SCADwright equivalent, line by line:

**OpenSCAD:**
```scad
// plate with two holes and rounded corners
$fn = 32;
corner_r = 3;
plate_w = 80;
plate_l = 40;
thk = 5;
hole_d = 6;
hole_spacing = 40;

module plate() {
    difference() {
        minkowski() {
            cube([plate_w - 2*corner_r,
                  plate_l - 2*corner_r, thk],
                 center=true);
            cylinder(r=corner_r, h=0.01);
        }
        for (dx = [-1, 1])
            translate([dx * hole_spacing/2, 0, -1])
                cylinder(h=thk+2, d=hole_d);
    }
}

plate();
```

**SCADwright:**
```python
from scadwright import render
from scadwright.boolops import difference
from scadwright.primitives import cylinder
from scadwright.shapes import rounded_rect

plate_w, plate_l, thk = 80, 40, 5
hole_d, hole_spacing = 6, 40

body = rounded_rect(plate_w, plate_l, r=3, fn=32).linear_extrude(height=thk)
hole = cylinder(h=thk + 2, d=hole_d, fn=32).down(1)

part = difference(
    body,
    hole.left(hole_spacing / 2),
    hole.right(hole_spacing / 2),
)

render(part, "plate.scad")
```

The shapes and operations are the same — `difference`, `cylinder`, `minkowski` (via `rounded_rect`). The differences: Python variables instead of SCAD globals, `fn=32` passed to the primitives (or use `with resolution(fn=32):`), and `render()` at the end to write the output file. No `module` declaration needed for a one-off part.

## Control flow

### `for` loop

SCAD:

```scad
for (i = [0:9])
    translate([i*10, 0, 0])
        cube(5);
```

SCADwright — use a Python for-loop plus `union`, a list comprehension, or the `array` helper:

```python
from scadwright.boolops import union
from scadwright.primitives import cube

# Python loop:
parts = []
for i in range(10):
    parts.append(cube(5).translate([i*10, 0, 0]))
row = union(*parts)

# List comprehension:
row = union(*[cube(5).translate([i*10, 0, 0]) for i in range(10)])

# Simpler when the spacing is uniform along an axis:
row = cube(5).array(count=10, spacing=10, axis="x")
```

### `if` / `else`

SCAD:

```scad
if (mode == "solid") cube(10);
else                 sphere(r=5);
```

SCADwright — inside a `Component.build()`, use plain Python:

```python
class Widget(Component):
    equations = "mode:str in ('solid', 'round')"

    def build(self):
        if self.mode == "solid":
            return cube(10)
        return sphere(r=5)
```

### List comprehension `[for (...) ...]`

SCAD:

```scad
points = [for (i=[0:35]) [10*cos(i*10), 10*sin(i*10)]];
polygon(points);
```

SCADwright — Python list comprehension:

```python
from scadwright import math as scmath
from scadwright.primitives import polygon

points = [(10*scmath.cos(i*10), 10*scmath.sin(i*10)) for i in range(36)]
shape = polygon(points=points)
```

### `let` (local variables)

SCAD:

```scad
let (r = d/2, h = sqrt(3) * r) ...
```

SCADwright — just Python variable assignment:

```python
r = d / 2
h = scmath.sqrt(3) * r
```

### Ternary `? :`

SCAD:

```scad
size = large ? 20 : 10;
```

SCADwright — Python conditional expression:

```python
size = 20 if large else 10
```

### `each` keyword

SCAD uses `each` to unpack lists in comprehensions. Python's `*` unpacking does the same job in every context SCADwright cares about:

```python
extras = [cube(1), cube(2)]
union(a, b, *extras)                      # unpack into variadic args
```

## Modules and functions

### User-defined modules

SCAD:

```scad
module bracket(width, height) {
    difference() {
        cube([width, height, 5]);
        cylinder(h=10, r=2, $fn=32);
    }
}

bracket(40, 20);
```

SCADwright — [Components](components.md):

```python
from scadwright import Component
from scadwright.boolops import difference
from scadwright.primitives import cube, cylinder

class Bracket(Component):
    equations = "width, height > 0"

    def build(self):
        return difference(
            cube([self.width, self.height, 5]),
            cylinder(h=10, r=2, fn=32),
        )

Bracket(width=40, height=20)
```

Components beat SCAD modules in two ways: you can read computed attributes (`bracket.mount_offset`) without rendering, and the class can carry an `equations` block of relationships SCADwright fills in for you and rules it checks when you make the part. See [Components](components.md).

### User-defined functions

SCAD's function syntax limits you to expressions. Python functions have no such restriction — write any Python function:

```python
def hex_grid_points(cols, rows, spacing):
    return [
        (col*spacing + (0.5*spacing if row % 2 else 0), row*spacing*0.866)
        for row in range(rows) for col in range(cols)
    ]
```

### `children()` and `$children`

SCAD's `children()` passes the caller-provided subtree into a module. SCADwright's equivalent is either:

1. **Plain Python function arguments** — accept the shape as a parameter:

    ```python
    def chamfered(shape, *, depth):
        return minkowski(shape, sphere(r=depth, fn=8))
    ```

2. **[Custom transforms](custom_transforms.md)** — register a function that becomes a method on every shape:

    ```python
    @transform("chamfer_top")
    def chamfer_top(node, *, depth):
        return minkowski(node, sphere(r=depth, fn=8))

    cube([10, 10, 5]).chamfer_top(depth=1)
    ```

SCAD's `$children` (number of children passed to a module) doesn't apply — in SCADwright, you receive the actual children as Python arguments and can `len()` them if needed.

## Type tests

SCAD has `is_undef`, `is_bool`, `is_num`, `is_string`, `is_list`. In Python:

```python
x is None                    # is_undef
isinstance(x, bool)          # is_bool
isinstance(x, (int, float))  # is_num — but see note below
isinstance(x, str)           # is_string
isinstance(x, (list, tuple)) # is_list
```

**Note:** Python makes `bool` a subclass of `int`, so `isinstance(True, int)` is `True`. SCADwright's own validators reject booleans where numbers are expected. If you're writing your own type test, check `isinstance(x, bool)` first.

## Strings and lists

SCAD provides `str()`, `concat()`, `chr()`, `ord()`, `len()`, `search()`. Python covers all of them and more:

```python
str(42)                      # str()
a + b                        # concat (for lists)
chr(65)                      # chr
ord("A")                     # ord
len(x)                       # len
"substring" in text          # search (substring check)
needle in haystack_list      # search (membership)
haystack_list.index(needle)  # search (find position)
```

## `undef`, `PI`, constants

```python
x = None                     # undef
import math
math.pi                      # SCAD's PI — use Python's stdlib constant
```

## `assert`

SCAD's `assert(condition, "message")` is a render-time check. SCADwright offers three layers:

```python
# 1. Rules in `equations`: bounds and inequalities, runs at construction.
equations = """
    width > 0
    width > thk
"""

# 2. Rules in `equations` with arbitrary Python: same block, any boolean expression.
equations = """
    len(size) = 3
    all(e.dia <= throat for e in elements)
"""

# 3. Geometry assertions: runs at bbox time, useful for assemblies.
from scadwright.asserts import assert_fits_in
assert_fits_in(my_part, ((0, 0, 0), (200, 200, 50)))
```

## Special variables

### Resolution (`$fn`, `$fa`, `$fs`)

Fully supported. Pass as kwargs, or set via the `resolution()` context, or declare as Component class/instance attributes. See [Resolution](resolution.md).

### Preview modifiers (`#`, `%`, `*`, `!`)

Fully supported as chained methods: `.highlight()`, `.background()`, `.disable()`, `.only()`. See [Preview modifiers](transformations.md#preview-modifiers).

### `$preview`

OpenSCAD sets `$preview = true` during F5 preview and `false` during F6 render. SCADwright doesn't have a direct equivalent — the closest concept is [variants](variants.md):

```python
from scadwright.design import Design, run, variant

class WidgetProject(Design):
    widget = Widget()

    @variant(fn=48, default=True)
    def print(self):
        return union(self.widget, supports())

    @variant(fn=24)
    def preview(self):
        return self.widget.highlight()

if __name__ == "__main__":
    run()

# CLI: scadwright build widget.py --variant=preview
```

Variants are user-controlled (you choose when to activate them) rather than OpenSCAD-controlled (F5 vs F6 automatically). For most use cases where you'd reach for `$preview` in SCAD, variants do the job more explicitly.

### Animation (`$t`) and viewpoint (`$vpr`, `$vpt`, `$vpd`, `$vpf`)

Fully supported via `scadwright.animation`. See [Animation and viewpoints](animation.md).

`t()` returns a symbolic expression standing for `$t`. Arithmetic builds an expression tree that emits as SCAD source:

```python
from scadwright.animation import t
from scadwright.primitives import cube

cube(10).rotate([0, 0, t() * 360])    # full turn over the animation
```

`viewpoint()` emits `$vpr`/`$vpt`/`$vpd`/`$vpf` at the top of the file. Can also be set per-variant via `@variant(rotation=..., distance=...)` kwargs, or from the CLI with `--vpr`/`--vpd` flags.

### `$children`

See [`children()` and `$children`](#children-and-children) above.

## `rands`, `lookup`, `search`

SCAD's `rands` seeds a list of random numbers; `lookup` does linear interpolation between table entries; `search` does substring/list lookup. Use Python's stdlib:

```python
import random
random.seed(42)
values = [random.uniform(min_v, max_v) for _ in range(count)]

# Lookup / interpolation: numpy.interp or a small helper.
# search: Python `in`, `str.find`, `list.index`, or `re`.
```

## Including other SCAD files

SCAD's `use <file>` and `include <file>` are supported as emit-time keyword arguments on `render` / `emit_str` / `emit`. See [Integrating legacy SCAD code](scad_interop.md) — this is the rare case; SCADwright's default assumption is that shared code lives in Python modules, not SCAD files.

## BOSL2's `attach()` system

If you're coming from BOSL2, you may be used to its `attach()` / `anchor()` system for positioning parts relative to each other. SCADwright has a similar but lighter system:

- Every shape gets six bbox-derived anchors (`top`, `bottom`, `front`, `back`, `lside`, `rside`) automatically.
- `peg.attach(plate)` puts the peg's bottom on the plate's top (the most common stacking operation).
- Components declare custom anchors at class scope: `mount = anchor(at="w/2, w/2, thk", normal=(0,0,1))`.
- `orient=True` adds rotation so anchor normals oppose each other (faces touching).

Unlike BOSL2, anchors don't appear on every primitive as keyword arguments, and they don't shift the origin. SCADwright keeps `center=` for origin control and `attach()` for positioning — two separate concepts.

See [Anchors and attachment](anchors.md) for the full reference.

SCADwright also automates epsilon overlap — `through(parent)` extends cutters through coincident faces, and `attach(fuse=True)` overlaps joints. See [Eliminating epsilon overlap](auto-eps_fuse_and_through.md).

## Text on a 3D shape

In OpenSCAD, putting raised or inset text on a part takes several steps: 2D `text(...)`, `linear_extrude`, position, then union or difference. SCADwright does it in one call:

```python
plate.add_text(label="HELLO", relief=0.5, on="top", font_size=8)   # raised
plate.add_text(label="v1.0",  relief=-0.3, on="top", font_size=4)  # inset
```

`relief` is signed: positive raises, negative cuts in. `on=` picks any face by name. See [`add_text()`](add_text.md) for the full reference.

## Features SCADwright doesn't have (and probably won't)

A short list of things that SCAD users occasionally ask about:

- **Assignment-in-expression.** Python doesn't have it (`:=` walrus notwithstanding); write two lines.
- **SCAD's `?:` short-circuit for building large comprehensions.** Use Python generator expressions and `filter(...)`.

If you run into something not covered here, it probably has a clean Python equivalent — or it's a legitimate gap. Open an issue with the use case.
