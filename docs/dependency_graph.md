# Project dependency graph

`scadwright graph PROJECT` reads a scadwright project and prints how its parts relate: which Components draw on which Specs, what each Design builds, what reads what. The default output is a plain-text project map; `--format json` gives the same information as data. It's useful for re-orienting on a project after time away, confirming in review that a change touches only the parts you expected, and finding who reads a dimension before you rename it.

The analyzer is fully static: it reads your `.py` files without importing or running them, and needs no optional extras. The project is everything reachable from the path you pass, recursing into subdirectories.

Run it on a project and you get an outline grouped by what each thing is. Given:

```python
# project/main.py
from scadwright import Component, Spec, Param
from scadwright.design import Design, variant
from scadwright.primitives import cube

class BatterySpec(Spec):
    equations = "cells = 4"

class Holder(Component):
    spec = Param(BatterySpec)
    equations = "wall = spec.cells * 2"
    def build(self):
        return cube([self.spec.cells, 5, 5])

class Tray(Design):
    holder = Holder()

    @variant(default=True)
    def show(self):
        return self.holder
```

`scadwright graph project/` prints:

```
scadwright project: project
1 design, 1 component, 1 spec.

Designs
  Tray [main.py:15]
    Variant show (default)  builds Component  Holder

Components
  Holder [main.py:9]
    uses Spec        BatterySpec
    built by Design  Tray

Specs
  BatterySpec [main.py:6]
    read by Component
      cells  Holder
```

## Reading the map

The map groups the project's parts into Designs, Components, Specs, and Transforms; each section appears only when the project has something to put in it. Every part shows its source location in brackets, so `[main.py:9]` is where to go look.

Under each part are its relationships, named plainly and shown from both directions. A Component names the Spec it uses (`uses Spec`) and the Designs that build it (`built by Design`); a Spec lists which part reads each of its fields (`read by Component`); a Design lists what each variant builds. You read a Component to see what it depends on, and a Spec to see what depends on it — which is the question you actually have when you're about to change one.

A concrete part wears its base in parentheses, `PentaconSixBodyCap (a BodyCap)`, and the base shows `specialized by` in return. The remaining verbs read the same way: `contains Component` for one part building another, `uses Transform` for a custom verb. A list of more than three values breaks to one per line so a busy part stays readable.

### Specs shared across files

A reusable Component takes any Spec as a parameter, written `spec = Param()`, and reads values off it in its equations. A concrete subclass names the one Spec it uses, written `spec = PentaconSixMount`. The map hangs `uses Spec` off that subclass, not the base, because the subclass is where the Spec is chosen — the base names no particular Spec, so it shows none. This is what lets a graph confirm that two parts built from one shared Spec actually read it.

### Morphs

A morph — `name = morph(stages=[...])` on a Design — appears under its Design marked `Morph`. Every stage of a valid morph builds the same parts, so the map states those parts once and then lists the stages as a numbered sequence, the order being the animation. From the [pentacon-six-mount example](../examples/README.md):

```
  validation_morph [validation_morph.py:40]
    Variant faced             builds Component  PentaconSixBodyCap, PentaconSixRearLensCap
    Variant held              builds Component  PentaconSixBodyCap, PentaconSixRearLensCap
    Variant locked (default)  builds Component  PentaconSixBodyCap, PentaconSixRearLensCap
    Variant mated             builds Component  PentaconSixBodyCap, PentaconSixRearLensCap
    Variant spread            builds Component  PentaconSixBodyCap, PentaconSixRearLensCap
    Morph mate
      builds Component  PentaconSixBodyCap, PentaconSixRearLensCap
      uses Variant as stage
        1. spread
        2. faced
        3. mated
        4. locked
        5. held
```

The stages also appear above as variants in their own right, since each one renders on its own.

## Running it on a project

```
scadwright graph PATH [--format ascii|json] [--filter NAME] [--depth N] [--exclude PATTERN]
```

`PATH` is a directory (recursed) or a single `.py` file. The default writes the map to stdout, ready to read, redirect, or grep:

```
scadwright graph project/
scadwright graph project/ > project-map.txt
scadwright graph examples/electronics-case.py
```

### Focusing on one part: `--filter`

On a large project, `--filter NAME` narrows the map to one part plus its connected neighbourhood:

