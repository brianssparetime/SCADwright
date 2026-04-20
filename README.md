# scadwright

scadwright is a Python library for designing 3D parts and assemblies: you write Python; scadwright generates an OpenSCAD source file that renders into STL (or any other format OpenSCAD supports).

## What is this and why does it exist?

OpenSCAD offers a straight-forward and easy path to programmatic 3d design: declare shapes, transform them, combine them with booleans.

But OpenSCAD is limited in ways that rapidly get annoying once your project grows beyond a few parts.

**scadwright keeps the basic OpenSCAD model** — the same shapes, the same transforms, the same boolean operations — and lets you write them in Python.

However, **scadwright goes way beyond just a python wrapper for OpenSCAD**: you get the ability to add new components and transforms to the language, components that publish their dimensions to callers, a rich library of reusable shapes out of the box, scripts you can parametrize from the command line, real error messages with line numbers, and automated tests.

While simple projects very strongly resemeble OpenSCAD code (easy to be productive immediately), as your projects grows in complexity, **scadwright allows a graceful transition to more complex features**, without any hard syntactic or conceptual boundaries. **Styles can be mixed and matched in the same project.**

I have put significant effort into refining the UX of scadwright:  the more advanced constructs use a syntax 
that's neither quite OpenSCAD nor quite standard object-oriented python. Instead, the goal is to ruthlessly 
elimate boiler plate, and make constructs simple to use in common cases for those with little background in
object-oriented python or advanced OpenSCAD, while retaining full python capabilities and a low-level interface
for exceptional cases.

scadwright calls OpenSCAD only at render time. The Python side has no external dependencies, but sympy is highly recommended to enable full functionality.  I've taken some care to make emitted SCAD relatively human-readable.

If you're comparing scadwright against SolidPython, PythonSCAD, CadQuery, Build123d, or other Python+CAD tools, see [How is scadwright different?](docs/how_is_scadwright_different.md) for a side-by-side.

The [quick start / organizing a project guide](docs/organizing_a_project.md) is the best place to see the power of scadwright in action. 


## scadwright systematically addresses the most painful aspects of OpenSCAD:

Here's 14 different OpenSCAD vexations which scadwright makes simple...


### 1. Modules can't expose what they know

When you write a parametric module in OpenSCAD — say a bracket with mount-hole positions — the caller has no way to ask where those holes are. You either compute the offsets in two places, or hard-code them.

In scadwright, parametric parts are Python classes. They publish whatever attributes the caller needs, and the caller can read them without rendering anything:

```python
from scadwright import Component
from scadwright.primitives import cube

class Bracket(Component):
    equations = ["width, height > 0"]

    def build(self):
        return cube([self.width, self.width, self.height])

b = Bracket(width=80, height=5)
print(b.width)               # readable; no geometry built yet
```

### 2. Dimensional relationships live in your head, not the code

A hollow tube has an outer diameter, an inner diameter, and a wall thickness, linked by `od == id + 2*thk`. In OpenSCAD you either write three modules (`tube_by_id_thk`, `tube_by_od_thk`, `tube_by_id_od`) or one module with conditional logic. The relationship lives in a comment; the code just enumerates cases. And if a wall thickness must be positive, you write an `assert()` that fires at render time -- after you've already waited.

In scadwright, you declare relationships and constraints together as equations. The framework solves for whichever parameter you didn't pass, and catches constraint violations at construction time -- before any geometry is built:

```python
from scadwright import Component

class Tube(Component):
    equations = [
        "od == id + 2*thk",                # structural relationship: solve for the missing one
        "h, id, od, thk > 0",              # constraints: caught immediately at construction
    ]

    def build(self): ...

Tube(h=10, id=8, thk=1)      # od solved = 10
Tube(h=10, id=8, od=10)      # thk solved = 1
Tube(h=10, od=10, thk=1)     # id solved = 8
Tube(h=10, id=8, thk=-1)     # ValidationError: thk must be positive
```

One definition, every call site reads naturally for the dimensions the caller has on hand. The full dimensional contract -- relationships and constraints -- is visible at a glance.

### 3. You can't add new transforms or other "verbs"

In OpenSCAD you can't write `cube(10).chamfer_top(depth=1)` — there's no way to add a transform that works on any shape.

In scadwright, register a transform once and it becomes a method on every shape:

