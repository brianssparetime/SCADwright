# SCADwright style guide

Conventions for writing Components, examples, and shape-library entries. This is the reference for how SCADwright code should look.

SCADwright code should be as simple and expressive as possible, even if that means departing from standard python idiom.

---

## Naming the project

- **SCADwright** — the project name. Use in prose: document titles, README and docs text, docstrings and comments that refer to the project, descriptions, marketing.
- **scadwright** — the Python package. Use in code: imports (`from scadwright import ...`), CLI invocations (`scadwright build ...`), `pip install scadwright`, `pyproject.toml`, and anywhere the literal identifier must match the installed package.

The dividing line is prose-vs-code: if it's a sentence *about* the project, write **SCADwright**; if it's something you'd type into an editor or a terminal, write **scadwright**.

---

## Preferred patterns

Use these features whenever they fit. They exist to eliminate boilerplate and make intent clear.

### Declare dimensional parameters with `equations`

Float parameters that have arithmetic relationships belong in `equations`. Variables are auto-declared as `Param(float)` -- no manual `Param()` needed.

```python
class Tube(Component):
    equations = [
        "od == id + 2*thk",
        "h, id, od, thk > 0",
    ]
```

Specify any two of (id, od, thk) and the solver fills in the third. Constraints (`> 0`) attach validators automatically.

`equations` accepts three forms:

- **Equalities** (`"od == id + 2*thk"`): drive the solver. Sympy functions like `cos`, `sqrt`, `pi` are available — useful for trig (`"base_r == pitch_r * cos(pressure_angle * pi / 180)"`).
- **Per-Param constraints** (`"x > 0"`, `"x, y, z >= -5"`): RHS is a numeric literal; compile to validators on the listed Params and fire on assignment.
- **Cross-constraints** (`"id < od"`, `"cap_height <= 2 * sphere_r"`): RHS references other Params or expressions; evaluated after all Params are set, before `setup()` runs. Use these instead of writing var-vs-var checks in `setup()`.

### Declare standalone float parameters with `params`

Floats that don't appear in any equation but need no special type or validators (but prefer constraints and equatiosn when feasible):

```python
class FilletRing(Component):
    params = "base_angle"
    equations = ["id, od > 0"]
```

### Declare anchors at class scope with `anchor()`

```python
class Bracket(Component):
    equations = ["w, thk, depth > 0"]

    mount_face = anchor(at="w/2, w/2, thk", normal=(0, 0, 1))
```

`at=` accepts a string (expressions evaluated against instance attributes) or a literal tuple. The attribute name becomes the anchor name.

### Use directional helpers for spatial positioning

`.up()`, `.down()`, `.left()`, `.right()`, `.forward()`, `.back()` over `.translate([x, y, z])` when the offset is along a single axis:

```python
inner = shell.up(self.floor_thk)
lid = self.lid.right(self.box.outer_w + 15)
```

### Use `center=` for origin control

Works on primitives and Components. Per-axis with a string, all axes with `True`:

```python
plate = cube([80, 40, 5], center="xy")
u = UShapeChannel(wall_thk=2, channel_length=50, channel_width=10, center="xy")
```

### Use `attach()` for positioning parts relative to each other

```python
cyl = cylinder(r=4, h=15).attach(base_part)
cap = SphericalCap(cap_dia=8, cap_height=5).attach(cyl)
```

Defaults are `face="top"`, `at="bottom"` -- bottom of self on top of other. Use `fuse=True` on joints to eliminate coincident-surface seams in unions.

### Use `through(parent)` for cutters in `difference()`

```python
part = difference(box, cylinder(h=10, r=3).through(box))
```

Eliminates manual epsilon constants. Call after positioning the cutter.

### Use generator-style `build()` for multi-part Components

Yield parts; the framework auto-unions them:

```python
def build(self):
    yield difference(outer, inner)
    for px, py in self.mount_positions:
        yield Tube(od=7, id=3, h=8).translate([px, py, self.floor_thk])
```

