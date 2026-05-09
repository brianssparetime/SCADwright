# LSP setup

SCADwright bundles a language server that surfaces six editor features for `equations = """..."""` blocks:

- **Inline diagnostics** for every error the resolver raises at class-definition time — unknown function names, type-tag disagreements, mutual inconsistency, malformed adjustments, comma-broadcast mistakes, override-pattern unsafety, and so on. Errors appear as squiggles while you type, not after you run the script.
- **Completion** at expression position (the curated math / builtins namespace, the surrounding class's `Param` declarations, and bare-Name targets declared on earlier equation lines), after `:` (the inline type-tag allowlist), and after `.` (a Component-typed Param's own `Param` names — same-file only). Callable completions auto-insert parentheses.
- **Hover** on any name in an equations block: curated functions show signatures and brief descriptions; `Param`-declared names show their type, default, and `doc=` text; auto-declared targets show the equation line where they were first introduced.
- **Goto-definition** on any name in an equations block: jumps to the `name = Param(...)` assignment for declared Params, or to the equation line that first introduces an auto-declared bare-Name target.
- **Document symbols** for each Component class with an equations block: the outline view shows one entry per class with its declared Params nested underneath, so the file structure of a parametric model is scannable from the sidebar.
- **Rename refactoring** on any renameable name inside an equations block: updates the `Param` assignment if applicable, every reference inside the same class's equations strings, AND cross-file references of the form `<param_name>.<old_name>` (in equations) or `self.<param_name>.<old_name>` (in `build()` bodies) in any other Component holding a `Param` of the source class. Single workspace edit, same-file-only when the editor hasn't supplied a workspace folder.

The server is the same code path the runtime uses, just invoked statically. No user code is imported — the analyzer parses the source via `ast.parse` and walks for `equations = ...` assignments.

## Install

```
pip install 'scadwright[lsp]'
```

The `[lsp]` extra pulls in `pygls` and `sympy`. Once installed, the `scadwright lsp` subcommand is on your PATH and serves the LSP protocol over stdio.

To smoke-test, run it in a terminal — it will block waiting for LSP messages on stdin. Ctrl-C exits.

## Editor configs

Configure your editor's LSP client to spawn `scadwright lsp` for Python files. Several common editors:

### Neovim (`nvim-lspconfig`)

```lua
local lspconfig = require("lspconfig")
local configs = require("lspconfig.configs")

if not configs.scadwright then
  configs.scadwright = {
    default_config = {
      cmd = { "scadwright", "lsp" },
      filetypes = { "python" },
      root_dir = lspconfig.util.root_pattern("pyproject.toml", ".git"),
      single_file_support = true,
    },
  }
end

lspconfig.scadwright.setup({})
```

If you use a project venv, point `cmd` at the venv's binary instead:

```lua
cmd = { vim.fn.getcwd() .. "/.venv/bin/scadwright", "lsp" },
```

### Vim (`vim-lsp`)

```vim
if executable('scadwright')
  augroup lsp_scadwright
    autocmd!
    autocmd User lsp_setup call lsp#register_server({
        \ 'name': 'scadwright',
        \ 'cmd': ['scadwright', 'lsp'],
        \ 'allowlist': ['python'],
        \ })
  augroup END
endif
```

### Helix (`languages.toml`)

In `~/.config/helix/languages.toml`:

```toml
[language-server.scadwright]
command = "scadwright"
args = ["lsp"]

[[language]]
name = "python"
language-servers = [{ name = "scadwright" }, "pylsp"]
```

The list form lets `scadwright` run alongside whatever Python LSP you already have configured (here `pylsp`; substitute `pyright` or `ruff-lsp` as appropriate).

### Emacs (`eglot`)

```elisp
(with-eval-after-load 'eglot
  (add-to-list 'eglot-server-programs
               '(python-mode . ("scadwright" "lsp")))
  ;; Or, alongside another Python server:
  ;; '(python-mode . ("pyright" "scadwright"))  ; requires eglot-x
  )
```