```python
from scadwright.boolops import minkowski
from scadwright.primitives import cube, sphere
from scadwright.transforms import transform

@transform("chamfer_top")
def chamfer_top(node, *, depth):
    return minkowski(node, sphere(r=depth, fn=8))

part = cube([10, 10, 5]).chamfer_top(depth=1)
```



### 4. Every union/difference needs manual epsilon overlap

In OpenSCAD, when two shapes share a face in a `difference()` or `union()`, the result has artifacts unless you manually extend the shapes by a tiny epsilon. Every project defines `eps = 0.01` and litters it through every cut and join.

scadwright handles this automatically:

```python
from scadwright.boolops import difference, union
from scadwright.primitives import cube, cylinder

box = cube([20, 20, 10])
part = difference(box, cylinder(h=10, r=3).through(box))     # through-hole, no manual eps
```

`through(parent)` detects which faces of the cutter are flush with the parent and extends them automatically. For joints, `attach(fuse=True)` overlaps parts at the contact face. See [Eliminating epsilon overlap](docs/auto-eps_fuse_and_through.md).

### 5. You spend half your time on geometry that isn't your actual project

OpenSCAD has no module library. Every project starts with reinventing tubes, rounded rectangles, and screw holes. Need an M3 bolt? Look up the head diameter, compute the hex profile, get the clearance hole size right. Need a gear? That's a week.

scadwright ships a shape library with 50+ ready-made Components across mechanical, fastener, gear, and print-oriented categories:

```python
from scadwright.shapes import Tube, SpurGear, Bolt, HexNut, HoneycombPanel, Bearing

cap = Tube(h=10, id=8, thk=1)                    # od solved: 10
gear = SpurGear(module=2, teeth=20, h=5)          # involute profile, publishes pitch_r
bolt = Bolt(size="M3", length=10)                 # ISO dimensions from data tables
bearing = Bearing(series="608")                   # 8x22x7, ready for fit-check
panel = HoneycombPanel(size=(80, 60, 3), cell_size=8, wall_thk=1)
```

Every shape is a Component -- you can read its computed dimensions, attach other parts to it, and pass it into boolean operations. See the [shape library docs](docs/shapes/) for the full catalog.

### 6. No clean separation between display and print variants

Often the best way to print a part is very different from how you want to see it. A part might need supports, or to be re-oriented, or cut in half for printing. For display, you might want to see parts mated together or show stand-in hardware.

In OpenSCAD this becomes commented-out blocks, duplicated files, or fragile flags.

scadwright has a `Design` class with named `@variant` methods:

```python
from scadwright.boolops import union
from scadwright.design import Design, run, variant

class Widget(Design):
    box = MyBox()
    lid = MyLid(box=box)

    @variant(fn=48, default=True)
    def print(self):
        return union(self.box, self.lid.translate([80, 0, 0]))

    @variant(fn=48)
    def display(self):
        return union(self.box, self.lid.up(self.box.height))

if __name__ == "__main__":
    run()
```

```
scadwright build widget.py --variant=print
scadwright build widget.py --variant=display
```


### 7. Positioning parts relative to each other requires manual coordinate math

In OpenSCAD, stacking a lid on a box means computing `translate([0, 0, box_height])` by hand. If you add a spacer or change a dimension, every downstream offset needs updating.

scadwright's `attach()` method lets you position parts by naming which faces should touch:

```python
from scadwright.primitives import cube, cylinder

plate = cube([40, 40, 2])
peg   = cylinder(h=10, r=3).attach(plate)                   # bottom on top
cap   = cube([8, 8, 2]).attach(peg, face="top")              # cap on top of peg
```

Insert a spacer between any two parts and nothing downstream needs to change. Components can declare custom named anchors for semantically meaningful attachment points.

See [Anchors and attachment](docs/anchors.md) for the full reference.

### 8. You can't reason about a part's size without rendering it

In OpenSCAD, the only way to know how big something is -- whether it fits on your print bed, whether two parts overlap, whether a lid is wider than its box -- is to render it and eyeball the result.

scadwright computes bounding boxes from the AST, without rendering. You can query them, assert against them, and use them to position parts relative to each other:

```python
from scadwright import bbox
from scadwright.asserts import assert_fits_in, assert_no_collision

bb = bbox(my_widget)
print(bb.size)                             # (width, length, height)

assert_fits_in(my_widget, [200, 200, 50])  # fits on the print bed?
assert_no_collision(box, lid)              # parts don't overlap?
```