### Structure files as REUSABLE / CONCRETE / DESIGN

```python
# =============================================================================
# REUSABLE: generic Components, custom transforms, data types
# =============================================================================

# =============================================================================
# CONCRETE: project-specific subclasses with baked-in values
# =============================================================================

# =============================================================================
# DESIGN: shared parts + variant methods
# =============================================================================
```

Reusable Components have no project-specific defaults. Concrete subclasses fill in values as plain class attributes. Design classes instantiate concrete parts and define variants.

### Comment framework hooks on first use

```python
def setup(self):                                    # framework hook: optional
def build(self):                                    # framework hook: returns the shape
@variant(fn=48, default=True)
def print(self):                                    # user-chosen variant name
```

### Import style

Standard library first, then SCADwright modules grouped by subpackage. Specific imports only:

```python
from collections import namedtuple

from scadwright import Component, anchor
from scadwright.boolops import difference, union
from scadwright.design import Design, run, variant
from scadwright.primitives import cube, cylinder
from scadwright.shapes import Tube, rounded_rect
```

---

## Use only when justified

These features exist for cases the preferred patterns can't handle. If you reach for one, be ready to explain why the preferred way doesn't work.

### `Param()` for non-float types

`Param()` is for bools, strings, and object types -- things that equations and `params=` can't express. Floats belong in equations or `params=`.

```python
n_shape = Param(bool, default=False)       # bool option
spec = Param(BatterySpec)                  # object type
slant = Param(str, default="outwards", one_of=("outwards", "inwards"))
```

### `self.anchor()` in `setup()` for conditional normals

The `at=` string in class-scope `anchor()` supports ternaries (`"0 if n_shape else outer_height"`), so conditional positions don't require `setup()`. The only case that does is when the **normal** itself changes based on a param, since `normal=` is a fixed tuple at class definition time.

### `setup()` for computed values

Last resort. Most computed values belong in equations. `setup()` is justified only when the computation genuinely can't be an equation (loops, conditionals, iterating a namedtuple spec) AND the result needs to be published for other Components to read. If you're reaching for `setup()`, first ask whether an equation, a `params=` declaration, or a class-scope `anchor()` can do the job instead.

### `.translate([x, y, z])` instead of directional helpers

Use when the offset involves multiple axes simultaneously, or when the position comes from a variable/computation rather than a literal:

```python
yield Tube(...).translate([px, py, self.floor_thk])
```

### `orient=True` on `attach()`

Rotates the attached part so anchor normals oppose. Use when mounting to a side face or any non-default orientation. Default `orient=False` is correct for vertical stacking.

### Manual EPS constants

Use `EPS = 0.01` and manual extension only for non-axis-aligned cutters or edge cases where `through()` can't detect the coincident face. Prefer `through(parent)` for cutters and `attach(fuse=True)` for joints.

---

## Don't

### Don't bake concrete values into reusable Components

Reusable Components declare parameters; concrete subclasses or callers provide values.

```python
# Wrong:
class Bracket(Component):
    w = Param(float, default=20)      # project-specific default in generic class

# Right:
class Bracket(Component):
    equations = ["w, thk, depth > 0"]

class MyBracket(Bracket):             # concrete subclass fills in values
    w = 20
    thk = 3
    depth = 15
```

### Don't use `Param(float)` when equations or params= work

```python
# Wrong:
w = Param(float)
h = Param(float)

# Right (if constrained):
equations = ["w, h > 0"]

# Right (if unconstrained):
params = "w h"
```

### Don't use `setup()` for simple arithmetic

```python
# Wrong:
def setup(self):
    self.inner_w = self.outer_w - 2 * self.wall_thk

# Right:
equations = ["inner_w == outer_w - 2 * wall_thk"]
```

### Don't use `.translate()` for single-axis offsets

```python
# Wrong:
part.translate([0, 0, 5])

# Right:
part.up(5)
```