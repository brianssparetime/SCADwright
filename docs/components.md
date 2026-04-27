# Components

A Component is a parametric part you define as a Python class. It behaves like an OpenSCAD `module`, with two additions: the caller can read computed values off it, and it acts like a shape itself. You can transform it, combine it with other shapes, or render it directly.

For when and why to introduce Components in a project, see [Organizing a project](organizing_a_project.md).

## Your first Component

A Component has two parts: parameters (the inputs the caller passes) and a `build()` method (the shape it produces).

The simplest way to declare parameters is the `equations` list. You state the relationships and rules your dimensions must satisfy; SCADwright creates the parameters for you and fills in whichever values the caller didn't pass.

```python
from scadwright import Component, render
from scadwright.boolops import difference
from scadwright.primitives import cylinder

class Tube(Component):
    equations = [
        "od = id + 2*thk",
        "h, id, od, thk > 0",
    ]

    def build(self):
        outer = cylinder(h=self.h, r=self.od / 2)
        inner = cylinder(h=self.h + 2, r=self.id / 2).down(1)
        return difference(outer, inner)

t = Tube(h=10, id=8, thk=1)
print(t.od)                                # 10.0 (filled in from the equation)
render(t, "tube.scad")                     # build() runs now
render(t.right(20).red(), "moved.scad")    # transforms work too
```

Specify any two of `id`, `od`, `thk` and SCADwright fills in the third. `build()` runs the first time the shape is needed; the result is kept for reuse.

## Parameters: the `equations` list

Each line in `equations` does one of two things:

- **States an equation.** `"od = id + 2*thk"` says od equals id + 2*thk. Either side can be any expression: `"len(size) = 3"`, `"max(a, b) = foo"`, `"spec.foo = 5"`. SCADwright fills in any value you didn't supply; if you supplied all of them, it checks they agree.
- **States a rule.** `"id < od"`, `"all(s > 2*r for s in size)"`. SCADwright checks the rule and raises a clear error if it fails.

Names you don't declare elsewhere become float parameters automatically. Most dimensions have a natural bound (a length is positive, an angle is between 0 and 180), so a rule line like `"id, od > 0"` declares the variables and sets their bounds in one step:

```python
class FilletRing(Component):
    equations = [
        "id, od > 0",
        "base_angle > 0",
        "base_angle < 90",
        "id < od",
    ]
```

Every name in `equations` is readable on the Component afterwards: `t.od`, `f.base_angle`.

Don't start a name with an underscore (`_`); those are reserved for SCADwright itself.

### Building expressions

Any Python expression in an equation can use these pieces:

- Arithmetic: `+`, `-`, `*`, `/`, `**`, parentheses.
- Math: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `sqrt`, `log`, `exp`, `abs`, `ceil`, `floor`, `min`, `max`, `pi`, `e`.
- Conditional: `a if cond else b`.
- Reading a field or an item out of an input: `spec.d`, `arr[0]`, `holes[i]`.
- Tuples, lists, dicts, comprehensions: `tuple(...)`, `list(...)`, `range(...)`, `len(...)`, `sum(...)`, `sorted(...)`, `tuple(i*pitch for i in range(count))`.

If an equation gives a value a name (`pitch = ...`, `od = ...`), SCADwright works out the value when you make the part and stores it on the part. You can read it back: `b.pitch`, `b.od`. An equation that doesn't name a new value (`len(size) = 3`, `spec.foo = 5`) is just a check: SCADwright reads each side and raises an error if they don't agree.

You can write your equations in any order. SCADwright reads the whole list and works out which one needs which other; you don't have to put them in any particular order.

```python
class BatteryHolder(Component):
    spec = Param(BatterySpec)
    count = Param(int, positive=True)
    equations = [
        "wall_thk, clearance, floor_thk > 0",
        "pitch = spec.d + 2 * (clearance + wall_thk)",
        "cradle_positions = tuple(-(count-1)*pitch/2 + i*pitch for i in range(count))",
    ]

b = BatteryHolder(spec=AA, count=6, wall_thk=1.6, clearance=0.4, floor_thk=2)
b.pitch                                    # 18.5 (readable on the Component)
b.cradle_positions                         # (-46.25, -27.75, -9.25, 9.25, 27.75, 46.25)
```

### Comma broadcasts

A comma list of names applies the line to each name. Same broadcast for both forms:

- `"x, y > 0"` is `x > 0` and `y > 0`.
- `"x, y = 5"` is `x = 5` and `y = 5`.

There's no Python tuple-unpacking. If you want different values per name, write separate lines.

### Optional inputs

