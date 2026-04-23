# Components

A Component is a parametric part you define as a Python class. It's like an OpenSCAD `module`, but it **publishes attributes** the caller can read and it **acts like a shape** -- you can transform it, combine it with others, render it directly.

For a walkthrough of how Components fit into a project as it grows, see [Organizing a project](organizing_a_project.md). In brief: start with a flat script, wrap it in a Component when you need named parameters or published dimensions, then add a `Design` class when you need print/display variants.

This page covers the Component authoring surface itself, in order from most common to most specialized.

## Your first Component

A Component needs two things: parameters (what the caller passes in) and a `build()` method (what shape it produces).

The simplest way to declare parameters is through `equations` -- list the constraints your dimensions must satisfy, and the framework creates the parameters for you as floats:

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
        outer = cylinder(h=self.h, r=self.od / 2)
        inner = cylinder(h=self.h + 2, r=self.id / 2).down(1)
        return difference(outer, inner)

t = Tube(h=10, id=8, thk=1)
print(t.od)                                # 10.0 -- solved from the equation
render(t, "tube.scad")                     # build() runs now, result is cached
render(t.right(20).red(), "moved.scad")    # transforms work too
```

`build()` returns the actual shape. It runs the first time SCADwright needs the geometry (render, bounding box, etc.) and the result is cached.

## Declaring parameters

There are three ways to declare parameters, from lightest to most explicit. Use the lightest one that fits.

### 1. `equations` -- the primary way

Variables that appear in an `equations` list are automatically created as `Param(float)`. Equalities (`==`) let the framework solve for whichever the user didn't pass. Inequalities (`>`, `>=`, `<`, `<=`) add validation constraints.

```python
class Tube(Component):
    equations = [
        "od == id + 2*thk",            # equality: solve for the missing one
        "h, id, od, thk > 0",          # inequality: all must be positive
    ]
```

This single block declares four float params (`h`, `id`, `od`, `thk`), sets up the solver, and adds positivity constraints. Specify any sufficient subset at construction time; the solver fills in the rest.

Comma-separated names in inequalities expand into per-variable constraints: `"x, y, z > 0"` means all three must be positive.

Most float parameters have a natural bound — a length is positive, an angle is between 0 and 180, a wall thickness is greater than zero. State the bound as a constraint; the variable is declared for free:

```python
class FilletRing(Component):
    equations = [
        "id, od > 0",
        "base_angle > 0",
        "base_angle < 90",
        "id < od",
    ]
```

`base_angle` doesn't appear in any equality, but the constraint auto-creates it as `Param(float)` and installs the validator. No separate declaration needed.

### 2. `params` -- for truly unbounded floats (rare)

Reach for the `params = "..."` string only when a float genuinely has no natural bound *and* doesn't appear in any equation — a signed offset, a freely-scaling coefficient, or similar:

```python
class Probe(Component):
    params = "phase_offset"        # can be positive or negative; no natural bound
    equations = ["amplitude, frequency > 0"]
```

If you can express a bound, prefer the constraint form — it catches bad inputs as well as declaring the Param.

### 3. `Param(...)` -- escape hatch for non-floats, defaults, and special types

Use `Param(...)` directly for anything that isn't a plain float: non-float types, params with defaults, or params with `one_of` constraints.

```python
class CaseBase(Component):
    pcb = Param(PCBSpec)               # non-float type
    equations = ["wall_thk, floor_thk > 0"]
```

```python
class Tube(Component):
    equations = ["od == id + 2*thk", "h, id, od, thk > 0"]
    slant = Param(str, default="outwards", one_of=("outwards", "inwards"))
```

`Param` accepts:

- `type` -- Python type to coerce the value to. `Param(float)` accepts `5`, `"3.14"`, etc.
- `default` -- used when the caller doesn't pass this parameter. Without a default, the parameter is required.
- `positive`, `non_negative`, `min`, `max`, `range`, `one_of` -- shorthand validators.
- `validators` -- list of callables that raise `ValidationError` on failure.

### Summary: which to use when

| Situation | Use |
| --- | --- |
| Float param in a solving equation | `equations` only -- auto-declared |
| Float param with a constraint (`> 0`, `>= 0`, `< 90`) | `equations` only -- auto-declared by the constraint |
| Float param that is genuinely unbounded | `params = "name"` (rare) |
| Non-float type (`int`, `str`, `tuple`, custom) | `Param(type)` |
| Any param with a default value | `Param(type, default=...)` |
| Enum-style constraint | `Param(str, one_of=(...))` |
| Published derived attribute (loop, namedtuple field, conditional) | [derivation](#derivations-loops-conditionals-namedtuple-fields) in `equations` |
| Arbitrary-Python validation (tuple length, XOR, membership, all-of) | [predicate](#predicates-arbitrary-python-validation) in `equations` |

### Structured data: namedtuple

For structured data that isn't a Component -- battery specs, port dimensions, screw sizes -- use Python's `namedtuple`. It's immutable, lightweight, and reads like a parts list:

```python
from collections import namedtuple

