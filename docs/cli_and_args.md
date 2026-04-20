# Command line and parameters

scadwright gives you two ways to render a script: call `render(...)` from inside the script, or run the `scadwright build` command.

Imports used on this page:

```python
from scadwright import arg, parse_args
```

The CLI also lets you parametrize a script — declare named parameters once, then override them from the command line.

## `scadwright build`

After installing scadwright, the `scadwright` command is available. The `build` subcommand takes a Python script and writes an OpenSCAD file:

```
scadwright build widget.py                          # writes widget.scad
scadwright build widget.py -o out.scad              # explicit output path
scadwright build widget.py --debug                  # source-line comments in output
scadwright build widget.py --compact                # single-line output
scadwright build widget.py --variant=print          # set render variant
scadwright build widget.py --vpr=60,0,30            # set camera rotation ($vpr)
scadwright build widget.py --vpd=200                # set camera distance ($vpd)
scadwright build widget.py -v                       # show INFO logs while building
```

The script must define a top-level `MODEL` (a scadwright shape). The CLI imports the script, finds `MODEL`, and renders it.

If the script doesn't define `MODEL`, the CLI prints a clear error and exits.

## `scadwright preview`

```
scadwright preview widget.py                  # build + open in OpenSCAD's GUI
scadwright preview widget.py --variant=print  # variant works the same as build
scadwright preview widget.py --openscad=/opt/homebrew/bin/openscad
```

`preview` builds the script's `MODEL` to a stable temp file (path keyed on the script + variant, in `$TMPDIR`), then launches OpenSCAD on it detached and returns immediately. Re-running `preview` overwrites the same temp file, so an OpenSCAD window already pointed at it auto-reloads — no need to close and reopen.

OpenSCAD lookup order: `--openscad` flag, then `$SCADWRIGHT_OPENSCAD`, then `openscad` on `PATH`.

## `scadwright render`

```
scadwright render widget.py                   # writes widget.stl next to the script
scadwright render widget.py -o /tmp/out.stl   # explicit STL output
scadwright render widget.py --variant=print
```

`render` builds the script to a temp `.scad` file and then invokes `openscad -o OUT.stl TEMPFILE` synchronously to produce an STL (or any format OpenSCAD's `-o` accepts based on extension — `.off`, `.amf`, `.3mf`, etc.). Output streams to stdout/stderr; the command returns OpenSCAD's exit code.

## Script parameters: `arg`

Declare a parameter at the top of your script. The first time you call `arg`, scadwright parses the command-line arguments and looks up the value:

```python
width = arg("width", default=40, type=float, help="widget width in mm")
fn    = arg("fn",    default=64, type=int)

with resolution(fn=fn):
    MODEL = cube([width, width, 20])
```

Run the script with overrides:

```
scadwright build widget.py --width=80 --fn=128
```

Or run the script directly with Python:

```
python widget.py --width=80
```

`scadwright build widget.py --help` lists the script's declared arguments along with their defaults and help text.

**Parameters of `arg`:**

- `name` — the argument name (becomes `--name` on the command line).
- `default` — value used when not overridden.
- `type` — Python type to coerce the value to (`int`, `float`, `str`, etc.). Defaults to `str`.
- `help` — short description shown in `--help` output.

## Rendering from inside a script: `render`

If you'd rather skip the CLI and just run the script with Python, call `render` directly:

```python
render(part, "out.scad")
render(part, "out.scad", pretty=False)         # one-line output
render(part, "out.scad", debug=True)           # source-line comments
```

This works even when the script also defines `MODEL` for the CLI; the two paths don't conflict.

## `parse_args`

```python
ns = parse_args()
```

Forces command-line argument parsing immediately and returns the result as a standard `argparse.Namespace`. Most scripts don't need this — `arg()` handles parsing on first use. Call `parse_args()` if you want all parameters resolved before any other code runs.

---

### Advanced notes

- `arg` uses `argparse.parse_known_args` under the hood, so unknown arguments don't cause errors. This lets `scadwright build`'s own flags coexist with script arguments.
- Re-registering the same `arg` name with different parameters raises `SCADwrightError`.
- `render` is the lower-level entry point used by the CLI; you can pass the same `pretty` / `debug` flags either way.
- For complex argument schemes (subparsers, mutually exclusive groups), use `argparse` directly — `arg` is the simple path.
