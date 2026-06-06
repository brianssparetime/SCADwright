# SCADwright

SCADwright is a Python library for designing 3D models. You write Python code that describes shapes, transforms, and combinations; SCADwright writes an OpenSCAD source file (`.scad`); OpenSCAD renders that file into STL or other formats.

If you've used OpenSCAD before, the shapes and operations will look familiar. The language around them is Python, which gives you classes, functions, automated tests, and proper error messages.

If you haven't used OpenSCAD, the basic idea is:

- Start with primitive shapes (cubes, spheres, cylinders).
- Move them around with transforms (translate, rotate, scale).
- Combine them with boolean operations (union, difference, intersection).
- The result is a 3D shape you can save and 3D-print.

## [Quick start guide / How to organize a project](organizing_a_project.md)

This quick guide shows you how a project can organically grow from very simple OpenSCAD-like code
to levaraging more complex constructs like reusable [Components](components.md) and [variants](variants.md) without
having to re-write anything.


## [Examples](../examples/README.md)

Example projects arranged from simplest to most complex, each building on the last: from flat OpenSCAD-like scripts up to multi-file projects around shared specs. 

Reading them in order is a guided tour of the constructs in context.


## Reference

### Comparative references:

- [Coming from OpenSCAD](coming_from_openscad.md) — SCAD features (for, if, let, modules, `$t`, `$preview`, etc.) mapped to their SCADwright/Python equivalents
- [How is SCADwright different?](how_is_scadwright_different.md) — comparison with SolidPython, PythonSCAD, CadQuery, Build123d, JSCAD, and plain OpenSCAD

### OpenSCAD equivalent functionality:

- [3D primitives](primitives_3d.md) — `cube`, `sphere`, `cylinder`, `polyhedron`
- [2D primitives](primitives_2d.md) — `square`, `circle`, `polygon`
- [Transformations](transformations.md) — moving, rotating, scaling, coloring shapes
- [Boolean operations](csg.md) — combining shapes (`union`, `difference`, `intersection`, `hull`, `minkowski`)
- [Extrusions](extrusions.md) — turning 2D shapes into 3D (`linear_extrude`, `rotate_extrude`)
- [Math](math.md) — `scadwright.math` SCAD trig (in degrees).  Python trig works fine too.
- [Animation and viewpoints](animation.md) — `t()` for `$t`-driven shapes, `cond()` for ternary, `viewpoint()` for the default camera. See also [Morph](morph.md) for one-line animation between variants.
- [Using existing SCAD files](scad_interop.md) — emitting `use <...>` / `include <...>` at the boundary to an existing SCAD codebase

### SCADwright extended functionality:

**Core concepts**

