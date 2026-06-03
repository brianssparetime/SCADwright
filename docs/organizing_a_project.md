# Quick Start / Organizing a project

SCADwright projects span a range from "a few lines of primitives" to "multi-part assembly with a dozen measurements." You don't need to learn the full feature set up front: start simple, and layer on structure only when the project calls for it.

For examples at each level of complexity, see [examples/](../examples/README.md).

## Graceful scaling of complexity: three stages

The same part (a plate with two holes) written three ways, each building on the last. This shows how SCADwright features layer on without requiring you to rewrite what you already have.

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

When the part has enough parameters that you want to name them, or you need a caller to read dimensions off the part, wrap it in a [Component](components.md). Variables in `equations` are auto-declared as float parameters; non-float types use `Param(...)` directly.

```python
from scadwright import Component, Param, render
from scadwright.boolops import difference
from scadwright.primitives import cube, cylinder

class Plate(Component):
    equations = "width, length, thk, hole_d, hole_spacing > 0"

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

When the project has enough measurements that the inline argument list is getting long, move them to a concrete subclass: a thin class that fills in values as plain `name = value` lines:

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

The subclass reads like a parts list. Every measurement appears once. The generic `Plate` stays portable; the concrete `MyPlate` holds the project-specific numbers. Equations still work the same way on the subclass: any value the base derives from others, `MyPlate` derives too.

As the Component grows, you'll sometimes need values worked out from other values (something with a loop, a conditional, or a field or item read from an input). Add those as `name = expression` lines in the same [`equations` block](components.md#parameters-equations). For checks that aren't simple bounds (a tuple's length, a rule that loops over elements, a choice between options), add a comparison or boolean rule to the same block.

### Stage 3: Add a Design with variants

When the project has multiple parts or needs different render arrangements (one for printing, one for display), add a [Design](variants.md) class. Parts are instantiated once and shared across variants:

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

Note the `if __name__ == "__main__": run()` at the bottom: this replaces the `render(part, "file.scad")` call from Stages 1 and 2. `run()` discovers the Design class, picks the right variant (from `--variant` or the `default=True` one), renders it, and writes the output file. You don't call `render()` yourself when using a Design.

The transition from Stage 1 to Stage 3 is additive: you wrap existing code in a class, then wrap that in a Design. Nothing gets rewritten; structure layers on.

## Keep generic Components portable

Never put project-specific defaults on a generic Component. If a value belongs to one design, put it on a concrete subclass. If it's genuinely tunable, leave it as a required parameter, or give it a geometrically neutral default like `corner_r=0`.

```python
# Wrong: the 80 mm width is a project choice baked into a reusable class.
class Plate(Component):
    width = Param(float, default=80)

# Right: Plate stays reusable; MyPlate holds the project number.
class Plate(Component):
    equations = "width > 0"

class MyPlate(Plate):
    width = 80
```

## Sharing measurements across parts

The three stages grow a single part. Once a project has *two* parts that must agree on a measurement, that number needs one home. Put it on both parts and a later edit changes one and silently breaks the fit.

Say a cover bolts onto the plate: both need the same mount-hole pattern, so `hole_d` and `hole_spacing` aren't the plate's alone anymore — they describe the interface between the parts. Put that interface in a [Spec](specs_and_adjustments.md#your-first-spec), a small frozen class that holds dimensions and runs the same `equations` block a Component does. Each part takes the Spec as a parameter and reads from it:

```python
from scadwright import Spec

class MountInterface(Spec):
    equations = """
        hole_d = 6
        hole_spacing = 40
    """

class Plate(Component):
    spec = Param()
    equations = "width, length, thk > 0"

    def build(self):
        hole = cylinder(h=self.thk + 2, d=self.spec.hole_d).down(1)
        return difference(
            cube([self.width, self.length, self.thk], center="xy"),
            hole.left(self.spec.hole_spacing / 2),
            hole.right(self.spec.hole_spacing / 2),
        )

class MyPlate(Plate):
    spec = MountInterface
    width = 80
    length = 40
    thk = 5
```

A `Cover` written the same way, given the same `MountInterface`, has holes that line up by construction. Change `hole_spacing` in the Spec and both parts follow on the next render. Passing the Spec in as a parameter keeps `Plate` portable: any Spec carrying `hole_d` and `hole_spacing` drops in.

A Spec is the home for any measurement two parts share, and for measurements taken off something external (a battery, a bolt, a lens mount) that several parts size against. Manufacturing fudges go in the same Spec as [adjustments](specs_and_adjustments.md#adjustments) on their own lines, so the design number stays clean. The [pentacon-six-mount example](../examples/README.md) is built this way: two bayonet caps, each reading one shared spec.

## Splitting across files

A single file with clear zones (REUSABLE / CONCRETE / DESIGN) works well for most projects. Consider splitting when you have more than three Components and the single file becomes hard to navigate, or when distinct parts don't depend on each other.

**By role**, generic Components, their concrete subclasses, and the Design go in separate files:

```
my_project/
    spec.py             # shared dimensions, if parts share measurements
    shapes.py           # generic Components (Plate, Cover, etc.)
    parts.py            # concrete subclasses (MyPlate, MyCover)
    main.py             # Design + @variant + run()
```

Generic Components import only from SCADwright and the standard library. Concrete subclasses import their generic base and the shared spec, then fill in values. The Design file imports the concrete subclasses and composes the scene. `run()` goes in exactly one file: the one you pass to `scadwright build`.

**By part**, for a small project of a few parts, one file per part often reads better: each file holds that part's generic and concrete classes, and they all read a shared `spec.py`. The [pentacon-six-mount example](../examples/README.md) is laid out this way — `spec.py`, `body_cap.py`, `rear_lens_cap.py`, and the files that compose them.

## Next steps

Once you're comfortable with the three stages above, these features are worth learning next:

- [Attaching shapes](attach.md): position parts relative to each other without manual coordinate math (`peg.attach(plate)`); see also [Anchors](anchors.md) for declaring custom attachment points
- [Eliminating epsilon overlap](auto-eps_fuse_and_through.md): `through(parent)` for cutters and `attach(fuse=True)` for joints, replacing manual EPS constants
- [Custom transforms](custom_transforms.md): add your own verbs to the language (`.chamfer_top(depth=1)` on any shape)
- [Shape library](shapes/README.md): tubes, gears, fasteners, and dozens more pre-built shapes
- [Variants](variants.md): `@variant` options, `run()` dispatch rules, and multi-part assembly layouts
- [Morph](morph.md): one-line animation between two variants, exported as APNG for READMEs
- [Command line and parameters](cli_and_args.md): `scadwright build`/`preview`, declared script arguments, and `--from-json` for inputs too big for the command line (a hole list, a parts table)
