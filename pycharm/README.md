# SCADwright PyCharm plugin

Editor-toolbar actions to preview, render, and kill OpenSCAD for the active scadwright Python script, plus syntax coloring and autocomplete inside `equations = """..."""` blocks. Same three commands the VSCode extension provides; same settings; same gating (the actions are enabled only on Python files that import scadwright). The equations highlighting goes a step beyond the VSCode extension by adding autocomplete on top of coloring.

## What's here today

- **Preview** runs `scadwright preview <file.py>` and opens the result in OpenSCAD.
- **Render** runs `scadwright render <file.py>` and writes an STL.
- **Kill OpenSCAD** stops any running OpenSCAD process.
- A Settings → Tools → SCADwright pane with the same four configurables as the VSCode extension.
- Syntax coloring inside `equations = """..."""` and `equations = ["..."]` blocks: numbers, strings, comments, the `?` optional sigil, the `:type` tag, the curated namespace (math functions, builtins, cardinality helpers, type names, constants), and the equation/comparison/arithmetic operators.
- Autocomplete inside the same blocks: type names after `:`, and the curated namespace (math/builtin/cardinality functions get auto-paren insertion) at expression position.

Action output streams into a "SCADwright" tool window at the bottom of the IDE.

## Build and install

You'll need a JDK 17 to build. On macOS without Xcode (which Homebrew's openjdk requires), the path of least resistance is downloading the Eclipse Temurin tarball directly:

```
mkdir -p ~/.local/opt && cd ~/.local/opt
curl -L -o temurin17.tar.gz "https://api.adoptium.net/v3/binary/latest/17/ga/mac/aarch64/jdk/hotspot/normal/eclipse?project=jdk"
tar -xzf temurin17.tar.gz
export JAVA_HOME=$HOME/.local/opt/jdk-17.0.19+10/Contents/Home
```

Replace `aarch64` with `x64` if you're on Intel macOS. The exact `jdk-17.0.X+Y` directory name will vary; `ls ~/.local/opt | grep jdk` shows what extracted.

With `JAVA_HOME` set, build the plugin:

```
cd pycharm
./gradlew buildPlugin
```

The first run downloads the IntelliJ Platform SDK (~600MB) and takes a few minutes. Subsequent builds are seconds.

The output is `pycharm/build/distributions/scadwright-pycharm-0.2.0.zip`. Install it in PyCharm:

1. **Settings** → **Plugins** → gear icon → **Install Plugin from Disk…**
2. Pick the `scadwright-pycharm-0.2.0.zip` file.
3. Restart PyCharm when prompted.

After restart, the three icons (Preview, Render, Kill OpenSCAD) appear in the main toolbar (top-right of the IDE), enabled when you have a Python file open that imports scadwright. They're also available via the editor right-click menu and the Tools menu.

## Iterating during development

Instead of rebuilding the .zip and reinstalling each time, use the Gradle wrapper's sandbox:

```
cd pycharm
./gradlew runIde
```

This launches a fresh PyCharm instance with the plugin already loaded. Edits to the source require quitting the sandbox and re-running `runIde`. The first launch is slow (several minutes); subsequent launches are faster.

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| scadwright command | `scadwright` | Command to invoke for the SCADwright CLI. Use a full path if it isn't on `PATH`. |
| openscad command | `openscad` | Command to invoke OpenSCAD. |
| Variant | (empty) | Variant passed to `scadwright build --variant=…`. Empty means no flag. |
| Save active file before invoking scadwright build | on | If on, every Preview / Render saves the active file first. |

Find them at **Preferences** → **Tools** → **SCADwright**.

## What the icons do

Each action runs an external command and streams its output to a "SCADwright" tool window pinned to the bottom of the IDE. Each click adds a fresh tab so consecutive runs stay inspectable side by side.

- **Preview** runs `scadwright preview <file.py>`, which builds the script's `MODEL` to a stable temp `.scad` file (keyed on script and variant) and launches OpenSCAD on it. Clicking Preview again overwrites the same temp file, so an already-open OpenSCAD window auto-reloads.
- **Render** runs `scadwright render <file.py>`, which builds to a temp `.scad` and then invokes `openscad -o <file>.stl` headlessly.
- **Kill OpenSCAD** runs `pkill -f openscad` (or `taskkill /F /IM openscad.exe` on Windows). Best-effort; doesn't open a tool window.

The actions are gated: they only enable when the active editor is a Python file containing `import scadwright` or `from scadwright …` at line start. Other Python files leave the toolbar buttons greyed out.

## Equations highlighting and autocomplete

Inside any Python file, an assignment of the form

```python
equations = """
    name :type = value
    ?optional_name = default
    a + b == c
"""
```

(or the list-of-strings form `equations = ["a = 1", "b = 2"]`) gets treated as the scadwright equations DSL: the contents are parsed by a separate lexer, colored token-by-token, and offer code completion on Ctrl+Space.

What it knows about:

- **Numbers, strings, comments**: standard literal coloring.
- **Optional sigil** (`?`): a name prefixed with `?` is colored as a metadata modifier, marking it as a Param declaration.
- **Type tag** (`:bool`, `:int`, `:str`, `:tuple`, `:list`, `:dict`): inline type annotations on Param names color as type metadata.
- **Curated namespace**:
  - Math functions: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `sqrt`, `log`, `exp`, `abs`, `ceil`, `floor`, `min`, `max`, `sum`, `round`, `degrees`, `radians`.
  - Builtins: `range`, `tuple`, `list`, `dict`, `set`, `frozenset`, `zip`, `enumerate`, `len`, `int`, `float`, `bool`, `str`, `all`, `any`, `sorted`, `reversed`, `isinstance`.
  - Cardinality helpers: `exactly_one`, `at_least_one`, `at_most_one`, `all_or_none`.
  - Constants: `True`, `False`, `None`, `pi`, `e`, `inf`.
- **Keywords**: `if`, `else`, `for`, `in`, `is`, `and`, `or`, `not`.
- **Operators**: `=`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `+`, `-`, `*`, `/`, `//`, `%`, `**`.

Autocomplete behavior:

- After `:` (and optional whitespace), only the six type names are suggested.
- At expression position (anywhere else inside the block), all five categories of the curated namespace are suggested, plus the keywords. Math/builtin/cardinality entries auto-insert `()` and place the caret between the parens.

Identifiers outside the curated namespace (your own Param names) get the editor's default text color and aren't auto-completed; cross-line name awareness inside an equations block isn't there yet and would need a real parser to do well.