### 9. Centering parts is manual and repetitive

In OpenSCAD, `center=true` works on primitives but not on modules. If your module builds a shape at the origin and you want it centered, you compute the offset yourself. Every module that needs centering reinvents the same translate-by-half-size logic.

In scadwright, every Component accepts `center=` as a constructor kwarg -- same syntax as `cube(center=...)`, with per-axis control:

```python
from scadwright.shapes import UShapeChannel

u = UShapeChannel(wall_thk=2, channel_length=50, channel_width=10, center="xy")
u.outer_width                              # still readable -- it's still a Component
```

The Component author doesn't write any centering code. The framework computes the bounding box after `build()` and translates the requested axes to the origin. For Components where the geometric center isn't the right reference point, override `center_origin()` to return a custom one.



### 10. Transforms read backwards

In OpenSCAD, the verb comes before the noun: you write the rotate-then-translate first, then the shape they apply to. Reading the code, you have to scan to the end of a line to see what's actually moving.

scadwright puts the shape first. Operations chain off the shape:

```python
from scadwright.primitives import cube

cube([10, 20, 30]).translate([0, 0, 5]).rotate([0, 45, 0]).red()
```


### 11. Errors don't tell you where they came from

OpenSCAD's error messages typically point at the rendered output, not your source. Tracking down which call produced a bad value is manual.

scadwright errors carry the file and line of your call:

```python
from scadwright.primitives import cube

cube([-5, 10, 10])
# ValidationError: cube size[0] must be non-negative, got -5.0 (at widget.py:42)
```


### 12. Scripts can't declare command-line parameters

OpenSCAD takes `-D foo=10`, but scripts can't say what parameters they accept, what types they expect, or what defaults to use. The contract lives in comments.

scadwright scripts declare parameters explicitly:

```python
from scadwright import arg, render
from scadwright.boolops import difference
from scadwright.primitives import cube, cylinder

width = arg("width", default=40, type=float, help="widget width in mm")

MODEL = difference(
    cube([width, width, 20], center="xy"),
    cylinder(h=22, r=5, center=True),
)

render(MODEL, "widget.scad")
```

```
scadwright build widget.py --width=80
scadwright build widget.py --help          # lists arguments with defaults
```

### 13. Resolution ($fn) is tedious to manage

In OpenSCAD, you either set `$fn` globally (too coarse) or pass it to every single primitive call (tedious and easy to miss one). There's no middle ground.

In scadwright, resolution (`fn`, `fa`, `fs`) flows automatically through the hierarchy. Set it once at the level that makes sense and every primitive below inherits it:

```python
from scadwright.shapes import Tube

# Per-instance: pass fn when constructing a Component
cap = Tube(h=10, id=8, thk=1, fn=64)

# Per-variant: set fn in the @variant decorator and every Component
# and primitive built inside that variant inherits it
@variant(fn=48, default=True)
def print(self):
    return self.housing     # all primitives inside get fn=48

# Per-scope: wrap any block of code
with resolution(fn=128):
    high_res_part = difference(sphere(r=10), sphere(r=8))
```

No declaration needed on the Component side — `fn` is accepted by every Component automatically and flows into the resolution context for its `build()` method.




### 14. You can't tell if a part has changed

OpenSCAD has no way to write a regression test that says "this part hasn't changed since I last reviewed it." You either re-render and visually compare, or trust that your edit didn't break anything.

scadwright hashes the geometry tree so you can pin a part's shape in a unit test:

```python
from scadwright import tree_hash

def test_widget_geometry_pinned():
    assert tree_hash(Widget(width=40)) == "a1b2c3d4e5f6..."
```

If any dimension, transform, or boolean op changes, the hash changes and the test fails -- before you ever open OpenSCAD.


## Quick example

```python
from scadwright import render
from scadwright.boolops import difference
from scadwright.primitives import cube, cylinder

body = cube([40, 40, 20], center="xy")
hole = cylinder(h=22, r=5, center=True, fn=64)

part = difference(
    body,
    hole.translate([10, 0, 0]),
    hole.translate([-10, 0, 0]),
)

render(part, "widget.scad")
```

Run with `python widget.py` (writes `widget.scad`) or use the CLI: `scadwright build widget.py`. Open the result in OpenSCAD to render.

