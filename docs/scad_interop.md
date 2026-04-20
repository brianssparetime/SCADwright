# Integrating legacy SCAD code

The normal way to structure a SCADwright project is entirely in Python — Components as classes, transforms as methods, libraries as Python packages. You don't need SCAD's `use` or `include` for that.

This page covers the less common case: you have existing `.scad` files (a team library, BOSL2 modules, a borrowed fastener generator) and you want the SCAD output SCADwright produces to pull them in at render time.

## Using SCAD library modules: `scad_use`

`scad_use=[...]` is an emit-time keyword on `emit`, `emit_str`, and `render`. Each entry becomes a `use <path>` line at the top of the emitted SCAD file:

```python
from scadwright import render
from scadwright.primitives import cube

# A .scad file somewhere on your SCAD library path (or a relative path)
# defining: module my_flange(d, h) { ... }
render(
    cube(10),
    "out.scad",
    scad_use=["libs/flange.scad"],
)
```

The emitted file starts with:

```scad
use <libs/flange.scad>

cube([10, 10, 10], center=false);
```

`use` brings in module and function definitions without executing the file's top-level statements.

## Including SCAD code: `scad_include`

`scad_include=[...]` works the same way but emits `include <path>` lines. `include` pulls in definitions AND executes top-level statements in the included file. Use this sparingly — it's easy to get surprising side-effects.

```python
render(cube(10), "out.scad", scad_include=["project_defaults.scad"])
```

Both `scad_use` and `scad_include` accept lists of strings; the order you pass is the order emitted. `use` lines come before `include` lines in the output.

## Why this is separate from the AST

`use` and `include` aren't geometry — they're file-level declarations. They don't fit inside the tree of shapes SCADwright builds, so they're specified at the boundary where SCADwright hands the output to OpenSCAD, not inside the shape expression.

If your project is mostly SCAD with SCADwright as a thin wrapper, this is the seam between the two worlds. If your project is mostly Python, you probably won't reach for these — prefer writing reusable shapes as Python modules and Components.

## See also

- [`scad_import`](primitives_3d.md#scad_import) — for bringing *external geometry* (STL, SVG, DXF, 3MF, OFF, AMF) into a SCADwright design. This is the common case; it belongs in the primitives chapter, not here.