`eglot` only runs one server per language by default; use `eglot-x` if you want to run both `scadwright` and another Python LSP.

### Emacs (`lsp-mode`)

```elisp
(with-eval-after-load 'lsp-mode
  (lsp-register-client
   (make-lsp-client
    :new-connection (lsp-stdio-connection '("scadwright" "lsp"))
    :major-modes '(python-mode)
    :server-id 'scadwright
    :add-on? t)))
```

`:add-on? t` makes `lsp-mode` run `scadwright` alongside (rather than instead of) your primary Python server.

### Sublime Text (LSP package)

In Preferences → LSP → Settings:

```json
{
  "clients": {
    "scadwright": {
      "enabled": true,
      "command": ["scadwright", "lsp"],
      "selector": "source.python"
    }
  }
}
```

### Zed

In `~/.config/zed/settings.json`:

```json
{
  "lsp": {
    "scadwright": {
      "binary": {
        "path": "scadwright",
        "arguments": ["lsp"]
      }
    }
  },
  "languages": {
    "Python": {
      "language_servers": ["scadwright", "..."]
    }
  }
}
```

The `"..."` keeps Zed's default Python servers active alongside `scadwright`.

### VSCode

VSCode users already have the SCADwright extension (which provides a TextMate grammar for coloring inside `equations = """..."""`). The LSP can be configured alongside, but the existing extension does not spawn it automatically; consult the extension's README if you want to point at a specific Python interpreter for runtime tasks.

### PyCharm / IntelliJ

PyCharm Community has no built-in LSP client; the SCADwright PyCharm plugin already provides coloring, completion, and toolbar actions natively. PyCharm Professional does have an LSP client and can be configured to spawn `scadwright lsp`, but the native plugin's PSI integration is deeper than LSP can reach today, so most users keep the native plugin.

## What you'll see

### Diagnostics

For a file like:

```python
class Bracket(sc.Component):
    equations = """
    width, height > 0
    h = snh(width)        # typo: should be sin
    """
```

The LSP marks `snh` on the second equation line with an error: `Bracket.equations[1]: cannot parse equation 'h = snh(width)': unknown function 'snh' (not a Param, equation target, or curated math/builtin name)`. The squiggle hugs the offending token where the validator captures a specific AST node; whole-equation errors (chained `=`, self-referential equations, mutual inconsistency) squiggle the whole logical line. The editor's diagnostic UI shows the full message on hover or in a problems panel.

