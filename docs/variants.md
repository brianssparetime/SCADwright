# Variants

A SCADwright project often needs to produce more than one `.scad` file from the same set of parts. Variants let you define multiple arrangements -- different scenes, different orientations, different levels of detail -- all from one script, with shared parts instantiated once.

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

- Parts are instantiated once at class-definition time. No duplication across variants.
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

## `@variant` options

- `fn=`, `fa=`, `fs=` -- resolution applied while building this variant. All primitives built inside the variant method inherit these values. Components in the returned AST capture the variant's resolution context at the moment they're constructed or wrapped, so primitives inside their `build()` see the right values regardless of when the build actually runs (see [Resolution](resolution.md#components-capture-context-at-ast-insertion-not-at-build)).
- `rotation=`, `target=`, `distance=`, `fov=` -- camera viewpoint (`$vpr`, `$vpt`, `$vpd`, `$vpf`) emitted at the top of the `.scad` file. Sets the default camera angle when opening the file in OpenSCAD.
- `out=` -- output `.scad` path. Default: `f"{DesignClass}-{variant_name}.scad"` next to the script.
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
        return union(self.box, self.lid.rotate([180, 0, 0]).up(2).right(80))

    @variant(default=True)
    def display(self):
        return union(self.box, self.lid.up(50))

    assemble = morph(stages=["print", "display"])
```

`scadwright morph widget.py assemble out.apng` writes an animated PNG that swings the lid from its print-bed pose into its seated pose along a hinge-like arc. See [Morph](morph.md) for the full feature page (limitations, ordering knobs, error catalog).

---

### Advanced notes

- The `current_variant()` function and `with variant("name"):` context manager are available for edge cases where a Component's `build()` method needs to branch on the active variant. `Design` + `@variant` is the preferred approach for most projects; reach for `current_variant()` only when a single Component genuinely needs variant-aware geometry.

- **Components shared across variants rebuild fresh per variant.** A Component instantiated as a Design class attribute (the typical pattern) caches its built tree, but the cache is invalidated before each variant render. So a Component referenced by both `print(self)` and `display(self)` builds once per variant, picking up that variant's `fn=`, `clearances`, and viewpoint contexts each time.
