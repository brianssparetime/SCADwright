# Quick Start / Organizing a project

scadwright projects span a range from "a few lines of primitives" to "multi-part assembly with a dozen measurements." You don't need to learn the full feature set up front -- start simple, and layer on structure only when the project calls for it.

For worked examples at each level of complexity, see [examples/](../examples/README.md).

## Graceful scaling of complexity

The same part -- a plate with two holes -- written three ways, each building on the last. This shows how scadwright features layer on without requiring you to rewrite what you already have.

### Stage 1: Flat script

A few primitives combined with booleans. Reads like OpenSCAD. No classes, no framework. This is all you need for a quick one-off part.

```python
from scadwright import render
from scadwright.boolops import difference
from scadwright.primitives import cube, cylinder

plate = cube([80, 40, 5], center="xy")
hole = cylinder(h=7, d=6, fn=32).down(1)

part = difference(
    plate,
    hole.left(20),
    hole.right(20),
)

render(part, "plate.scad")
```

Every measurement appears once, at its point of use. Zero ceremony.

### Stage 2: Wrap in a Component

When the part has enough parameters that you want to name them, or you need a caller to read dimensions off the part, wrap it in a [Component](components.md). Variables in equations are auto-declared as float params; non-float types use `Param(...)` directly.

```python
from scadwright import Component, Param, render
from scadwright.boolops import difference
from scadwright.primitives import cube, cylinder

class Plate(Component):
    equations = [
        "width, length, thk, hole_d, hole_spacing > 0",
    ]

    def build(self):
        body = cube([self.width, self.length, self.thk], center="xy")
        hole = cylinder(h=self.thk + 2, d=self.hole_d).down(1)
        return difference(
            body,
            hole.left(self.hole_spacing / 2),
            hole.right(self.hole_spacing / 2),
        )

plate = Plate(width=80, length=40, thk=5, hole_d=6, hole_spacing=40)
render(plate, "plate.scad")
```

The part is now parametric. A caller can read `plate.width` or `plate.hole_spacing` without rendering anything. Change one measurement and re-run.

When the project has enough measurements that the inline kwarg list is getting long, move them to a concrete subclass -- a thin class that fills in values as plain class attributes:

```python
class MyPlate(Plate):
    width = 80
    length = 40
    thk = 5
    hole_d = 6
    hole_spacing = 40

plate = MyPlate()
render(plate, "plate.scad")
```

The subclass reads like a parts list. Every measurement appears once, as a plain `name = value` line. No `self.x = self.x` repetition, no decorator. The generic `Plate` stays portable; the concrete `MyPlate` holds the project-specific numbers.

### Stage 3: Add a Design with variants

When the project has multiple parts or needs different render arrangements (one for printing, one for display), add a [Design](components.md#multiple-variants-the-design-class) class. Parts are instantiated once and shared across variants:

```python
from scadwright.boolops import union
from scadwright.design import Design, run, variant

class MyPlate(Plate):
    width = 80
    length = 40
    thk = 5
    hole_d = 6
    hole_spacing = 40

class PlateProject(Design):
    plate = MyPlate()

    @variant(fn=48, default=True)
    def print(self):
        return self.plate

    @variant(fn=48)
    def display(self):
        # show the plate with stand-in bolts
        bolt = cylinder(h=12, d=5.8).color("silver")
        return union(
            self.plate,
            bolt.left(self.plate.hole_spacing / 2),
            bolt.right(self.plate.hole_spacing / 2),
        )

if __name__ == "__main__":
    run()
```

```
scadwright build plate.py                    # default (print) variant
scadwright build plate.py --variant=display  # display variant
```

Each `@variant` method returns the scene for one arrangement. `fn=48` on the decorator sets resolution for all primitives built inside that variant.

Note the `if __name__ == "__main__": run()` at the bottom -- this replaces the `render(part, "file.scad")` call from Stages 1 and 2. `run()` discovers the Design class, picks the right variant (from `--variant` or the `default=True` one), renders it, and writes the output file. You don't call `render()` yourself when using a Design.

The transition from Stage 1 to Stage 3 is additive -- you wrap existing code in a class, then wrap that in a Design. Nothing gets rewritten; structure layers on.

## Concrete subclasses

A concrete subclass is where your project-specific measurements live:

- **Subclass the generic Component.** `class MyPlate(Plate):`.
- **Fill in each measurement as a plain class attribute.** `width = 80`.
- **No `__init__`, no `super()` call.** scadwright generates the `__init__` for you; class attributes override the equation-declared Params.
- **Equations still work.** A concrete `Tube` subclass with `h = 10`, `id = 8`, `thk = 1` still lets the solver compute `od`.

> **Never bake project-specific defaults into a generic Component.** If a value is specific to one design, it belongs as a class attribute on a concrete subclass, not as `Param(..., default=<that value>)` on the generic class. Either the value is genuinely tunable (a Param with no default or a geometrically neutral default like `corner_r=0`) or it's a fixed design choice (class attribute on the concrete subclass).

## Splitting across files

A single file with clear zones (REUSABLE / CONCRETE / DESIGN) works well for most projects. Consider splitting when you have more than three Components and the single file becomes hard to navigate, or when distinct subassemblies don't share internal state.

**Layout:**
```
my_project/
    shapes.py           # generic Components (Plate, Bracket, etc.)
    parts.py            # concrete subclasses (MyPlate, MyBracket)
    main.py             # Design + @variant + run()
```

Generic Components import only from scadwright and the standard library. Concrete subclasses import their generic base and fill in values. The Design file imports concrete subclasses and composes the scene. `run()` goes in exactly one file -- the one you pass to `scadwright build`.

## Next steps

Once you're comfortable with the three stages above, these features are worth learning next:

- [Anchors and attachment](anchors.md) -- position parts relative to each other without manual coordinate math (`peg.attach(plate)`)
- [Eliminating epsilon overlap](auto-eps_fuse_and_through.md) -- `through(parent)` for cutters and `attach(fuse=True)` for joints, replacing manual EPS constants
- [Custom transforms](custom_transforms.md) -- add your own verbs to the language (`.chamfer_top(depth=1)` on any shape)
- [Shape library](shapes/README.md) -- tubes, gears, fasteners, and dozens more pre-built shapes
- [Variants](variants.md) -- `@variant` options, `run()` dispatch rules, and multi-part assembly layouts
- [Style guide](style-guide.md) -- coding conventions for writing clean, idiomatic scadwright
