# Animation and viewpoints

OpenSCAD's animation feature drives a special variable `$t` from 0 to 1 over a configurable timeline; you reference `$t` inside transforms and sizes to make geometry change frame-by-frame. OpenSCAD's view also reads top-of-file `$vpr`/`$vpt`/`$vpd`/`$vpf` globals as the default camera.

SCADwright exposes both via `scadwright.animation`:

```python
from scadwright.animation import t, cond, viewpoint
```

## `t()` — animation time

`t()` returns a `SymbolicExpr` standing for OpenSCAD's `$t`. Arithmetic with it (and Python numbers) builds an expression tree that emits as SCAD source instead of being resolved to a Python float at build time:

```python
from scadwright.primitives import cube
from scadwright.animation import t

cube(10).rotate([0, 0, t() * 360])    # full turn over the animation
```

emits:

```
rotate([0, 0, $t * 360]) {
    cube([10, 10, 10], center=false);
}
```

To run the animation: open the `.scad` in OpenSCAD, then **View → Animate**, set FPS and Steps, and `$t` advances from 0 to 1 across the timeline.

### Where SymbolicExprs are accepted

- **Transform operands**: `translate`, `rotate`, `scale`, `mirror` (vector elements and the scalar angle of axis-angle `rotate`).
- **Primitive sizes**: `cube` size dimensions, `sphere` radius/diameter, `cylinder` height/radius/diameter.
- **Viewpoint fields** (see below).

Anywhere else, SCADwright expects a Python number — passing a `SymbolicExpr` raises `ValidationError` with a clear message. Validators like `positive=True` short-circuit when the value is symbolic (no way to check at build time).

### Arithmetic and operators

`SymbolicExpr` overloads `+ - * / %` (mixed with Python numbers in either order), unary `-`, and `**` (which emits as `pow(a, b)` since SCAD has no `**`). Comparisons (`<`, `<=`, `>`, `>=`, `==`, `!=`) return SymbolicExprs too — they're for use with `cond()`, not `if`:

```python
t() < 0.5         # a SymbolicExpr representing "$t < 0.5"

if t() < 0.5:     # TypeError — won't silently misbehave
    ...
```

## `cond(test, a, b)` — branching on `$t`

For values that depend on a condition involving `$t`, use `cond()` to emit a SCAD ternary:

```python
from scadwright.animation import t, cond

# Ping-pong: 0 → 1 over the first half, 1 → 0 over the second half.
ping = cond(t() < 0.5, 2 * t(), 2 - 2 * t())
cube(1).translate([ping * 50, 0, 0])
```

emits:

```
translate([($t < 0.5 ? 2 * $t : 2 - 2 * $t) * 50, 0, 0]) {
    cube([1, 1, 1], center=false);
}
```

`cond()` is a value-level switch; it doesn't replace whole shapes. To swap one shape for another, you can `cond` between scaling factors (e.g. `scale by 0 to hide`).

## `viewpoint(...)` — default camera

```python
from scadwright import render
from scadwright.animation import viewpoint, t

with viewpoint(rotation=[60, 0, 30], distance=200, target=[0, 0, 0]):
    render(MODEL, "out.scad")
```

emits at the top of `out.scad`:

```
$vpr = [60, 0, 30];
$vpt = [0, 0, 0];
$vpd = 200;
```

Fields:

| Kwarg      | SCAD var | Meaning                                     |
| ---------- | -------- | ------------------------------------------- |
| `rotation` | `$vpr`   | Euler rotation `[x, y, z]` in degrees       |
| `target`   | `$vpt`   | Point the camera looks at, `[x, y, z]`      |
| `distance` | `$vpd`   | Distance from target                        |
| `fov`      | `$vpf`   | Vertical field-of-view in degrees           |

Any field left as `None` is omitted; OpenSCAD picks its default.

### Animated cameras

Viewpoint fields accept `SymbolicExpr`, so you can build a turntable:

```python
with viewpoint(rotation=[60, 0, t() * 360], distance=200):
    render(MODEL, "turntable.scad")
```

### Nested `viewpoint()` blocks

Nested calls merge — an inner `None` falls back to the outer block's value, not to OpenSCAD's default:

```python
with viewpoint(rotation=[60, 0, 30], distance=100):
    with viewpoint(distance=200):
        # rotation is still [60, 0, 30] from the outer block,
        # distance is 200 from the inner.
        render(MODEL, "closer.scad")
```

## Combining with variants

Animation pairs naturally with variants -- render an animated `display` variant alongside a static `print` variant:

```python
from scadwright.animation import t, viewpoint
from scadwright.design import Design, run, variant

class AnimatedWidget(Design):
    widget = MyWidget()

    @variant(fn=48, default=True)
    def print(self):
        return self.widget

    @variant(fn=48)
    def display(self):
        with viewpoint(rotation=[60, 0, 30], distance=200):
            return self.widget.rotate([0, 0, t() * 360])

if __name__ == "__main__":
    run()
```