Prefix a name with `?` anywhere in `equations` to make it optional. If the caller omits it, the value is `None`, and any rule that references it is skipped.

Four helpers check how many optional inputs were set:

| Helper | Meaning |
|---|---|
| `exactly_one(a, b, ...)` | one and only one is set |
| `at_least_one(a, b, ...)` | one or more is set |
| `at_most_one(a, b, ...)` | zero or one is set |
| `all_or_none(a, b, ...)` | all are set or none are |

"Set" means "is not None." The value `0` counts as set.

```python
class ChamferedBox(Component):
    size = Param(tuple)
    equations = [
        "?fillet > 0",
        "?chamfer > 0",
        "len(size) = 3",
        "exactly_one(?fillet, ?chamfer)",                       # one, not both
        "edge = ?fillet if ?fillet else ?chamfer",              # whichever is set
        "all(s > 2 * edge for s in size)",
    ]

ChamferedBox(size=(20, 15, 10), fillet=2)     # chamfer omitted
ChamferedBox(size=(20, 15, 10), chamfer=3)    # fillet omitted
```

When a helper fails, the error message names each argument and its value, so you can see which inputs were set.

The `?` sigil is for optional *inputs*. It can't appear on a name that's computed by another line.

### Keep one idea per line

If a line is trying to do two things at once (pick a value *and* check something with it), split it by naming the intermediate on its own line. In the ChamferedBox example above, `edge` is a name for the active radius; the size check below it then reads plainly as "every side fits the edge."

## Other kinds of parameters

### `Param(...)` for non-floats and defaults

Use `Param(...)` when a parameter isn't a plain float (a bool, a string, a tuple, a spec object) or when it needs a default or an enumerated choice:

```python
class CaseBase(Component):
    pcb = Param(PCBSpec)                                 # non-float type
    equations = ["wall_thk, floor_thk > 0"]

class Tube(Component):
    equations = ["od = id + 2*thk", "h, id, od, thk > 0"]
    slant = Param(str, default="outwards", one_of=("outwards", "inwards"))
```

Options:

- `type`: the Python type to convert the value to. `Param(float)` accepts `5` or `"3.14"`.
- `default`: used when the caller doesn't pass this parameter. Without a default, the parameter is required.
- `positive`, `non_negative`, `min`, `max`, `range`, `one_of`: common validators you can list inline.
- `validators`: a list of your own check functions (each raises `ValidationError` on bad input).

### `params = "..."` for unbounded floats (rare)

For a float that has no natural bound and doesn't appear in any equation (a signed offset, a freely-scaling coefficient), list its name in a `params` string:

```python
class Probe(Component):
    params = "phase_offset"                  # can be positive or negative
    equations = ["amplitude, frequency > 0"]
```

If you can express any bound at all, prefer the bound form; it catches bad inputs and declares the parameter in one line.

### `namedtuple` for spec data

