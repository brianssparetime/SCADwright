# SCADwright VSCode extension

Three things this extension does:

1. **Language server**: spawns `scadwright lsp` to provide diagnostics, completion, hover, goto-definition, document symbols, and rename for `equations = """..."""` blocks. Errors appear as squiggles while you type, completion offers Param names and the curated math/builtins namespace, hover shows declared types and defaults.
2. Adds **Kill / Preview / Render** icons to the editor title bar, so you can build and view a scadwright script without leaving VSCode.
3. Colors the small equation language inside `equations = """..."""` blocks, so the `?` sigils, `:type` tags, math functions, and operators show up with their own colors instead of all looking like one string.

The extension activates on any Python file. The icons only appear on files that have `import scadwright` or `from scadwright …`. The coloring only fires on assignments to the literal name `equations` at the start of a line. The language server runs in the background on every Python file; it's harmless on non-scadwright files (no `equations` block → no diagnostics).

## Install

The language server requires the `[lsp]` extra in your project's Python environment:

```
pip install 'scadwright[lsp]'
```

The extension uses `vscode-languageclient` from npm. Install it once before packaging or symlinking:

```
cd vscode
npm install
```

Then choose one of:

### Option A: symlink (good for trying it out)

Drops the live folder into VSCode's extensions directory. Edits to the extension take effect on the next "Reload Window," no build step needed.

```
ln -s "$(pwd)/vscode" "$HOME/.vscode/extensions/scadwright-local.scadwright-vscode-0.2.0"
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
code --install-extension scadwright-vscode-0.2.0.vsix
```

Reload VSCode.

If you'd rather not install `vsce` globally, `npx @vscode/vsce package` works too.

### Skipping the language server

If you only want the toolbar and coloring, set `scadwright.lsp.enable` to `false` in your VSCode settings. The extension then runs in TextMate-only mode and the `npm install` step isn't strictly required (the require for `vscode-languageclient` is wrapped — it'll log a warning and continue).

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| `scadwright.scadwrightCommand` | `scadwright` | Command to invoke for the SCADwright CLI. Use a full path if it isn't on `PATH`. The LSP uses the same command unless `scadwright.lsp.enable` is `false`. |
| `scadwright.openscadCommand` | `openscad` | Command to invoke OpenSCAD. |
| `scadwright.variant` | `""` | Variant passed to `scadwright build --variant=…`. Empty means no flag. |
| `scadwright.saveBeforeBuild` | `true` | Save the active file before running `scadwright build`. |
| `scadwright.lsp.enable` | `true` | Run the SCADwright language server. Set to `false` for TextMate-only mode (toolbar and coloring only, no diagnostics or completion). |
| `scadwright.lsp.trace.server` | `off` | Log JSON-RPC traffic between VSCode and the language server. Set to `messages` or `verbose` when reporting LSP issues. Output appears in the SCADwright output channel. |

The language server's binary is auto-discovered. If you set `scadwright.scadwrightCommand` (in workspace, user, or folder settings), the LSP uses that path. Otherwise, it looks for `<workspaceRoot>/.venv/bin/scadwright` (or `.venv\Scripts\scadwright.exe` on Windows) before falling back to `scadwright` on `PATH`. The first-found binary wins across multi-root workspaces.

## What the language server provides

While editing an `equations = """..."""` block:

- **Diagnostics**: every error the resolver raises at class-definition time (unknown function names, type-tag disagreements, mutual inconsistency, malformed adjustments, comma-broadcast mistakes, override-pattern unsafety) appears as a squiggle on the offending range, with the same message the runtime would print.
- **Completion** at expression position (curated math/builtins, the surrounding class's `Param` declarations, bare-Name targets declared on earlier equation lines), after `:` (the inline type-tag allowlist), and after `.` (a Component-typed Param's own `Param` names — same-file only). Callables auto-insert parentheses.
- **Hover** on any name: curated functions show signatures and brief descriptions; `Param`-declared names show their type, default, and `doc=` text; auto-declared targets show the equation line where they were first introduced.
- **Goto-definition** on any name: jumps to the `name = Param(...)` assignment for declared Params, or to the equation line that first introduces an auto-declared bare-Name target.
- **Document symbols** for outline view: each Component class with an equations block shows its declared Params nested underneath.
- **Rename** on any renameable name: updates the `Param` assignment if applicable plus every reference inside the same class's equations strings, in one workspace edit.

The language server runs on every Python file but only does work when it sees an `equations = ...` assignment. No user code is imported — the server parses the source via `ast.parse`, the same surface the runtime resolver uses.

If pygls isn't installed (or `scadwright[lsp]` hasn't been pip-installed), the language server fails to start and a one-time install hint appears in the SCADwright output channel. The toolbar icons and coloring keep working regardless.

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

The TextMate grammar provides only the coloring layer; semantic features (validation, autocomplete on parameter names, goto-definition, hover, rename) come from the language server, which understands the equations DSL the same way the runtime does. With the language server enabled, a typo in a cardinality helper surfaces as an inline squiggle while you type, not just at import time.