BatterySpec = namedtuple("BatterySpec", "d length label")
AA = BatterySpec(d=14.5, length=50.5, label="AA")
```

Pass these as `Param(BatterySpec)` on a Component that needs them. The Component can then read fields like `self.spec.d` in derivations or `build()`.

## Equations

### How solving works

- Variables in an equation are automatically created as `Param(float)`.
- At construction, the framework determines which params the user supplied and solves for the rest.
- If the user supplies more than necessary, the framework checks consistency and raises if violated.
- Math constants (`pi`, `e`) are recognized and don't count as params. Trig functions (`sin`, `cos`, `tan`) work too.
- A quadratic like `"area == pi * r**2"` works -- the framework uses inequality constraints to disambiguate (e.g. pick the positive root).

### Error cases

All produce a `ValidationError` with enough context to act:

- **Under-specified** -- `Tube(h=10, id=8)`: message lists the sufficient combinations.
- **Over-specified inconsistent** -- `Tube(h=10, id=8, od=10, thk=2)`: message quotes the offending equation and the values.
- **No valid solution** -- `Tube(h=10, od=4, thk=3)` implies `id = -2`; the constraint rejects it.
- **Multiple valid solutions** -- add a constraint (typically `> 0`) to disambiguate.
- **Derivation fails at runtime** -- `ValidationError: X: derivation ``name = expr`` failed: {exception}`; covers `NameError`, `ZeroDivisionError`, `TypeError`, and friends with the raw source.
- **Predicate evaluates to falsy** -- `ValidationError: X: equation ``expr`` failed`; enriched with left/right values for top-level `Compare` and with the offending index for `all(... for e in seq)`.

### Dependency

Equations require `sympy`, installed via the extras: `pip install 'scadwright[equations]'`. Components without `equations` have no sympy import and no extra dependency.

## Composite parts: yield the pieces

When a Component is made of multiple subparts, write `build()` as a generator and `yield` each part. The framework auto-unions them:

```python
class Widget(Component):
    equations = ["w > 0"]

    def build(self):
        yield cube([self.w, self.w, self.w])
        yield cylinder(h=self.w * 2, r=self.w / 4).up(self.w)
        yield sphere(r=self.w / 3).up(self.w * 2).right(self.w / 2)
```

Rules:

- An empty generator (yields nothing) raises `BuildError`.
- A single yield unwraps to that Node (no redundant `union(x)` wrapper).
- A non-Node yield raises `BuildError` at the offending index.
- Returning a Node (not a generator) still works -- use it for single-shape Components.
- Generator form is pure union. If you need `difference`, `intersection`, or to transform the whole result, return a Node instead.

## Concrete subclasses

When a project has enough measurements that inline kwargs are unwieldy, move them to a concrete subclass. Each measurement becomes a plain class attribute:

```python
class MyTube(Tube):
    h = 10
    id = 8
    thk = 1

t = MyTube()                               # od solved = 10.0
```

The subclass reads like a parts list. The generic `Tube` stays portable; the concrete `MyTube` holds the project-specific numbers. See [Organizing a project](organizing_a_project.md) for when and why to use this pattern.

## Resolution (`fn`/`fa`/`fs`)

Resolution is implicit -- every Component accepts `fn`, `fa`, `fs` as constructor kwargs without declaring them. The values flow into the resolution context for `build()`, so all primitives inside inherit them:

```python
t = Tube(h=10, id=8, thk=1, fn=64)        # all cylinders get $fn=64
```

You can also set resolution at the class level:

```python
class HighResTube(Tube):
    fn = 128                               # default $fn for everything in build()
```

Per-shape `fn=` arguments on primitives still win over both.

## Centering

Every Component accepts `center=` as a constructor kwarg. It uses the same syntax as `cube(center=...)`: `True` for all axes, `"xy"` for X and Y only, etc. Centering is applied after `build()`, so the Component stays a Component and its attributes remain readable:

```python
t = Tube(h=10, id=8, thk=1, center="xy")
t.od                                       # 10.0 -- still accessible
bbox(t).center                             # (0, 0, 5) -- X,Y centered, Z at build origin
```

By default, centering uses the bbox center. A Component can override `center_origin()` to use a different reference point:

```python
class Bracket(Component):
    equations = ["width, height, thk > 0"]

    def center_origin(self):
        # Center on the mounting-face midpoint, not the bbox center.
        return (self.width / 2, self.thk / 2, 0)

    def build(self): ...
