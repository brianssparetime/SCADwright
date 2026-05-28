# Project dependency graph

`scadwright graph PROJECT` walks a scadwright project and emits a dependency graph (Mermaid by default; also JSON and Graphviz DOT) showing how Components, Specs, and Designs relate. Useful for re-orienting on a project after time away, code review (does this change touch the components I expected?), refactoring (who reads this attribute?), and onboarding a collaborator.

The analyzer is fully static — it parses `.py` files via `ast.parse` and never imports user code. A scadwright project is everything reachable from the path you pass, recursing into subdirectories.

## Install

The `graph` subcommand is part of the base `scadwright` install — no extras needed.

## Usage

```
scadwright graph PATH [--format mermaid|json|dot] [--filter NAME] [--depth N]
```

`PATH` may be a directory (recursed) or a single Python file. The default `--format mermaid` writes Mermaid `graph TD` source to stdout — pipe into a renderer or paste into [mermaid.live](https://mermaid.live):

```
scadwright graph project/ > project-graph.mmd
scadwright graph project/ | mmdc -i - -o project-graph.svg
```

Single-file projects work too:

```
scadwright graph examples/electronics-case.py
```

For downstream tooling — custom dashboards, doc generators, diff tooling — `--format json` produces a structured payload:

```
scadwright graph project/ --format json
```

The JSON shape is two top-level keys, ``nodes`` and ``edges``. Each node has ``id``, ``label``, and ``kind``. Each edge has ``source``, ``target``, ``kind``, plus ``via_param`` (on ``uses_param`` edges) or ``attrs_read`` (on ``reads_attr`` edges) when relevant.

For larger projects where Mermaid layout suffers, `--format dot` produces Graphviz DOT source. Pipe through `dot` to render:

```
scadwright graph project/ --format dot | dot -Tsvg -o project-graph.svg
scadwright graph project/ --format dot | dot -Tpng -o project-graph.png
```

Graphviz's layout engines (`dot`, `neato`, `sfdp`) handle the geometry — the same shape vocabulary applies (diamond, rounded box, cylinder, hexagon).

## Focusing on one class: `--filter`

When the project has more nodes than fit comfortably on one diagram, `--filter NAME` narrows the output to one class plus its connected neighbourhood:

```
scadwright graph project/ --filter BatteryHolder
scadwright graph project/ --filter BatteryHolder --depth 1
scadwright graph project/ --filter main.BatteryHolder
```

`NAME` is the class name. If two classes in different modules share a name, pass the full dotted id (``module.ClassName``) — the error message lists the candidates when the bare name is ambiguous.

`--depth N` caps the radius. Hops count in either direction (Param-of, contains, inherits, etc. all count as one hop):

- `--depth 0` keeps only the focus node.
- `--depth 1` keeps the focus plus direct neighbours.
- Default (no `--depth`) keeps the full reachable subgraph from the focus.

`--depth` requires `--filter`; using it alone is an error.

## What you'll see

For a small project:

```python
# project/main.py
from scadwright import Component, Spec, Param

class BatterySpec(Spec):
    cells: int = Param(int, default=4)

class Holder(Component):
    spec = Param(BatterySpec)
    equations = "wall = spec.cells * 2"
    def build(self):
        return cube([self.spec.cells, 5, 5])
```

`scadwright graph project/` emits:

```
graph TD
  main_BatterySpec{BatterySpec}
  main_Holder(Holder)
  main_Holder --"cells"--> main_BatterySpec
  main_Holder --"Param(spec)"--> main_BatterySpec
```

Rendered:

- `BatterySpec` is a diamond (Spec).
- `Holder` is a rounded box (Component).
- `Holder --"Param(spec)"--> BatterySpec` shows the Param-typed dependency.
- `Holder --"cells"--> BatterySpec` shows attribute reads (combined from equations and `build()`).

Designs appear as cylinders, variants as hexagons. Inheritance edges appear with no label. Multiple attribute reads on the same target collapse into one labeled edge.

## Composition: `contains` edges

When a Component instantiates another Component, the graph emits a `"contains"` edge. Both shapes the design supports — class-attribute instantiation and `build()`-body instantiation — surface:

```python
class Inner(Component):
    pass

class Outer(Component):
    inner = Inner()           # class-attribute composition
    def build(self):
        return Inner(...)     # build()-body composition
```

```
graph TD
  main_Inner(Inner)
  main_Outer(Outer)
  main_Outer --"contains"--> main_Inner
```

In the `build()` body, the instantiation can sit anywhere — directly returned, nested in `union(...)` or `difference(...)`, inside conditionals, list comprehensions, or helper-function calls. Multiple instantiations of the same target collapse into one edge.

Curated factories (`cube`, `cylinder`, boolean ops) drop silently — they aren't project Components, so they don't surface as nodes or edges.

## Variants

`Design` classes get a node per `@variant`-decorated method. Each variant renders as a hexagon, linked to its Design by a `"variant"` edge, with `"builds"` edges to the Components the variant produces:

```python
from scadwright import variant, Component
from scadwright.design import Design

class Holder(Component):
    pass

class BatteryBox(Design):
    holder = Holder()

    @variant(default=True)
    def show(self):
        return self.holder
```

```
graph TD
  main_BatteryBox[(BatteryBox)]
  main_BatteryBox_show{{show}}
  main_Holder(Holder)
  main_BatteryBox --"variant"--> main_BatteryBox_show
  main_BatteryBox_show --"builds"--> main_Holder
```

Variant build-target detection picks up the patterns scadwright projects actually use:

- `return self.foo` — when `foo = SomeComponent()` at Design class scope.
- `return SomeComponent()` — direct instantiation in the variant body.
- `return union(self.a, self.b)` — both Components surface as build targets.
- `return helper(self.x)` — `self.x` resolves through the class-attribute map.

## Limitations

`scadwright graph` covers Component / Spec / Design class discovery, Param / equations / `build()` reads, composition, and variant analysis. The following aren't covered:

- **No abstract / concrete distinction.** All Components render with the same shape, regardless of whether they're directly instantiated anywhere.
- **Cross-project imports aren't followed.** A class whose base is in a third-party scadwright extension is categorized as `unknown` and omitted.
- **Dynamic dispatch isn't tracked.** `cls = A if flag else B; return cls()` can't be statically resolved; both branches drop unless they're each independently instantiated.

The runtime resolver isn't invoked, so equations that fail validation (typos, unknown function names, etc.) silently lose their attribute-read edges from the graph. The LSP catches those errors separately while you type.

## Troubleshooting

- **A file with a syntax error is skipped, with a stderr warning.** Classes defined in unparseable files don't appear in the graph; the warning lists each skipped file and the parse error so you know what's missing. Fix the syntax and re-run.
- **A class doesn't appear in the graph.** Confirm its base resolves to one of `scadwright.Component`, `scadwright.Spec`, or `scadwright.Design` — directly or via project-local intermediate classes. Bases imported from external packages categorize as `unknown` and drop the class.
- **Equation-derived edges are missing.** If equations don't validate (the LSP would mark them with squiggles), attribute-read edges from those equations are dropped. The rest of the graph still builds. Fix the validation error and re-run.
