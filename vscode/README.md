# SCADwright VSCode extension

Adds three editor-title icons when you open a Python file that imports `scadwright`:

- **Kill OpenSCAD** — kills any running `openscad` processes (handy when a preview window is stuck).
- **Preview** — runs `scadwright build` on the current file and opens the resulting `.scad` in OpenSCAD's GUI for preview.
- **Render** — runs `scadwright build`, then invokes `openscad -o <file>.stl <file>.scad` headless to produce an STL.

## Install (local)

Requires `vsce` (`npm install -g @vscode/vsce`) and a recent VSCode.

```
cd vscode
vsce package           # produces scadwright-vscode-0.1.0.vsix
code --install-extension scadwright-vscode-0.1.0.vsix
```

Reload VSCode. Open any Python file containing `import scadwright` or `from scadwright …`; the three cube icons appear in the editor title bar.

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| `scadwright.scadwrightCommand` | `scadwright` | Command to invoke for the SCADwright CLI. Use a full path if it isn't on `PATH`. |
| `scadwright.openscadCommand` | `openscad` | Command to invoke OpenSCAD. |
| `scadwright.variant` | `""` | Variant passed to `scadwright build --variant=…`. Empty = no flag. |
| `scadwright.saveBeforeBuild` | `true` | Save the active file before running `scadwright build`. |

## Activation

The extension activates on any Python file. The icons only appear when the open file matches `import scadwright` / `from scadwright …`. Editing in or out of that pattern updates the icons live.

## How it works

- **Preview**: shells out to `scadwright preview <file.py>`, which builds the script's `MODEL` to a stable temp `.scad` file (keyed on the script + variant) and launches OpenSCAD on it. Re-clicking Preview overwrites the same temp file, so an already-open OpenSCAD window auto-reloads the change.
- **Render**: shells out to `scadwright render <file.py>`, which builds to a temp `.scad` and then invokes `openscad -o <file>.stl` headless. Output streams to the SCADwright channel.
- **Kill**: `pkill -f openscad` (or `taskkill /F /IM openscad.exe` on Windows).

## Syntax highlighting in `equations` blocks

Inside a Component class, an `equations = """..."""` block (or list-form `equations = [...]`) contains scadwright's small DSL — not arbitrary Python. The extension ships a TextMate grammar injection that highlights the DSL elements on top of normal Python coloring:

- `?fillet`, `?count` — the optional sigil shows as an operator.
- `count:int`, `?direction:bool`, `len(size:tuple)` — the `:type` annotation shows as a type tag.
- `exactly_one`, `at_least_one`, `at_most_one`, `all_or_none` — cardinality helpers show as builtin functions.
- `sin`, `cos`, `sqrt`, `min`, `max`, `degrees`, `radians`, etc. — curated math functions show as builtin functions.
- `range`, `tuple`, `len`, `all`, `any`, etc. — curated namespace builtins show as builtin functions.
- `pi`, `e`, `inf`, `True`, `False`, `None` — show as constants.
- `=` (the lone equation operator), `==`, `<`, `>=`, etc. — show as Python operators.
- Numeric literals, string literals (`'xy'`, `"AAA"`), inline `# ...` comments — show as their Python counterparts.

The injection is contextual: it triggers only on assignments to the literal name `equations` at line start. An unrelated triple-quoted string elsewhere isn't affected.

### Limits

- The grammar can't track bracket depth across multiple lines, so a `:` inside a slice (`arr[1:int]`) or dict literal (`{i: ...}`) inside an equation may mis-color the word after the `:` as a type tag. Cosmetic only — the runtime scanner correctly suppresses tag recognition inside `[...]`/`{...}`.
- This is highlighting, not validation or autocomplete. A typo in a cardinality helper (`exactlyone`) won't be flagged red — it surfaces at class-define time when the file imports. Autocomplete on Param names, go-to-definition for derived names, and validation would require a language server, which isn't shipped here.
