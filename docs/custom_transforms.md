# Custom transforms

Custom transforms let you add new verbs to the language. Once you register one, it becomes a method on every shape — you can chain it just like the built-in `translate` or `red`.

Imports used on this page:

```python
from scadwright.transforms import transform
```

## Defining a transform

Use the `@transform("name")` decorator on a function. The function signature is fixed:

- **First parameter**: the shape being transformed. Positional, any name (`node` by convention).
- **A `*` separator**, then all options as keyword-only parameters.
- **Return**: the new shape.

```python
@transform("chamfer_top")
def chamfer_top(node, *, depth):
    return minkowski(node, sphere(r=depth, fn=8))

# Now every shape has a .chamfer_top method:
part = cube([10, 10, 5]).chamfer_top(depth=1)
```

The function above wraps a shape in a `minkowski` with a small sphere, which rounds its edges. After registration, `cube(...).chamfer_top(depth=1)` works on any shape — primitives, components, anything.

If you forget the `*` separator, registration raises a clear error at import time — you don't have to remember.

## Hoisted vs inline

When you use the same transform multiple times with the same options, scadwright generates one OpenSCAD `module` and calls it at each spot:

```python
union(
    cube([10, 10, 5]).chamfer_top(depth=1),
    cube([6, 6, 8]).translate([15, 0, 0]).chamfer_top(depth=1),
)
```

The output SCAD has one `module chamfer_top_<hash>(depth) { ... }` definition and two short calls to it. This keeps the rendered file small and readable.

**There's a catch.** To produce the module, scadwright runs your function once with a *placeholder* in place of the shape. That means your function must treat its shape argument **opaquely** — don't read `.size`, `.r`, `.width`, or any other attribute off it. If you try, you get a clear `AttributeError` pointing at the fix:

```python
@transform("bad")
def bad(node, *, pad):
    return cube(node.size[0] + pad)   # AttributeError at emit time
```

**If you need to read child attributes, pass `inline=True`:**

```python
@transform("frame", inline=True)
def frame(node, *, pad):
    # inline=True means we get the real shape here, not a placeholder.
    x, y, z = node.size
    return difference(
        cube([x + 2*pad, y + 2*pad, z], center=True),
        node,
    )
```

Inline transforms skip the module-hoisting machinery and call your function at every use site with the actual shape. They can't share a module across calls (so the SCAD output is a bit larger when used repeatedly), but your function has full access to the shape's attributes.

**Rule of thumb:** keep transforms non-inline by default. Only switch to `inline=True` when you genuinely need to inspect the shape.

## Listing registered transforms

```python
list_transforms()         # ["chamfer_top", "frame", ...]
```

Returns the names of all transforms registered so far.

---

### Pattern: face-relative transforms

A common pattern for transforms that operate on a specific face of a shape (e.g. cutting a port through a wall, adding a boss to a face): accept a `face` parameter, use `bbox()` to find the face plane, and position the operation in face-local coordinates.

```python
@transform("port_cutout", inline=True)
def port_cutout(node, *, face, at_along, at_z, width, height):
    b = bbox(node)
    if face in ("+x", "-x", "rside", "lside"):
        cutter = cube([b.size[0] + 2, width, height], center=True)
        x_pos = b.max[0] if face in ("+x", "rside") else b.min[0]
        cutter = cutter.translate([x_pos, at_along, at_z])
    # ... similar for +y/-y, +z/-z ...
    return difference(node, cutter)
```

This keeps the face-resolution logic inside the transform — callers just write `body.port_cutout(face="rside", at_along=12, ...)` and don't think about coordinates. The `electronics-case` example uses this pattern extensively.

---

### Under the hood

- Two registrations with the same name raise `SCADwrightError`.
- The hashed module name combines the transform name and a hash of its keyword arguments, so the same transform with different options gets distinct modules.
- For transforms that need raw control over emitted SCAD (custom emit logic, not just AST composition), there's a `Transform` subclass form. It's the escape hatch the decorator is built on; most users won't need it.
- Inline transforms repeat the full geometry at every call site in the generated SCAD. If you apply an inline transform many times (e.g. once per mount hole), consider switching to a non-inline transform to keep the output compact.
- The `node.<transform_name>(...)` method lookup is provided by overriding `__getattr__` on the base node class. If you ever name a transform the same as an existing built-in method (e.g. `translate`), the built-in wins.