## Quick example (with a Component)

When a part has named dimensions and relationships between them, wrap it in a Component:

```python
from scadwright import Component, render
from scadwright.boolops import difference
from scadwright.primitives import cylinder

class Tube(Component):
    equations = [
        "od == id + 2*thk",
        "h, id, od, thk > 0",
    ]

    def build(self):
        return difference(
            cylinder(h=self.h, r=self.od / 2),
            cylinder(h=self.h + 2, r=self.id / 2).translate([0, 0, -1]),
        )

t = Tube(h=30, id=20, thk=2)      # od solved = 24.0
print(t.od)                        # 24.0 -- readable without rendering
render(t, "tube.scad")
```

## Quick example (with a Component and @variant)

Building on the Tube above, add a Design with variants -- a display view showing the tube upright, and a print view that halves it into two concave-down pieces spaced apart for the print bed:

```python
from scadwright import Component, bbox
from scadwright.boolops import difference, union
from scadwright.design import Design, run, variant
from scadwright.primitives import cylinder

class Tube(Component):
    equations = [
        "od == id + 2*thk",
        "h, id, od, thk > 0",
    ]

    def build(self):
        return difference(
            cylinder(h=self.h, r=self.od / 2),
            cylinder(h=self.h + 2, r=self.id / 2).translate([0, 0, -1]),
        )

class MyTube(Tube):
    h = 30
    id = 20
    thk = 2

class TubeProject(Design):
    tube = MyTube()

    @variant(fn=64, default=True)
    def display(self):
        return self.tube

    @variant(fn=64)
    def print(self):
        half = self.tube.halve([0, -1, 0])          # cut in half along Y
        spacing = bbox(half).size[1] + 5
        return union(
            half,                                    # concave side down
            half.translate([0, spacing, 0]),
        )

if __name__ == "__main__":
    run()
```

```
scadwright build tube.py                     # display variant (default)
scadwright build tube.py --variant=print     # two halves, bed-ready
```

## Install

```
pip install -e '.[dev]'
pytest                                 # unit + golden tests
SCADWRIGHT_TEST_OPENSCAD=1 pytest        # also OpenSCAD round-trip tests
```

The `scadwright` command becomes available.

## Dependencies

scadwright has no required dependencies beyond Python's standard library, however, equation solving (the `equations` class attribute) requires sympy, installed via `pip install 'scadwright[equations]'`.  Installing this is highly recommended for the full functionality of scadwright.

## Other tools useful in conjunction:

### MCP

If you're developing with Claude Code, install the [OpenSCAD MCP server](https://github.com/quellant/openscad-mcp). It gives Claude the ability to render your `.scad` output, visually inspect the result, and catch geometry errors without you having to open OpenSCAD yourself. scadwright's generated SCAD is fully compatible -- Claude can build your script, render it through the MCP, and iterate on the design in a tight feedback loop.

Whichever AI assistant you use, dropping the [style guide](docs/style-guide.md) into its context steers generated code away from generic-Python habits toward scadwright's idioms.

### VS Code extension 

Included in this project is [a Visual Studio Code extension](/vscode/) that detects when you open a python scadwright file and shows icons to preview in OpenSCAD, render to a file, or kill any OpenSCAD instances.  

This makes it simple to see the results of changes with a single click.  As long as the generated filename is the same (i.e. you're invoking the same variant), clicking preview will auotmatically update the code in an open OpenSCAD instance and re-preview it, saving the time of closing and re-opening the application.

## Documentation

I've taken great care to produce excellent documentation that's easy to consume.  This is not an AI-generated after-thought, but rather months of iteration on explaining simply how to produce expressive and powerful code.

[Full documentation here](docs/README.md). Documentation is along the lines of the [OpenSCAD Language Reference](https://openscad.org/documentation.html).  There's also a [cheatsheet](docs/cheatsheet.md) that parallels [the OpenSCAD cheatsheet](https://openscad.org/cheatsheet/).

For a quick intro, see [How to organize a project](docs/organizing_a_project.md).

This framework also includes [examples of projects at various levels of difficulty click](examples/README.md)

If you're comparing scadwright against SolidPython, PythonSCAD, CadQuery, Build123d, or other Python+CAD tools, see [How is scadwright different?](docs/how_is_scadwright_different.md) for a side-by-side.
