# Resolution (smoothness)

OpenSCAD draws spheres, cylinders, and circles using a fixed number of straight facets. The default is fairly low-poly; you usually want to increase it for final output. The three controls are:

- `fn` -- number of facets in a full circle. `fn=64` makes a sphere from 64 segments around its equator.
- `fa` -- minimum angle per facet (smaller = smoother).
- `fs` -- minimum facet size (smaller = smoother).

## Setting resolution

You can pass these directly to a primitive:

```python
sphere(r=10, fn=64)
cylinder(h=20, r=5, fn=128)
```

Or set them for a whole block of shapes at once with `resolution`:

```python
from scadwright import resolution

with resolution(fn=64):
    body = sphere(r=10)
    cap = cylinder(h=2, r=10)        # both get fn=64

    with resolution(fn=16):
        preview = sphere(r=2)        # fn=16 here
```

Inner blocks inherit unspecified values from the outer block. Direct kwargs on a primitive (`sphere(r=10, fn=8)`) win over the surrounding context.

You can also set defaults at the [Component](components.md) class level:

```python
class Gear(Component):
    fn = 128
    def build(self): ...                # everything inside gets fn=128
```

Every Component accepts `fn`, `fa`, `fs` as constructor kwargs without declaring them:

```python
t = Tube(h=10, id=8, thk=1, fn=64)    # all primitives inside get fn=64
```

And `@variant(fn=...)` sets resolution for an entire variant's build (see [Variants](variants.md)):

```python
@variant(fn=48, default=True)
def print(self):
    return self.widget                  # all primitives get fn=48
```

## Precedence

When a primitive picks up its `fn` / `fa` / `fs`, the rules in order:

1. **Explicit `fn=` on the call** -- always wins. `sphere(r=5, fn=8)` uses 8, period.
2. **Current `resolution()` context** at the moment the primitive is constructed.
3. If neither of those, the value is unset and OpenSCAD uses its built-in defaults.

For primitives constructed **inside `Component.build()`**, the Component's own settings also participate:

4. **Instance attribute** -- `Tube(..., fn=64)` or `self.fn = 64` beats
5. **Class attribute** -- `fn = 64` at class scope beats
6. **Outer `resolution()` context** active at build time.

So inside a Component's build method, the effective order is: per-call > instance attr > class attr > outer context > unset.

## Components capture context at AST insertion, not at build

Component `build()` runs lazily — the first time the geometry is needed (bbox, emit, render), not at construction. But the `resolution()` context that primitives inside `build()` see is captured eagerly: at the moment the Component enters the AST. Three capture points, latest wins:

1. **Construction.** `Component()` snapshots the active `(fn, fa, fs)` context.
2. **Wrap.** Every time the Component is wrapped as a direct child of a parent Node — `Translate(child=c)`, `difference(c, ...)`, `union(c, ...)`, etc. — the parent's `__post_init__` overwrites the snapshot with the wrap-time context.
3. **Render fallback.** If a Component reaches `render()` with a snapshot of all-`None` values, `render()` captures the render-time context.

The result: the user's mental model of "this `with resolution()` block applies to what's inside" works regardless of when the Component's build actually fires.

```python
with resolution(fn=32):
    w = Widget()            # snapshot=(32, None, None) captured here
render(w, "out.scad")        # build runs here; snapshot replays inside, primitives see fn=32

# Or:
w = Widget()                 # snapshot=(None, None, None) at construction
with resolution(fn=64):
    n = w.translate([1,0,0]) # wrap re-captures: w's snapshot now (64, None, None)
render(n, "out.scad")        # primitives inside w.build() see fn=64

# Or:
w = Widget()                 # construction outside any context
with resolution(fn=24):
    render(w, "out.scad")    # render-time fallback fires; primitives see fn=24
```

Class- and instance-level Component settings still override the snapshot, in the documented precedence order.

---

### Advanced notes

- `resolution` uses a `contextvars.ContextVar` under the hood, so it's thread-safe.
- A primitive captures `fn`/`fa`/`fs` at construction time, not at render time. Constructing a primitive inside one `resolution` block and rendering it inside another preserves the construction-time values.
- A Component's resolution snapshot is overwritten on every direct-parent wrap. Reusing the same Component instance across wraps in different contexts means the *latest* wrap's context wins. If you want context independence, construct fresh Component instances per use site.
- A Component nested two-or-more levels deep in the AST receives the immediate-parent's wrap context, not the outer wrap's. Each compound node's `__post_init__` walks only its direct children. This is the intended behavior — it matches the dataclass `__post_init__` semantic and avoids the surprise of an outer wrap mutating snapshots deep in the tree.
