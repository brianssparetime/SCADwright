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

`equations` accepts five forms, distinguished by AST shape — the framework classifies each line automatically:

- **Equalities** (`"od == id + 2*thk"`): drive the solver. Sympy functions like `cos`, `sqrt`, `pi` are available — useful for trig (`"base_r == pitch_r * cos(pressure_angle * pi / 180)"`).
- **Per-Param constraints** (`"x > 0"`, `"x, y, z >= -5"`): a plain number on the right; compile to validators on the listed Params and fire on assignment.
- **Cross-constraints** (`"id < od"`, `"cap_height <= 2 * sphere_r"`): an expression (over other Params) on the right; evaluated after all Params are set.
- **Derivations** (`"pitch = spec.d + 2 * (clearance + wall_thk)"`, single `=`, plain name on the left): the expression on the right is evaluated in a restricted namespace at construction; the result is stored on the instance. Use for loop-generated tuples, namedtuple-field arithmetic, conditional scalars — anything a scalar sympy equation can't express.
- **Predicates** (`"len(size) == 3"`, `"spec.series in {...}"`, `"all(e.dia <= throat for e in elements)"`): arbitrary boolean Python; evaluated at construction, a falsy result raises `ValidationError`. Use for tuple-length checks, XOR between options, element-wise loops, or any check that sympy can't reason about.

Optional inputs use the `?` sigil. Prefix any variable with `?` in the equations list (`"?fillet > 0"`) and the caller may omit it; when omitted, its value is `None` and any constraint referencing it skips. `?` is not allowed in `==` equalities or on the left side of a derivation. For the conditional idiom, write `?x if ?x else y` when the input has a positivity constraint; reach for the explicit `?x is None` form only when `0` is a legitimate value or you specifically need specified-ness (XOR predicates).

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

`params = "..."` is the rare escape for floats that are genuinely unbounded *and* don't appear in any equation. See [Components → Declaring parameters](components.md#declaring-parameters).

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

### Don't use a method where a derivation works

```python
# Wrong (imperative loop in a helper method):
def _compute_positions(self):
    self.cradle_positions = tuple(
        -(self.count-1) * self.pitch / 2 + i * self.pitch
        for i in range(self.count)
    )

# Right (derivation in the equations list):
equations = [
    "cradle_positions = tuple(-(count-1)*pitch/2 + i*pitch for i in range(count))",
]
```

Derivations cover loop-generated tuples, namedtuple-field arithmetic (`spec.d + ...`), and conditional scalars (`(a + b) if cond else c`). Reach for `equations` first.

### Don't hand-code what a predicate does

```python
# Wrong (imperative validation after construction):
def _validate(self):
    for e in self.elements:
        if e.constricted and e.dia > self.throat:
            raise ValueError(...)

# Right (predicate in the equations list):
equations = [
    "all(not e.constricted or e.dia <= throat for e in elements)",
]
```

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
- `no-component-setup` — `def setup(self):` on a `Component` subclass. Move computed values to derivations in `equations` (single `=`) and validation to predicates. The framework hook still exists as an internal escape; user-facing Components must be declarative.

The linter is intentionally conservative: it only flags patterns that have a clear correct alternative. Style-guide rules that require semantic understanding (no baked-in defaults on *reusable* Components, preferring derivations over imperative helpers, etc.) aren't mechanically checkable and live as prose-only guidance.