```

The `center_bbox()` chained method on any shape also supports per-axis centering:

```python
cube([10, 20, 30]).center_bbox("xy")       # center X and Y, leave Z
```

---

## Advanced

### Derivations: loops, conditionals, namedtuple fields

For computed values that *can't* be a scalar sympy equation -- anything that iterates, conditionally branches, or reaches into a namedtuple field -- write them as derivations in the same `equations` list. A derivation is a `name = expression` line (single `=`). The RHS is evaluated at construction time in a restricted namespace (curated Python builtins, curated math, plus instance attributes) and the result is stored on the instance.

```python
class BatteryHolder(Component):
    spec = Param(BatterySpec)
    count = Param(int, positive=True)
    equations = [
        "wall_thk, clearance, floor_thk, tray_depth > 0",
        "pitch = spec.d + 2 * (clearance + wall_thk)",                                # namedtuple field
        "cradle_positions = tuple(-(count-1)*pitch/2 + i*pitch for i in range(count))",  # loop
    ]
```

Derivations see all Params and any earlier derivations. They run in declaration order, so `cradle_positions` above can reference `pitch`.

Derivation names freeze along with Params after construction; reassigning one raises `ValidationError`. The curated namespace includes `range`, `tuple`, `list`, `dict`, `set`, `zip`, `enumerate`, `sum`, `abs`, `round`, `len`, `min`, `max`, `all`, `any`, `int`/`float`/`bool`/`str`, and math functions (`sin`, `cos`, `sqrt`, `pi`, etc.).

### Predicates: arbitrary-Python validation

Boolean expressions that sympy can't reason about -- `len(size) == 3`, `spec.series in {"AA", "AAA"}`, `all(e.dia <= throat for e in elements)`, XOR between optional Params -- are predicates. Drop them into the same `equations` list; the framework classifies each line by shape and routes predicates to the runtime evaluator.

```python
class RoundedBox(Component):
    size = Param(tuple)
    equations = [
        "r > 0",
        "len(size) == 3",                              # tuple-length validation
        "all(s > 2 * r for s in size)",                # element-wise constraint
    ]
```

A falsy predicate raises `ValidationError` with the raw source and, for the two common shapes (top-level `Compare`, `all(... for e in seq)`), per-value context showing which element or pair violated the check.

### Validators reference

Pre-built validators for use with `Param(validators=[...])`:

```python
positive(x)               # x > 0
non_negative(x)           # x >= 0
minimum(n)(x)             # x >= n
maximum(n)(x)             # x <= n
in_range(lo, hi)(x)       # lo <= x <= hi
one_of(*values)(x)        # x in values
```

Custom validators are just functions that take a value and raise `ValidationError` on failure.

### `materialize(component)`

Returns the AST node that `build()` produced (cached). Useful in tests to verify what a Component actually built:

```python
from scadwright import materialize
from scadwright.ast.csg import Difference

tree = materialize(Tube(h=10, id=8, thk=1))
assert isinstance(tree, Difference)        # Tube builds a difference of two cylinders
assert len(tree.children) == 2
```

### Plain `__init__`

You can write your own `__init__` instead of using `equations`/`params`/`Param`. Call `super().__init__()` first, then set attributes:

```python
class Bracket(Component):
    def __init__(self, width, height):
        super().__init__()
        self.width = width
        self.height = height

    def build(self):
        return cube([self.width, self.width, self.height])
```

This is supported but not recommended -- you lose equation solving, auto-generated kwargs-only init, validator support, and the declarative style that makes Components scannable. Use it only if you have a specific reason the declarative approach doesn't fit.

### Build caching and errors

- `build()` runs once per Component instance and the result is cached. Treat Components as immutable after construction.
- If `build()` raises any exception that isn't already a `SCADwrightError`, SCADwright wraps it in a `BuildError` that includes the Component class name and the source location of where you instantiated it. The original exception is chained via `__cause__`.

### Frozen after construction

Components with equations are immutable after construction. Reassigning a param (e.g. `t.id = 5`) would desync from the solved values, so writes raise. To reparameterize, build a new instance.

---

### See also

- [Anchors and attachment](anchors.md) -- declare named attachment points on Components and position parts relative to each other with `attach()`
