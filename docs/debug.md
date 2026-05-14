# Debug helpers

Tools for SCAD-side diagnostics. Most SCADwright users never need this — for Python-side debugging, use `print()` or logging. These helpers exist for cases where the diagnostic needs to live in the emitted SCAD output.

Imports used on this page:

```python
from scadwright.debug import force_render, echo
```

## `force_render`

Wraps a subtree in SCAD's `render(convexity=...)`, forcing OpenSCAD to do a full CGAL render of that subtree in preview (F5) mode rather than its cheaper OpenCSG approximation. Useful when preview shows artifacts that full render fixes, or when the subtree is so complex that preview is slower than full render.

```python
# Chained (preferred when you're in a shape expression):
complex_part.force_render(convexity=5)

# Standalone:
force_render(complex_part, convexity=5)
```

**Parameters:**

- `convexity` — optional render-complexity hint. Higher values allow OpenSCAD to correctly render more deeply-nested concavities; default is OpenSCAD's.

This doesn't change the emitted geometry — only OpenSCAD's rendering strategy. The bounding box passes straight through the child.

### What goes inside the wrap

`force_render` is a memoization boundary: everything inside it is part of the cache build, and any edit invalidates the cache. Put stable, expensive geometry inside; keep cheap or iteratively-edited operations outside. Putting frequent differences (engravings, version stamps, sweepable hole arrays) inside the wrap means each preview re-evaluates them as part of the cache; build the cutter outside instead:

```python
# Cutter inside the cache, dragged into every rebuild:
result = body.add_text(label="...", relief=-0.3, ...).force_render()

# Cutter outside, body cached on its own:
cutter = body.text_geometry(label="...", relief=-0.3, ...)
result = difference(body.force_render(), cutter)
```

[`text_geometry`](add_text.md#returning-glyph-geometry-without-combining-text_geometry) is the text-specific tool; for hole cutouts and similar, plain `difference()` with the cutter as its own expression does the same job. When a downstream consumer (`pack_on_bed`, anything that calls `tight_bbox`) needs to see the cached body's extents, wrap with [`with_bbox_from(body)`](introspection.md#overriding-bbox-with_bbox_from) so the difference doesn't trip the "can't tighten" raise.

## `echo`

Emits SCAD's `echo(...)` for diagnostic output visible at SCAD render time. Accepts positional and keyword arguments, which map to SCAD's anonymous and named echo arguments.

```python
# Bare statement: emits `echo("starting");`
echo("starting")

# Wrap a subtree: emits `echo("label") { ...subtree... }`
cube(10).echo("size=10")

# Or standalone wrapping form:
echo("label", _node=cube(5))

# Positional and keyword args:
echo("count:", n=4)
```

**When to reach for this:**

- You're generating SCAD that someone else will open and you want a visible message at render time.
- You want to see a computed parameter value in OpenSCAD's console.
- Otherwise, use `print()` in Python.

**Bounding box:** a bare `echo` has zero bbox (it's a statement, not geometry). A wrapping `echo` passes its child's bbox through unchanged.