```
scadwright graph project/ --filter BatteryHolder
scadwright graph project/ --filter BatteryHolder --depth 1
```

`NAME` is the part's name. When two parts in different modules share a name, the map qualifies them with their module (`a.Part`, `b.Part`); pass that dotted form to pick one, and the error message lists the candidates when a bare name is ambiguous.

`--depth N` caps the radius, counting hops in either direction: `--depth 0` keeps only the focus part, `--depth 1` adds its direct neighbours, and the default keeps the whole reachable neighbourhood. `--depth` requires `--filter`.

### Excluding files: `--exclude`

`scadwright graph` walks the project in full. For a project that keeps historical snapshots, scratch sketches, or generated stubs alongside live code, `--exclude PATTERN` drops matching files before they enter the map:

```
scadwright graph project/ --exclude OLD
scadwright graph project/ --exclude OLD --exclude scratch
scadwright graph project/ --exclude 'OLD/2026-*'
```

A pattern without a `/` matches any single path segment, so `--exclude OLD` skips every file under a directory or named `OLD`, and `--exclude '*.test.py'` skips test files by suffix. A pattern with a `/` matches the file's project-relative path, so `--exclude OLD/2026-*` skips only the dated subdirs under `OLD`. Repeat the flag for more than one pattern; the built-in skips (`__pycache__`, `node_modules`, hidden directories) always apply.

## JSON output

`--format json` prints the same map as structured data — for doc generators, dashboards, diff tooling, or handing to an assistant:

```
scadwright graph project/ --format json
```

The shape mirrors the text: a top-level `project`, then `designs`, `components`, `specs`, and `transforms`, each an object keyed by part name. Every part carries its `location` and its relationships, with each read field listed in full:

```json
{
  "components": {
    "Holder": {
      "location": "main.py:9",
      "uses_spec": [
        {"spec": "BatterySpec", "via_param": "spec", "reads": ["cells"]}
      ]
    }
  }
}
```

Each relationship is stored once, on the part that owns it — a Component's `uses_spec`, a Design's `builds`. The reverse views the text map shows (`read by`, `built by`) aren't duplicated here; they invert from the forward data. So the JSON keeps one source of truth and diffs cleanly across runs.

## What it covers, and what it doesn't

The map finds Component, Spec, Design, and Transform classes and the relationships among them: inheritance, the Spec or Component a part takes as a Param and the fields it reads, one Component building another, what each variant and morph builds, and custom-transform use. Detection follows the shapes scadwright projects actually use — composition anywhere in a method body, a variant that delegates to a helper, a morph's stages — and collapses repeats into a single relationship.

Some things static analysis can't see:

- **Cross-project bases.** A class whose base lives in a third-party scadwright extension can't be categorized, so it drops from the map.
- **Dynamic dispatch.** `cls = A if flag else B; return cls()` can't be resolved; neither branch surfaces unless it's also built directly somewhere.
- **Transforms named at runtime.** `@transform(name_var)` or `register(name_var, ...)` with a non-literal name can't be read statically, so the transform and any calls to it drop.
- **Star-imported transforms.** `from project_transforms import *` binds names at runtime, so a file that calls one through a star import shows no `uses Transform`.

## Troubleshooting

- **A file with a syntax error is skipped.** A stderr warning names the file and the parse error; classes in it won't appear. Fix the syntax and re-run.
- **A part is missing.** Its base has to resolve to `Component`, `Spec`, or `Design` — directly or through project-local intermediates. A base imported from an external package drops the class.
- **A variant reads `no parts traced`.** Its return doesn't resolve to a project Component: it builds only primitives, or uses a pattern beyond direct instantiation, a `self.part` attribute, or delegation to a helper method. Read the variant to see what it makes.
- **An equation's reads are missing.** The equations block doesn't validate (the LSP would mark it); its attribute reads drop while the rest of the map still builds. Fix the validation error and re-run.
- **A transform call shows no `uses Transform`.** The chained `.X(...)` isn't a registered project transform — `X` is a built-in verb (`.translate`, `.rotate`), an unrelated method, or a typo. Confirm the project defines `@transform("X")`, a `Transform` subclass with `name = "X"`, or `register("X", ...)` with a literal name.
