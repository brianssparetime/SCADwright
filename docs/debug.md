# Debug helpers

Tools for SCAD-side diagnostics. Most scadwright users never need this — for Python-side debugging, use `print()` or logging. These helpers exist for cases where the diagnostic needs to live in the emitted SCAD output.

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
