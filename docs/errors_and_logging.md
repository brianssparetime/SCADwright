# Errors and logging

Imports used on this page:

```python
from scadwright.errors import ValidationError, BuildError, EmitError, SCADwrightError
```

## Errors

When something goes wrong, scadwright raises one of three error types. All three inherit from a common base, `SCADwrightError`, so a single `except SCADwrightError` catches anything the library throws.

### `ValidationError`

Raised when you pass bad arguments to a built-in function or shape — wrong vector length, negative size, non-numeric value, an out-of-range polyhedron face index, etc.

The error message includes the file and line of your call:

```
ValidationError: cube size[0] must be non-negative, got -5.0 (at widget.py:42)
```

### `BuildError`

Raised when a `Component`'s `build()` method itself raises an exception (other than another scadwright error). scadwright wraps the original exception, adds the component's class name and source location, and chains the original via Python's `__cause__`.

```
BuildError: while building Widget: division by zero (at widget.py:88)
```

The original exception is still accessible — pytest and Python's traceback show it under "the above exception was the direct cause of the following exception."

If `build()` raises a `SCADwrightError` (like a `ValidationError` from a primitive inside it), scadwright passes it through unchanged — no double-wrapping.

### `EmitError`

Raised by the SCAD emitter for unrecoverable problems while writing output. The most common cause is referring to a custom transform that hasn't been registered.

In practice you rarely see `EmitError` directly, because most problems get caught earlier as `ValidationError`.

### Catching errors

```python
try:
    render(part, "out.scad")
except SCADwrightError as e:
    print(f"render failed: {e}")
    if e.source_location:
        print(f"  source: {e.source_location}")
```

Each error carries a `source_location` attribute when one was captured. The printed form already includes it; the attribute is there if you want to format it differently.

## Logging

scadwright logs build timings, emit timings, and other internal events using Python's standard `logging` module. The library is silent by default — you have to opt in.

### `set_verbose`

The simple way to see what scadwright is doing:

```python
set_verbose()                  # show INFO-level events (build/emit timings)
set_verbose(False)             # quiet again
```

Output goes to stderr. A typical line:

```
[scadwright.component INFO] built Widget in 2.34ms (src: widget.py:42)
[scadwright.emit INFO] emitted 847 chars in 1.10ms
```

The CLI's `-v` flag is equivalent to `set_verbose()`.

For more detail (resolution context entries, every primitive constructed, etc.):

```python
import logging
set_verbose(logging.DEBUG)
```

---

### Advanced notes

- The full logger hierarchy is under the `scadwright` namespace: `scadwright.component`, `scadwright.emit`, `scadwright.resolution`, `scadwright.variant`, `scadwright.validation`. Configure them individually with `logging.getLogger("scadwright.component").setLevel(...)` if you want fine-grained control.
- `set_verbose()` attaches a single stderr handler. Calling it multiple times doesn't stack handlers — it replaces and re-applies cleanly.
- `BuildError`'s `__cause__` is the original exception. Tracebacks from pytest show both the wrapping and the original; debuggers can step into either.
