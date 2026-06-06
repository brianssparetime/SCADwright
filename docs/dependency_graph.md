# Project dependency graph

`scadwright graph PROJECT` walks a scadwright project and emits a dependency graph (plain-text ASCII by default; also Mermaid, JSON, and Graphviz DOT) showing how Components, Specs, Designs, and Transforms relate. Useful for re-orienting on a project after time away, confirming in review that a change touches only the components you expected, and finding who reads an attribute before a refactor.

The analyzer is fully static: it reads your `.py` files without importing or running them, and needs no optional extras. A scadwright project is everything reachable from the path you pass, recursing into subdirectories.

Run it on a project and you get a node-and-edge map you can read in a terminal or grep. Given:

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

`scadwright graph project/` emits the default ASCII format:

```
# scadwright graph: project  (2 nodes, 2 edges, 0 warnings)

## nodes
component  main.Holder  main.py:6
spec       main.BatterySpec  main.py:2

## edges
main.Holder
  reads_attr      main.BatterySpec  [cells]
  uses_param      main.BatterySpec  (via spec)

## warnings
(none)
```

## Reading the output

The output has three sections (`## nodes`, `## edges`, `## warnings`) under a one-line header that summarizes counts. Each node line carries the node's kind, dotted id, and source location (`path:line`). Edge lines sit indented under each source, naming the edge kind, the target id, and any extras (`[cells]` for attribute reads, `(via spec)` for the Param a dependency flows through). The format is deterministic line by line, so diffs across runs read cleanly, and you can grep the output for a class's id to find every reference to it.

Two edge kinds carry a Spec or Component dependency. `uses_param` marks a Param whose type resolves to a project class. `reads_attr` marks attribute access, merged into one labeled edge per source-and-target pair from three places: equation references, `self.<param>.<attr>` reads in any method body, and direct class-attribute reads like `BatterySpec.cells`.

These edges span files. A reusable base can take any Spec as a parameter, written `spec = Param()`, and read values off it in the equations. A concrete subclass names the one Spec it uses, written `spec = MountInterface`. The graph draws `uses_param` and `reads_attr` from that subclass to the Spec, because the subclass is where the Spec is chosen. The base names no particular Spec, so it gets none.

## What the graph captures

Beyond the Param and attribute dependencies above, the graph traces composition, custom-transform use, and variant builds. In the Mermaid and DOT renderings, each kind of node has its own shape: Specs are diamonds, Components rounded boxes, Designs cylinders, variants hexagons, and project-registered transforms parallelograms.

### Composition (`contains`)

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

The instantiation can sit anywhere in a method body — returned, nested in a boolean op, or built in a helper — and repeated instantiations of the same target collapse into one edge. Curated factories (`cube`, `cylinder`, boolean ops) aren't project Components, so they don't surface as nodes or edges.

### Custom transforms (`uses`)

A project that registers a transform gets a parallelogram node. Two registration shapes count: a free function with the `@transform("name")` decorator, and a `Transform` subclass with a `name = "..."` class attribute. Components, transforms, and variant methods that invoke a registered transform via a chained call `<expr>.<name>(...)` get a `"uses"` edge to the parallelogram:

```python
from scadwright.transforms import transform
from scadwright import Component
from scadwright.primitives import cube

@transform("port_cutout")
def port_cutout(node, *, on, width):
    return node

class Case(Component):
    def build(self):
        body = cube([40, 30, 10], center="xy")
        return body.port_cutout(on="+x", width=10)
```

```
graph TD
  main_Case(Case)
  main_port_cutout[/port_cutout/]
  main_Case --"uses"--> main_port_cutout
```

A chained call collapses into one `"uses"` edge per source-and-target pair, wherever it sits in a method body. Three more details:

- Transforms participate in `reads_attr` and `contains` themselves: a transform that reads a Spec's class attribute or instantiates a Component shows those edges outgoing from its own parallelogram.
- Variants that call transforms surface the edge from the variant sub-node, not the parent Design.
- Module-level `register("name", instance)` is a third registration shape; it produces a parallelogram, but there's no defining function or class to walk, so no outgoing edges follow from it.

### Variants (`builds`)

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

Build-target detection picks up the patterns scadwright projects actually use:

- `return self.foo` — when `foo = SomeComponent()` at Design class scope.
- `return SomeComponent()` — direct instantiation in the variant body.
- `return union(self.a, self.b)` — both Components surface as build targets.
- `return helper(self.x)` — `self.x` resolves through the class-attribute map.

## Running it on a project

```
scadwright graph PATH [--format ascii|mermaid|json|dot] [--filter NAME] [--depth N]
```

`PATH` may be a directory (recursed) or a single Python file. The default `--format ascii` writes plain text to stdout that you can read directly, redirect, or pipe:

```
scadwright graph project/
scadwright graph project/ > project-graph.txt
scadwright graph project/ --filter Bayonet | less
scadwright graph examples/electronics-case.py
```

### Focusing on one class: `--filter`

