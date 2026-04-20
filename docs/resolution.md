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

## Watch out: builds are lazy

Component `build()` runs the first time the geometry is needed (bbox, emit, render), not at construction. If you construct a Component inside a `with resolution(...)` block but the build triggers outside it, the context is already gone:

```python
with resolution(fn=32):
    w = Widget()                # no build yet -- just a Component instance
render(w, "out.scad")           # build runs here, context is gone
```

If the Component has its own `fn` (class attribute or passed as a kwarg), this doesn't matter -- that value is captured at build time. But if the Component has no settings of its own, it'll fall through to whatever context is active at build, which may be nothing. Either pass `fn=` when constructing the Component or use a `@variant(fn=...)` decorator.

---

### Advanced notes

- `resolution` uses a `contextvars.ContextVar` under the hood, so it's thread-safe.
- A primitive captures `fn`/`fa`/`fs` at construction time, not at render time. Constructing a primitive inside one `resolution` block and rendering it inside another preserves the construction-time values.
- For Components, resolution is captured when `build()` runs (which happens lazily on first access), not when the Component is constructed. The class-level `fn`/`fa`/`fs` wrap the call to `build()` in an implicit resolution context. Instance-level `self.fn = ...` overrides the class default.
