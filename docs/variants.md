# Variants

A SCADwright project often needs to produce more than one `.scad` file from the same set of parts. Variants let you define multiple arrangements -- different scenes, different orientations, different levels of detail -- all from one script, with the parts written down once.

## The Design + @variant pattern

A `Design` subclass holds the shared parts as class attributes. Each `@variant`-decorated method returns the scene for one arrangement:

```python
from scadwright.boolops import union
from scadwright.design import Design, run, variant

class BoxAndLid(Design):
    box = MyBox()
    lid = MyLid(box=box)

    @variant(fn=48, default=True)
    def print(self):
        # Lid flipped and spaced for the print bed
        return union(
            self.box,
            self.lid.flip("z").up(self.lid.height).right(80),
        )

    @variant(fn=48)
    def display(self):
        # Lid seated on the box, assembled view
        return union(self.box, self.lid.up(self.box.height))

if __name__ == "__main__":
    run()
```

- Parts are written down once, in the class body. Each variant then builds its own copy, so it can't disturb another variant's geometry.
- Each variant method returns a scene Node. The method name becomes the variant name.
- `run()` replaces `render()` -- it discovers the Design, picks the right variant, and writes the `.scad` file.

## When variants are useful

### Print vs. display

The most common case. The print variant lays parts flat on the bed, spaced apart, flipped for clean overhangs. The display variant shows the assembled design, possibly with stand-in hardware or ghost parts for context:

```python
@variant(fn=48, default=True)
def print(self):
    return union(
        self.base,
        self.lid.flip("z").up(self.lid.thk).right(80),
    )

@variant(fn=48)
def display(self):
    pcb_standin = cube([85, 56, 1.5], center="xy").color("darkgreen")
    return union(self.base, pcb_standin.up(6), self.lid.up(self.base.height))
```

### Individual parts for separate print jobs

When each part needs its own `.scad` (different print settings, different materials, or just too big for one bed):

```python
class ProjectBox(Design):
    base = Pi4Case()
    lid = Pi4Lid(base=base)

    @variant(fn=48)
    def print_base(self):
        return self.base

    @variant(fn=48)
    def print_lid(self):
        return self.lid.flip("z").up(self.lid.thk)

    @variant(fn=48, default=True)
    def display(self):
        return union(self.base, self.lid.up(self.base.height))
```

Running `scadwright build project.py` with no `--variant` builds the default. Running `scadwright build project.py --variant=print_base` builds just the base. With no default and multiple variants, `scadwright build` runs all of them -- one `.scad` per variant.

### Multi-part assembly views

For complex projects, variants can show different subassemblies or exploded views:

```python
class Bike(Design):
    frame = Frame()
    fork = Fork()
    wheels = WheelSet()
    seat = SeatPost()

    @variant(fn=48)
    def frame_only(self):
        return self.frame

    @variant(fn=48)
    def rolling_chassis(self):
        return union(self.frame, self.fork, self.wheels)

    @variant(fn=48, default=True)
    def full_assembly(self):
        return union(self.frame, self.fork, self.wheels, self.seat)

    @variant(fn=24)
    def exploded(self):
        return union(
            self.frame,
            self.fork.up(50),
            self.wheels.up(100),
            self.seat.up(150),
        )
```

### Resolution tiers

Use lower resolution for fast iteration, higher for final output. The `fn=` on the decorator controls resolution for the entire variant:

```python
@variant(fn=16)
def draft(self):
    return self.widget                  # fast preview

@variant(fn=128, default=True)
def final(self):
    return self.widget                  # production quality
```

### Section views and debug

`halve` and `.highlight()` are particularly useful in debug variants:

```python
@variant(fn=48)
def cross_section(self):
    return self.housing.halve([0, -1, 0]).rotate([270, 0, 0])

@variant(fn=48)
def debug_clearances(self):
    return union(
        self.outer.highlight(),         # ghost of the outer shell
        self.inner,                     # solid inner shows clearance
    )
```