When the project has more nodes than fit comfortably on one diagram, `--filter NAME` narrows the output to one class plus its connected neighbourhood:

```
scadwright graph project/ --filter BatteryHolder
scadwright graph project/ --filter BatteryHolder --depth 1
scadwright graph project/ --filter main.BatteryHolder
```

`NAME` is the class name. If two classes in different modules share a name, pass the full dotted id (`module.ClassName`) — the error message lists the candidates when the bare name is ambiguous.

`--depth N` caps the radius, counting hops in either direction (Param-of, contains, inherits all count as one): `--depth 0` keeps only the focus node, `--depth 1` adds its direct neighbours, and the default keeps the full reachable subgraph. `--depth` requires `--filter`; using it alone is an error.

### Excluding files: `--exclude`

`scadwright graph` walks the project directory in full. For projects that keep historical snapshots, scratch sketches, or generated stubs alongside live code, `--exclude PATTERN` drops matching files before they enter the graph:

```
scadwright graph project/ --exclude OLD
scadwright graph project/ --exclude OLD --exclude scratch
scadwright graph project/ --exclude 'OLD/2026-*'
```

A pattern without a `/` matches any single path segment. `--exclude OLD` skips every file whose path contains a directory or file named `OLD`. Wildcards work too: `--exclude '*.test.py'` skips test files by suffix.

A pattern with a `/` matches the file's project-relative path. `--exclude OLD/2026-*` skips only the dated subdirs under `OLD`, leaving `OLD/keep.py` in the graph.

Repeat the flag to apply more than one pattern. The built-in skips (`__pycache__`, `node_modules`, hidden directories like `.git`) always apply.

## Other output formats

For embedding a diagram in a Markdown README, `--format mermaid` writes Mermaid `graph TD` source. Pipe it into a renderer or paste into [mermaid.live](https://mermaid.live):

```
scadwright graph project/ --format mermaid > project-graph.mmd
scadwright graph project/ --format mermaid | mmdc -i - -o project-graph.svg
```

For programmatic consumers (custom dashboards, doc generators, diff tooling), `--format json` produces a structured payload:

```
scadwright graph project/ --format json
```

The JSON shape is two top-level keys, `nodes` and `edges`. Each node has `id`, `label`, `kind`, plus `path` and `line` (project-relative, POSIX-style) when source location is available. Each edge has `source`, `target`, `kind`, plus `via_param` (on `uses_param` edges) or `attrs_read` (on `reads_attr` edges) when relevant.

For larger projects where Mermaid layout suffers, `--format dot` produces Graphviz DOT source. Pipe through `dot` to render:

```
scadwright graph project/ --format dot | dot -Tsvg -o project-graph.svg
scadwright graph project/ --format dot | dot -Tpng -o project-graph.png
```

Graphviz's layout engines (`dot`, `neato`, `sfdp`) handle the geometry — the same shape vocabulary applies (diamond, rounded box, cylinder, hexagon, parallelogram).

## Limitations

`scadwright graph` covers Component / Spec / Design / Transform class discovery, Param / equations / `build()` / class-attribute reads, composition, variant analysis, and transform usage. The following aren't covered:

- **No abstract / concrete distinction.** All Components render with the same shape, regardless of whether they're directly instantiated anywhere.
- **Cross-project imports aren't followed.** A class whose base is in a third-party scadwright extension is categorized as `unknown` and omitted.
- **Dynamic dispatch isn't tracked.** `cls = A if flag else B; return cls()` can't be statically resolved; both branches drop unless they're each independently instantiated.
- **Transforms registered with computed names don't surface.** `@transform(name_var)` or `register(name_var, instance)` where the name isn't a string literal can't be resolved by static analysis; the registration drops and chained calls to it produce no edge.
- **Star-imported transforms drop.** `from project_transforms import *` registers the names at runtime, but the consumer file's imports aren't enumerable without executing it, so the consumer's `"uses"` edges to those transforms don't appear.

## Troubleshooting

- **A file with a syntax error is skipped, with a stderr warning.** Classes defined in unparseable files don't appear in the graph; the warning lists each skipped file and the parse error so you know what's missing. Fix the syntax and re-run.
- **A class doesn't appear in the graph.** Confirm its base resolves to one of `scadwright.Component`, `scadwright.Spec`, or `scadwright.Design` — directly or via project-local intermediate classes. Bases imported from external packages categorize as `unknown` and drop the class.
- **Equation-derived edges are missing.** If equations don't validate (the LSP would mark them with squiggles), attribute-read edges from those equations are dropped. The rest of the graph still builds. Fix the validation error and re-run.
- **A transform call doesn't produce an edge.** The chained `.X(...)` name doesn't match a registered project transform. Cause: `X` is a curated framework verb (`.translate`, `.rotate`, ...), a Python method on an unrelated object, or a typo. Fix: confirm the project defines `@transform("X")`, `class MyTransform(Transform): name = "X"`, or `register("X", ...)` with `X` as a string literal.