Diagnostics update on every keystroke (debounced by the editor's LSP client). Closing a file clears its diagnostics.

### Completion

At expression position the suggestion list combines:

- The **curated namespace**: math functions (`sin`, `cos`, `sqrt`, ...), builtins (`len`, `min`, `max`, `int`, `str`, ...), cardinality helpers (`exactly_one`, `at_least_one`, ...), and constants (`pi`, `e`, `True`, `False`, `None`).
- The **surrounding class's `Param` declarations**, with the compact `Param(...)` signature in the detail field and any literal `doc=` text in the documentation popup.
- **Auto-declared bare-Name targets** from earlier equation lines (the names the resolver would auto-declare as `Param(float)` at class-define time), tagged `auto-declared`.

Selecting a callable inserts `name()` and parks the caret inside the parens (the snippet uses LSP's standard placeholder syntax; clients without snippet support fall back to the literal text).

Typing `:` after a name (or `?name:`) triggers type-tag completion — the closed list `bool`, `int`, `str`, `tuple`, `list`, `dict`. The `:` is registered as a completion trigger character so the list pops automatically.

Typing `.` after a name triggers cross-Component attribute completion: if the base name is declared as `b = Param(B)` and class `B` lives in the same file with its own equations block, the suggestion list is `B`'s Params, with each entry's `Param(...)` signature in the detail field. Same-file only — cross-file resolution would need workspace import-graph walking that's deferred. Bases whose type can't be resolved against the current file produce no suggestions.

### Hover

Hovering on a name in an equations block surfaces:

- **Curated names**: signature plus a one-sentence description (`sin(x)` shows "sine of `x` in degrees", `exactly_one(*args)` calls out its use with the `?` sigil).
- **`Param` declarations**: the compact `Param(...)` signature and the literal `doc=` text when present.
- **Auto-declared targets**: a note that the name was first introduced on equations-line *N* (matching the runtime's `equations[N]` numbering in error messages).
- **Type-tag names** (when hovered after `:`): the inline-annotation form.

### Goto-definition

Triggering goto-definition (`gd` in many editors, `Ctrl+Click` / `Cmd+Click` in others) on a name inside an equations block:

- A class-declared `Param` jumps to its `name = Param(...)` assignment line.
- An auto-declared bare-Name target jumps to its first occurrence as an equation target — even when that occurrence appears later in the block, since the runtime sees all targets uniformly.
- Curated names (`sin`, `pi`, ...) yield no location; the editor falls back to its Python LSP or shows nothing.

### Document symbols

The outline view (often a sidebar; `Ctrl+Shift+O` in some clients, `:lua vim.lsp.buf.document_symbol()` in Neovim) lists one entry per Component class with an equations block, with each `Param` declaration as a child. Selecting a Param jumps to its assignment line; the detail line shows the compact `Param(...)` signature so you can scan a class's parameters without scrolling. Plain Python classes that don't define an `equations` attribute are not duplicated — your editor's Python LSP already surfaces those.

### Undeclared attribute-base warning

When an equation reads an attribute off a name that isn't declared as a `Param` of the surrounding class — for example `x = b.outer_d` with no matching `b = Param(B)` — the LSP marks the offending name with a warning: *"`b.outer_d` reads an attribute of `b`, but `b` isn't declared as a Param of this Component. ..."*. The runtime currently only surfaces this at solve time as part of the `cannot solve...` error message; the LSP raises the same observation while you type.

### Rename

Triggering rename (`F2` in many editors, `<leader>rn` in some Vim setups) on a name inside an equations block produces a single workspace edit covering:

- The `name = Param(...)` (or `name: T = Param(...)`) assignment line, if the target is a declared Param. Just the name token is replaced; the rest of the assignment statement stays put.
- Every occurrence of the name inside any of the surrounding class's equation, rule, and adjustment lines — including the LHS of an adjustment.
- Cross-file: every other Component or Spec in the project that holds a `Param` whose type resolves to the source class. References of the form `<param_name>.<old_name>` (in equations strings) or `self.<param_name>.<old_name>` (in `build()` method bodies) are rewritten in place. The editor's workspace folders define the project scope; rename degrades to same-file when the editor hasn't supplied any.

Curated names (`sin`, `pi`, ...) and inline type-tag names (`bool`, `int`, ...) are refused — the LSP doesn't own those identifiers. Renaming to a name that would collide with the curated namespace is also refused. If the equations block fails validation, rename is refused too: any edits we emit could be misaligned against an unparseable text.

## Limitations

- Only `equations` blocks are analyzed. Errors elsewhere in the file are not surfaced by `scadwright lsp` — your editor's regular Python server (Pyright, Pylance, ruff-lsp, etc.) handles those.
- Cross-file attribute completion (typing `b.` to see B's Params) is same-file only — cross-file Param-type inference requires walking the project, similar to rename's cross-file pass, but isn't implemented yet.
- The LSP does not evaluate the iterative resolver, so runtime-only errors (`cannot solve…`, `equation violated`, supplied-vs-missing kwargs) only appear when the script actually runs.

## Troubleshooting

- **`scadwright: error: scadwright lsp requires the 'lsp' extra`** — install with `pip install 'scadwright[lsp]'`.
- **Editor says LSP failed to start** — verify `scadwright lsp` is on the PATH the editor uses. Try the absolute path to the venv's binary.
- **No diagnostics appear on a file with a known error** — confirm the file is recognized as Python (`.py` extension) and that the editor's LSP client is talking to `scadwright`. Open the editor's LSP-server log panel: errors from the analyzer surface there as `window/logMessage` notifications.
