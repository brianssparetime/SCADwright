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
| `scadwright.scadwrightCommand` | `scadwright` | Command to invoke for the scadwright CLI. Use a full path if it isn't on `PATH`. |
| `scadwright.openscadCommand` | `openscad` | Command to invoke OpenSCAD. |
| `scadwright.variant` | `""` | Variant passed to `scadwright build --variant=…`. Empty = no flag. |
| `scadwright.saveBeforeBuild` | `true` | Save the active file before running `scadwright build`. |

## Activation

The extension activates on any Python file. The icons only appear when the open file matches `import scadwright` / `from scadwright …`. Editing in or out of that pattern updates the icons live.

## How it works

- **Preview**: shells out to `scadwright preview <file.py>`, which builds the script's `MODEL` to a stable temp `.scad` file (keyed on the script + variant) and launches OpenSCAD on it. Re-clicking Preview overwrites the same temp file, so an already-open OpenSCAD window auto-reloads the change.
- **Render**: shells out to `scadwright render <file.py>`, which builds to a temp `.scad` and then invokes `openscad -o <file>.stl` headless. Output streams to the SCADwright channel.
- **Kill**: `pkill -f openscad` (or `taskkill /F /IM openscad.exe` on Windows).
