# SCADwright VSCode extension

Two things this extension does:

1. Adds **Kill / Preview / Render** icons to the editor title bar, so you can build and view a scadwright script without leaving VSCode.
2. Colors the small equation language inside `equations = """..."""` blocks, so the `?` sigils, `:type` tags, math functions, and operators show up with their own colors instead of all looking like one string.

The extension activates on any Python file. The icons only appear on files that have `import scadwright` or `from scadwright …`. The coloring only fires on assignments to the literal name `equations` at the start of a line.

## Install

Two options.

### Option A: symlink (good for trying it out)

Drops the live folder into VSCode's extensions directory. Edits to the extension take effect on the next "Reload Window," no build step needed.

```
ln -s "$(pwd)/vscode" "$HOME/.vscode/extensions/scadwright-local.scadwright-vscode-0.1.0"
```

Then in VSCode: `Cmd+Shift+P` → `Developer: Reload Window`. To remove later, delete the symlink and reload the window.

### Option B: package and install

You'll need `vsce`:

```
npm install -g @vscode/vsce
```

Then:

```
cd vscode
vsce package
code --install-extension scadwright-vscode-0.1.0.vsix
```

Reload VSCode.

If you'd rather not install `vsce` globally, `npx @vscode/vsce package` works too.

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| `scadwright.scadwrightCommand` | `scadwright` | Command to invoke for the SCADwright CLI. Use a full path if it isn't on `PATH`. |
| `scadwright.openscadCommand` | `openscad` | Command to invoke OpenSCAD. |
| `scadwright.variant` | `""` | Variant passed to `scadwright build --variant=…`. Empty means no flag. |
| `scadwright.saveBeforeBuild` | `true` | Save the active file before running `scadwright build`. |

## What the icons do

- **Kill OpenSCAD**: stops any running `openscad` process. Handy when a preview window is stuck.
- **Preview**: runs `scadwright preview <file.py>`, which builds the script's `MODEL` to a temporary `.scad` file (keyed on the script and variant) and launches OpenSCAD on it. Clicking Preview again overwrites the same temp file, so an already-open OpenSCAD window auto-reloads.
- **Render**: runs `scadwright render <file.py>`, which builds to a temp `.scad` and then invokes `openscad -o <file>.stl` headlessly to produce an STL.

## Coloring inside `equations` blocks

Inside a Component class, an `equations = """..."""` block (or the list form `equations = [...]`) carries scadwright's small equation language. The extension picks out the equation-language elements on top of the regular Python coloring:

| Element | Examples |
| --- | --- |
| Optional sigil | `?fillet`, `?count`, `?direction:bool` |
| Inline `:type` tag | `count:int`, `axis:str`, `len(size:tuple)` |
| Cardinality helpers | `exactly_one(?fillet, ?chamfer)`, `at_least_one(...)`, `at_most_one(...)`, `all_or_none(...)` |
| Math functions | `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `sqrt`, `log`, `exp`, `abs`, `ceil`, `floor`, `min`, `max`, `sum`, `round`, `degrees`, `radians` |
| Builtins | `range`, `tuple`, `list`, `dict`, `set`, `frozenset`, `zip`, `enumerate`, `len`, `int`, `float`, `bool`, `str`, `all`, `any`, `sorted`, `reversed` |
| Constants | `pi`, `e`, `inf`, `True`, `False`, `None` |
| Operators | `=` (the lone equation operator), `==`, `!=`, `<`, `<=`, `>`, `>=`, arithmetic (`+ - * / // % **`), boolean (`and`, `or`, `not`), conditional (`if`, `else`), membership and identity (`in`, `not in`, `is`, `is not`) |
| Literals | numbers (`0`, `3.14`, `1e-6`), strings (`'xy'`, `"AAA"`) |
| Comments | inline `# ...` to end of line |

The coloring is contextual: it triggers only on assignments to the literal name `equations` at the start of a line. Docstrings, regular triple-quoted strings, and `self.equations = ...` assignments are left alone.

### Picking different colors

The extension assigns each equation-language element two color names. The first is scadwright-specific (for example, `keyword.operator.optional.scadwright`); the second is a Python equivalent that themes already know how to color (for example, `storage.modifier.python`). Themes that don't know about the scadwright names still render reasonable colors via the Python ones. To customize, target the `*.scadwright` names directly in your VSCode settings:

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

To find the color name for any specific token, run `Developer: Inspect Editor Tokens and Scopes` from the command palette and click the token. The popup lists every name attached to it.

### Color names by element

| Element | scadwright name | Python fallback |
| --- | --- | --- |
| The `?` sigil | `keyword.operator.optional.scadwright` | `storage.modifier.python` |
| The `:` in a `:type` tag | `keyword.operator.type-annotation.scadwright` | `punctuation.separator.annotation.python` |
| The type name (`int`, `bool`, …) | `support.type.builtin.scadwright` | `support.type.python` |
| The lone `=` equation operator | `keyword.operator.equation.scadwright` | `keyword.operator.assignment.python` |
| `exactly_one` / `at_least_one` / `at_most_one` / `all_or_none` | `support.function.cardinality.scadwright` | `support.function.builtin.python` |
| Math functions | `support.function.math.scadwright` | `support.function.builtin.python` |
| Builtins | `support.function.builtin.scadwright` | `support.function.builtin.python` |
| `pi`, `e`, `inf` | `constant.language.scadwright` | `constant.numeric.python` |

### Limits

The coloring can't always tell when a `:` inside an equation belongs to a slice (`arr[start:int]`) or a dict key (`{i: ...}`) versus a `:type` tag, so a slice or dict-key colon followed by an identifier may briefly color the identifier as if it were a type tag. The actual equation parser handles this correctly; the visual mismatch is cosmetic.

The extension provides coloring only. Validation, autocomplete on parameter names, and go-to-definition would need additional tooling beyond what coloring can do. A typo in a cardinality helper still surfaces when the file imports, with a clear error pointing at the offending line.
