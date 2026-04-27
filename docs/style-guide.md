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

Float parameters that have arithmetic relationships belong in `equations`. Names are auto-declared as `Param(float)` — no manual `Param()` needed.

```python
class Tube(Component):
    equations = [
        "od = id + 2*thk",
        "h, id, od, thk > 0",
    ]
```

Specify any two of (id, od, thk) and SCADwright fills in the third. Bound rules (`> 0`) declare the parameter and attach validators in one step.

Each line in `equations` is one of two things:

- **An equation.** `"od = id + 2*thk"`, `"len(size) = 3"`, `"max(a, b) = foo"`, `"x * len(y) = c"`. Either side can be any expression. SCADwright fills in any value the system can solve from what you supplied; anything you over-supplied gets consistency-checked. Subscript and attribute expressions like `arr[0]` or `spec.foo` are reads — the resolver consistency-checks them but never mutates them.
- **A rule.** `"id < od"`, `"all(s > 2*r for s in size)"`. Checked at construction; a falsy result raises `ValidationError`. Bound rules with a numeric bound (`"x > 0"`) compile to a per-Param validator that fires on direct assignment too.

Comma broadcasts: `"x, y > 0"` is two rules; `"x, y = 5"` is two equations.

`=` and `==` are accepted and mean the same thing. Prefer `=`.

**Optional inputs.** Prefix a name with `?` in the equations list (`"?fillet > 0"`) to make it optional. If omitted, the value is `None` and any rule referencing it skips. `?` can't appear on a name that's computed by another line. For the conditional idiom, write `?x if ?x else y` when the input has a positivity constraint; reach for the explicit `?x is None` form only when `0` or `False` is a legitimate value.

### Let constraints declare float parameters

A constraint auto-creates its operand as `Param(float)` and installs the validator in one line. Most dimensions have a natural bound — a length is positive, an angle lives in a range — so the constraint form covers the declaration and the validation together:

```python
class FilletRing(Component):
    equations = [
        "id, od > 0",
        "base_angle > 0",
        "base_angle < 90",
        "id < od",
    ]
```

`params = "..."` is the rare escape for floats that are genuinely unbounded *and* don't appear in any equation. See [Components → Other kinds of parameters](components.md#other-kinds-of-parameters).

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

### Use `yield`-form `build()` for multi-part Components

Yield each part; SCADwright auto-unions them:

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

### Don't use `Param(float)` when a constraint will declare it

```python
# Wrong:
w = Param(float)
h = Param(float)

# Right (any natural bound is a constraint):
equations = ["w, h > 0"]
```

For a genuinely-unbounded float that doesn't appear in any equation (rare — signed offsets, freely-scaling coefficients), use `params = "name"`. But first check whether a constraint actually does apply — it usually does.

### Don't use a method where an equation works

```python
# Wrong (imperative loop in a helper method):
def _compute_positions(self):
    self.cradle_positions = tuple(
        -(self.count-1) * self.pitch / 2 + i * self.pitch
        for i in range(self.count)
    )

# Right (equation in `equations`):
equations = [
    "cradle_positions = tuple(-(count-1)*pitch/2 + i*pitch for i in range(count))",
]
```

Equations cover loop-generated tuples, namedtuple-field arithmetic (`spec.d + ...`), and conditional scalars (`(a + b) if cond else c`). Reach for `equations` first.

### Don't pack two ideas into one equation

If a line is carrying both a computed value and a check on it, split them so each line is a single idea: one equation that names the intermediate, one rule that uses it.

```python
# Wrong (one string, two ideas: which edge is active + every side fits it)
equations = [
    "?fillet > 0", "?chamfer > 0",
    "exactly_one(?fillet, ?chamfer)",
    "all(s > 2 * (?fillet if ?fillet else ?chamfer) for s in size)",
]

# Right (one equation gives the active edge a name; one rule checks size)
equations = [
    "?fillet > 0", "?chamfer > 0",
    "exactly_one(?fillet, ?chamfer)",
    "edge = ?fillet if ?fillet else ?chamfer",
    "all(s > 2 * edge for s in size)",
]
```

Adding an extra line is cheap (one more string, no boilerplate), and the equation expressions live inside Python strings so nested expressions don't get IDE support. Split any line where a reader would need to parse a sub-expression before they can parse the whole.

### Don't hand-code what a rule line does

```python
# Wrong (imperative validation after construction):
def _validate(self):
    for e in self.elements:
        if e.constricted and e.dia > self.throat:
            raise ValueError(...)

# Right (rule line in equations):
equations = [
    "all(not e.constricted or e.dia <= throat for e in elements)",
]
```


### Don't define `setup()` on a Component

```python
# Wrong (imperative computation in a hook method):
def setup(self):
    self.pitch = self.spec.d + 2 * (self.clearance + self.wall_thk)

# Right (equation in `equations`):
equations = [
    "pitch = spec.d + 2 * (clearance + wall_thk)",
]
```

Anything `setup()` was used for — computed values, validation, multi-step bookkeeping — has a place in `equations`. The lint rule `no-component-setup` enforces this on user-facing Components.

### Don't use `.translate()` for single-axis offsets

```python
# Wrong:
part.translate([0, 0, 5])

# Right:
part.up(5)
```

---

## Enforcement

`tools/lint_scadwright.py` is an AST-only linter that catches the most common mechanical drift. It runs automatically as part of the test suite (`tests/test_lint_scadwright.py::test_repo_lints_clean`) and can also be invoked directly:

```
python tools/lint_scadwright.py              # default: examples/ + src/scadwright/shapes/
python tools/lint_scadwright.py path/to.py   # lint a specific file or directory
```

Rules currently enforced:

- `no-module-eps` — module-level `EPS = ...` assignments. Prefer `.through(parent)` for cutters or `.attach(fuse=True)` for joints; when a manual epsilon is genuinely unavoidable (non-axis-aligned cutters, hull-slab layer thickness), scope it locally inside the function that needs it.
- `no-param-float` — `Param(float)` with no `default=` argument. Floats belong in `equations` or `params=`. `Param(float, default=None)` is the deliberate opt-out pattern and is allowed.
- `translate-single-axis` — `.translate([x, 0, 0])` (or any permutation with two literal zeros). Use the `.right/.left/.up/.down/.forward/.back` directional helper.
- `no-component-setup` — `def setup(self):` on a `Component` subclass. Move computed values to equations in `equations` (`x = expr`) and checks to rule lines (comparisons or boolean expressions). The framework hook still exists as an internal escape; user-facing Components must declare their inputs and rules in `equations`.

The linter is intentionally conservative: it only flags patterns that have a clear correct alternative. Style-guide rules that require semantic understanding (no baked-in defaults on *reusable* Components, preferring `equations` over imperative helpers, etc.) aren't mechanically checkable and live as prose-only guidance.