For a bundle of related numbers (a battery's diameter and length, a screw's dimensions, a port's profile), use Python's `namedtuple`. It's a small record that reads like a parts list:

```python
from collections import namedtuple

BatterySpec = namedtuple("BatterySpec", "d length label")
AA = BatterySpec(d=14.5, length=50.5, label="AA")
```

Pass these into a Component as `Param(BatterySpec)`. The Component reads fields like `self.spec.d` in equations or in `build()`.

### Summary

| Situation | Use |
|---|---|
| Float in an equation | `equations` only, auto-declared |
| Float with a bound (`> 0`, `< 90`) | `equations` only, auto-declared by the bound |
| Float that is truly unbounded | `params = "name"` (rare) |
| Non-float type (`int`, `str`, `tuple`, custom) | `Param(type)` |
| Parameter with a default value | `Param(type, default=...)` |
| Enum-style choice | `Param(str, one_of=(...))` |
| Value worked out from other values | equation line in `equations` (`name = ...`) |
| Check the bound form can't express | rule line in `equations` |

## Building the shape

### Returning a shape

In the simple case, `build()` returns a single shape:

```python
def build(self):
    outer = cylinder(h=self.h, r=self.od / 2)
    inner = cylinder(h=self.h + 2, r=self.id / 2).down(1)
    return difference(outer, inner)
```

### Yielding pieces

If the Component is made of multiple pieces, write `build()` with a `yield` line for each piece. SCADwright joins them into a single shape (union):

```python
class Widget(Component):
    equations = ["w > 0"]

    def build(self):
        yield cube([self.w, self.w, self.w])
        yield cylinder(h=self.w * 2, r=self.w / 4).up(self.w)
        yield sphere(r=self.w / 3).up(self.w * 2).right(self.w / 2)
```

Rules:

- Yielding nothing is an error.
- Yielding one piece is fine; the result is that piece (no wrapper).
- Every yield has to be a shape. Yielding anything else raises an error naming the offending yield.
- `yield` form is always union. For `difference` or `intersection`, or to transform the whole result, return a single shape instead.

## Features every Component gets

These work on every Component automatically, no matter how it was written.

### Centering with `center=`

Pass `center=` to the constructor to move the shape onto the origin. It uses the same syntax as `cube(center=...)`: `True` for all axes, `"xy"` for X and Y only, and so on.

```python
t = Tube(h=10, id=8, thk=1, center="xy")
t.od                                       # 10.0 (still readable)
bbox(t).center                             # (0, 0, 5)
```

By default, centering uses the shape's bounding-box center. If the bounding-box center isn't the right reference point, override it:

```python
class Bracket(Component):
    equations = ["width, height, thk > 0"]

    def center_origin(self):
        return (self.width / 2, self.thk / 2, 0)

    def build(self): ...
```

Bounding-box centering is also available as a chained method on any shape:

```python
cube([10, 20, 30]).center_bbox("xy")
```

### Resolution (`fn`/`fa`/`fs`)

Resolution flows implicitly. Every Component accepts `fn`, `fa`, `fs` as constructor keyword arguments; every primitive inside inherits them:

```python
t = Tube(h=10, id=8, thk=1, fn=64)        # every cylinder inside gets $fn=64
```

You can also set resolution as a default on the class, so every part you build from it uses it:

```python
class HighResTube(Tube):
    fn = 128
```

A primitive can still override with its own `fn=` argument.

## Concrete subclasses

When a project has enough measurements that inline arguments get unwieldy, move them to a concrete subclass. Each measurement becomes one line:

```python
class MyTube(Tube):
    h = 10
    id = 8
    thk = 1

t = MyTube()                               # od filled in: 10.0
```

The generic `Tube` stays reusable; `MyTube` holds the project-specific numbers. See [Organizing a project](organizing_a_project.md) for when and why to do this.

---

## Reference

### Validators

Ready-made check functions for `Param(validators=[...])`:

```python
positive(x)               # x > 0
non_negative(x)           # x >= 0
minimum(n)(x)             # x >= n
maximum(n)(x)             # x <= n
in_range(lo, hi)(x)       # lo <= x <= hi
one_of(*values)(x)        # x is one of the listed values
```

A custom validator is just a function that takes a value and raises `ValidationError` on bad input.

### What errors look like

Every failure raises `ValidationError` (or `BuildError` if something goes wrong inside `build()`). The message tells you which Component and which line failed:

- Not enough inputs: `cannot solve for equation variables: given {id}, need one of: {id, thk}, {od, thk}, ...`
- Inputs that don't agree: `equation violated: od = id + 2*thk (lhs=10, rhs=12)`.
- A bound failure: `ChamferedBox.fillet: must be > 0, got -1`.
- A rule failure: `RoundedBox: constraint violated: all(s > 2 * r for s in size): failed at index 1 with s=4: left=4, right=6.0`.

If `build()` raises an exception, SCADwright wraps it in a `BuildError` that includes the Component class name and the source line where you created the Component.

### Plain `__init__` (escape hatch)

You can write your own `__init__` instead of using `equations` / `params` / `Param`. Call `super().__init__()` first, then set values on `self`:

```python
class Bracket(Component):
    def __init__(self, width, height):
        super().__init__()
        self.width = width
        self.height = height

    def build(self):
        return cube([self.width, self.width, self.height])
```

This is supported but gives up everything the `equations` approach provides: filling in missing values, validation, readable computed values. Use it only if you have a specific reason the `equations` approach doesn't fit.

### Inspecting the built shape: `materialize()`

`materialize(component)` returns the shape that `build()` produced (cached on first call). Useful in tests to assert the Component built what you expected:

```python
from scadwright import materialize
from scadwright.ast.csg import Difference

tree = materialize(Tube(h=10, id=8, thk=1))
assert isinstance(tree, Difference)
assert len(tree.children) == 2
```

### Components are frozen after construction

Once constructed, a Component's values can't be reassigned. `t.id = 5` raises an error. To change values, build a new Component.

### `sympy` dependency

Install `sympy` with `pip install 'scadwright[equations]'`. It's highly recommended: without it, you can't use the `equations` feature, which is how you'll declare most Components.

### See also

- [Anchors and attachment](anchors.md): named attachment points on Components; position parts relative to each other with `attach()`.
