# SCADwright VSCode extension

Two things:

1. **Editor-title icons** (Kill, Preview, Render) that shell out to the `scadwright` CLI for the active file.
2. **Syntax highlighting inside `equations` blocks** — a TextMate grammar injection that lights up the small DSL inside `equations = """..."""` strings on top of normal Python coloring.

The extension activates on any Python file. The icons only appear when the open file matches `import scadwright` / `from scadwright …`; editing in or out of that pattern updates the icons live. The grammar injection runs everywhere but is contextual — it only fires on `equations = """..."""` (or `equations = [...]`) at line start, so unrelated triple-quoted strings aren't affected.

## Install

Two options.

### Option A — symlink (recommended for development)

Drops the live folder into VSCode's extensions directory. Edits to the grammar or `extension.js` take effect on the next `Developer: Reload Window`. No build step.

```
ln -s "$(pwd)/vscode" "$HOME/.vscode/extensions/scadwright-local.scadwright-vscode-0.1.0"
```

Then `Cmd+Shift+P` → `Developer: Reload Window` in VSCode. To remove later: `rm` the symlink, reload window.

### Option B — package and install (recommended for distribution)

Requires `vsce`:

```
npm install -g @vscode/vsce       # one-time
```

Then:

```
cd vscode
vsce package                       # produces scadwright-vscode-0.1.0.vsix
code --install-extension scadwright-vscode-0.1.0.vsix
```

Reload VSCode.

If you don't want a global vsce install, `npx @vscode/vsce package` works too.

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| `scadwright.scadwrightCommand` | `scadwright` | Command to invoke for the SCADwright CLI. Use a full path if it isn't on `PATH`. |
| `scadwright.openscadCommand` | `openscad` | Command to invoke OpenSCAD. |
| `scadwright.variant` | `""` | Variant passed to `scadwright build --variant=…`. Empty = no flag. |
| `scadwright.saveBeforeBuild` | `true` | Save the active file before running `scadwright build`. |

## Editor-title commands

- **Kill OpenSCAD** — `pkill -f openscad` (or `taskkill /F /IM openscad.exe` on Windows). Handy when a preview window is stuck.
- **Preview** — shells out to `scadwright preview <file.py>`, which builds the script's `MODEL` to a stable temp `.scad` file (keyed on script + variant) and launches OpenSCAD on it. Re-clicking Preview overwrites the same temp file, so an already-open OpenSCAD window auto-reloads the change.
- **Render** — shells out to `scadwright render <file.py>`, which builds to a temp `.scad` and then invokes `openscad -o <file>.stl` headless. Output streams to the SCADwright channel.

## Syntax highlighting in `equations` blocks

Inside a Component class, an `equations = """..."""` block (or the list form `equations = [...]`) carries scadwright's small DSL — not arbitrary Python. The grammar injection picks out the DSL elements on top of the standard Python colors:

| Element | Examples |
| --- | --- |
| Optional sigil | `?fillet`, `?count`, `?direction:bool` |
| Inline `:type` tag | `count:int`, `axis:str`, `len(size:tuple)` |
| Cardinality helpers | `exactly_one(?fillet, ?chamfer)`, `at_least_one(...)`, `at_most_one(...)`, `all_or_none(...)` |
| Curated math functions | `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `sqrt`, `log`, `exp`, `abs`, `ceil`, `floor`, `min`, `max`, `sum`, `round`, `degrees`, `radians` |
| Curated namespace builtins | `range`, `tuple`, `list`, `dict`, `set`, `frozenset`, `zip`, `enumerate`, `len`, `int`, `float`, `bool`, `str`, `all`, `any`, `sorted`, `reversed` |
| Curated constants | `pi`, `e`, `inf`, `True`, `False`, `None` |
| Operators | `=` (the lone equation operator), `==`, `!=`, `<`, `<=`, `>`, `>=`, arithmetic (`+ - * / // % **`), boolean (`and`, `or`, `not`), conditional (`if`, `else`), membership/identity (`in`, `not in`, `is`, `is not`) |
| Literals | numeric (`0`, `3.14`, `1e-6`), nested string literals (`'xy'`, `"AAA"`) |
| Comments | inline `# ...` to end of line |

### Theming

The injection assigns scadwright-specific scopes (e.g. `keyword.operator.optional.scadwright`) with secondary Python scopes as fallbacks (e.g. `storage.modifier.python`). Themes that don't know about the scadwright-specific scopes still render reasonable colors via the fallbacks. Themes that *want* to customize can target the `*.scadwright` scopes directly via `editor.tokenColorCustomizations` in VSCode settings:

```jsonc
"editor.tokenColorCustomizations": {
  "textMateRules": [
    {
      "scope": "keyword.operator.optional.scadwright",
      "settings": { "foreground": "#FF79C6", "fontStyle": "bold" }
    },
    {
      "scope": "support.function.cardinality.scadwright",
      "settings": { "foreground": "#FFB86C" }
    }
  ]
}
```

Run `Developer: Inspect Editor Tokens and Scopes` from the command palette and click any token in an `equations` block to see what scopes it carries — useful for pinning custom colors.

### Recognized scopes

| Custom scope | Fallback | Used for |
| --- | --- | --- |
| `keyword.operator.optional.scadwright` | `storage.modifier.python` | The `?` sigil |
| `keyword.operator.type-annotation.scadwright` | `punctuation.separator.annotation.python` | The `:` in a `:type` tag |
| `support.type.builtin.scadwright` | `support.type.python` | The type name in a `:type` tag (`int`, `bool`, …) |
| `keyword.operator.equation.scadwright` | `keyword.operator.assignment.python` | The lone `=` (equation operator, not Python assignment) |
| `support.function.cardinality.scadwright` | `support.function.builtin.python` | `exactly_one` / `at_least_one` / `at_most_one` / `all_or_none` |
| `support.function.math.scadwright` | `support.function.builtin.python` | Curated math functions |
| `support.function.builtin.scadwright` | `support.function.builtin.python` | Curated namespace builtins |
| `constant.language.scadwright` | `constant.numeric.python` | `pi`, `e`, `inf` |

### Limits

- TextMate grammars can't track bracket depth across lines, so a `:` inside a slice (`arr[start:int]`) or dict literal (`{i: ...}`) inside an equation may mis-color the word after the `:` as a type tag. The runtime scanner correctly suppresses tag recognition inside `[...]`/`{...}` — this is purely visual.
- This is highlighting, not validation or autocomplete. A typo in a cardinality helper (`exactlyone`) won't be flagged red; it surfaces at class-define time when the file imports. Autocomplete on Param names, go-to-definition for derived names, and validation would need a language server, which isn't shipped here.