- [Components](components.md) — your own parametric parts as classes (replaces OpenSCAD modules)
- [Composition helpers](composition_helpers.md) — `mirror_copy`, `rotate_copy`, `linear_copy`, `multi_hull`, `sequential_hull`
- [Variants](variants.md) — print vs. display, multi-part assemblies, section views, resolution tiers
- [Shape library](shapes/README.md) — 50+ ready-made Components: tubes, gears, fasteners, bearings, infill panels, and more
- [Anchors](anchors.md) — the data type (named attachment points), authoring custom anchors on Components
- [Attaching shapes](attach.md) — `attach()` to position parts relative to each other
- [Eliminating epsilon overlap](auto-eps_fuse_and_through.md) — `through()` for cutters, `attach(fuse=True)` for joints
- [Custom transforms](custom_transforms.md) — adding your own verbs (e.g. `.chamfer_top(depth=1)`)
- [Specs](specs_and_adjustments.md#your-first-spec) — shared dimensions across parts in a single source of truth
- [Morph](morph.md) — one-line animations between two variants, exported as APNG for READMEs. See also [Animation and viewpoints](animation.md) for the lower-level `$t` toolkit.

**Workflow**

- [Resolution](resolution.md) — controlling smoothness (`fn`/`fa`/`fs`), precedence rules
- [Errors and logging](errors_and_logging.md) — what SCADwright does when something's wrong
- [Command line](cli_and_args.md) — `scadwright build`/`preview`/`render`, script parameters
- [Project dependency graph](graph_setup.md) — `scadwright graph` emits a Mermaid/JSON/DOT graph of how Components, Specs, and Designs relate
- [Debug helpers](debug.md) — `force_render`, `echo` for SCAD-side diagnostics (niche)
- [Testing](testing.md) — `tree_hash` for regression pinning, geometry assertions, golden-file patterns

**Advanced**

- [Adjustments](specs_and_adjustments.md#adjustments) — printer-error fudges recorded inline alongside the equations they correct
- [Bounding boxes and tests](introspection.md) — measuring parts and writing tests
- [Matrix](matrix.md) — 4×4 transform math for advanced placement calculations

### [Cheatsheet](cheatsheet.md)

A compact one-page reference of the whole public API — imports, primitives, transforms, CSG, extrusions, components, resolution, variants, math, matrix, bbox, CLI. Start here when you know what you want and just need the syntax.

### Conventions used in these docs

- **Vector arguments** (positions, sizes) accept either a list `[x, y, z]` or keyword arguments `x=, y=, z=`. Both forms work everywhere.
- **Scalar shorthand.** `cube`, `square`, and `scale` accept a single number as shorthand for "same on every axis" — `cube(5)` means `cube([5, 5, 5])`. Other vector-taking operations (`translate`, `mirror`, `resize`) require an explicit vector because a scalar would be ambiguous there ("translate 5 along which axis?").
- **Lowercase names** like `cube` or `cylinder` are basic shapes (functions). **Capitalized names** like `Tube` or `Component` are classes.
- **Chained methods** like `.translate(...)` or `.red()` create a new shape; the original is unchanged.
- **Errors** include the file and line of the call that produced them.

## Package layout

The public API is split into small, focused submodules. Import what you need:

- `scadwright.primitives` — `cube`, `sphere`, `cylinder`, `polyhedron`, `square`, `circle`, `polygon`
- `scadwright.boolops` — `union`, `difference`, `intersection`, `hull`, `minkowski`
- `scadwright.transforms` — standalone `translate`/`rotate`/`scale`/`mirror`/`color`/`resize` + the custom-transform decorator
- `scadwright.extrusions` — `linear_extrude`, `rotate_extrude`
- `scadwright.composition_helpers` — `linear_copy`, `rotate_copy`, `mirror_copy`, `multi_hull`, `sequential_hull`
- `scadwright.shapes` — higher-level parametric parts (`Tube`, `Funnel`, `RoundedBox`, `Arc`, `Sector`, etc.)
- `scadwright.math` — trig and numeric helpers matching OpenSCAD semantics
- `scadwright.errors` — `ValidationError`, `BuildError`, `EmitError`, `SCADwrightError`
- `scadwright.asserts` — geometry assertions for tests

The root namespace (`from scadwright import ...`) keeps the Component authoring surface (`Component`, `Param`, `Spec`, `Adjustment`, validators) and top-level tools (`bbox`, `tree_hash`, `emit`, `render`, `resolution`, `variant`, etc.).

Transforms also exist as chained methods on every shape (`cube(10).translate([5, 0, 0])`), which usually reads better for simple expressions; the standalone `translate(cube(10), [5, 0, 0])` form is available for cases where the subject is a complex expression already.

## Style guide

[Style guide](style-guide.md) — conventions for writing idiomatic SCADwright code: preferred patterns (`equations`, directional helpers, `attach`/`through`), when lower-level alternatives are justified, and common anti-patterns. Worth reading before authoring Components or contributing to the shape library.

It's also particularly useful to drop into an LLM's context when using AI assistance — it steers generated code away from generic-Python habits toward SCADwright's idioms.