Manufacturing-specific tweaks (printer overshoot, material shrinkage, slop on a tight fit) belong in [Adjustments](specs_and_adjustments.md#adjustments), not as separate variants.

## Where the output goes

By default each variant writes `f"{DesignClass}-{variant_name}.scad"` next to the script. Two class attributes change that:

```python
class WidgetProject(Design):
    name = "widget"        # filename stem; default is the class name
    out_dir = "build"      # directory, relative to the script
```

The variants then write to `build/widget-print.scad` and `build/widget-display.scad`, and SCADwright creates the directory if it isn't there.

A single variant can override the path with `out=`, which composes under `out_dir` when it's relative and replaces it when it's absolute:

```python
@variant(out="fixtures/jig.scad")     # -> build/fixtures/jig.scad
def jig(self):
    ...
```

`scadwright build ... -o path.scad` beats all of it, and is taken relative to where you ran the command rather than to the script.

## `@variant` options

Write `@variant` on its own when there's nothing to set, and `@variant(...)` when there is. Every option below is passed by name.

- `fn=`, `fa=`, `fs=` -- resolution for everything this variant builds. The geometry is built before the variant hands it back, so these values are already in the result.
- `rotation=`, `target=`, `distance=`, `fov=` -- camera viewpoint (`$vpr`, `$vpt`, `$vpd`, `$vpf`) emitted at the top of the `.scad` file. Sets the default camera angle when opening the file in OpenSCAD. The camera travels with the scene, so it reaches the file whether you build from the command line or render the scene yourself.
- `out=` -- output `.scad` path for this one variant. See [Where the output goes](#where-the-output-goes).
- `default=True` -- the variant to run when no `--variant` is given. At most one per `Design`.

```python
@variant(fn=48, rotation=(60, 0, 30), distance=200, default=True)
def display(self):
    return union(self.housing, self.hood)
```

## CLI

```
scadwright build widget.py --variant=print -o widget_print.scad
scadwright build widget.py --variant=display
scadwright build widget.py                    # runs the default variant
scadwright build widget.py --vpr=60,0,30     # override camera rotation
scadwright build widget.py --vpd=200         # override camera distance
```

CLI viewpoint flags (`--vpr`, `--vpt`, `--vpd`, `--vpf`) override any viewpoint set by `@variant`.

## Calling a variant yourself

Calling a variant method gives you its scene, the same one `scadwright build` writes to a file:

```python
from scadwright.render import render

design = BoxAndLid()
render(design.display(), "check.scad")
```

Everything on the `@variant` line applies at the call. The geometry carries the variant's `fn`, and the scene carries its camera, so the file above matches `scadwright build --variant=display` line for line. Only `out=` and `default=` stay out of it: both choose which file gets written, and you did that by passing a path.

Each call builds its own copy of the design's parts, so one variant can't disturb another:

```python
print_scene = design.print()
display_scene = design.display()     # print_scene is unaffected
```

Hold both, render them in either order, render one of them twice: each keeps the resolution its own variant declared. Reading a part straight off the design (`design.box`) gives it as declared, untouched by any variant you have run.

Reach for this in tests, when measuring a scene with the [assertions](testing.md#geometry-assertions), or any time a script wants the geometry rather than a file.

## `run()` dispatch rules

In order:

1. If exactly one variant is registered:
   - If `--variant` is given and doesn't match, error.
   - Otherwise run that one variant.
2. If `--variant=NAME` is given (multiple variants exist), run it; error if the named variant doesn't exist.
3. If exactly one variant is marked `default=True`, run it.
4. If multiple are marked `default=True`, error (caught at class-definition time).
5. Multiple variants, none default: `scadwright build` runs all of them; `scadwright preview` and `scadwright render` error (they need exactly one target).

## Animating between variants

Once you have two variants that contain the same parts in different arrangements, a single line declares an animation that morphs from one to the other:

```python
class BoxAndLid(Design):
    box = MyBox()
    lid = MyLid()

    @variant
    def print(self):
        return union(self.box, self.lid.rotate([0, 180, 0]).up(2).right(80))

    @variant(default=True)
    def display(self):
        return union(self.box, self.lid.up(50))

    assemble = morph(stages=["print", "display"])
```

`scadwright morph widget.py assemble out.apng` writes an animated PNG that swings the lid from its print-bed pose into its seated pose along a hinge-like arc. See [Morph](morph.md) for the full feature page (limitations, ordering knobs, error catalog).

---

### Advanced notes

- The `current_variant()` function and `with variant("name"):` context manager are available for edge cases where a Component's `build()` method needs to branch on the active variant. `Design` + `@variant` is the preferred approach for most projects; reach for `current_variant()` only when a single Component genuinely needs variant-aware geometry.

- **Each variant builds its own copy of the parts.** A part used by both `print(self)` and `display(self)` is built twice, once per variant, so each picks up its own `fn=` and `clearances` and neither can disturb the other. [Specs](specs_and_adjustments.md) are shared rather than copied, which is what keeps a measured dimension one number across every part that reads it.
