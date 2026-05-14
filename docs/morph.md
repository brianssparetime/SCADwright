# Morph — variant-to-variant animation

A morph turns two existing variants into a snazzy animation. Declare one line in your `Design` class, run a single CLI command, get an animated PNG ready to drop into a README:

```python
from scadwright import morph

class BoxAndLid(Design):
    box = MyBox()
    lid = MyLid()

    @variant
    def print(self):
        return union(self.box, self.lid.rotate([180, 0, 0]).up(2).right(80))

    @variant(default=True)
    def display(self):
        return union(self.box, self.lid.up(50))

    assemble = morph(start="print", end="display")
```

```bash
scadwright morph widget.py assemble out.apng
```

`out.apng` lands next to the script. The lid swings from the print-bed pose into the display pose along a circular arc — the path of a single rotation about a virtual hinge. No ffmpeg required.

## How it works

The morph captures both variants' ASTs, identifies which parts (`self.box`, `self.lid`, ...) appear in both, and computes the transform difference between them. At animation time the start-pose transforms morph smoothly into the end-pose transforms using **Chasles' theorem**: any rigid motion in 3D is equivalent to a single rotation about a screw axis, plus an optional translation along that axis. For a 180° flip combined with a translation, this reads as a hinge swing rather than translating-and-rotating-in-midair.

The CSG structure of both variants is preserved. If `print` uses `difference(self.body, self.hole.up(5))` and `display` uses `difference(self.body, self.hole.up(10))`, the morph's output keeps the `difference()` — only `self.hole`'s position animates.

## The `morph(...)` factory

```python
morph(start: str, end: str, *, order: list[str] | None = None, simultaneous: bool = False) -> _MorphSpec
```

- `start`: name of the start-pose variant (a method decorated with `@variant`).
- `end`: name of the end-pose variant.
- `order` (optional): list of class-attribute names specifying the order in which parts animate when `simultaneous=False`. Names not listed inherit the default order: ascending by destination z (parts that end up lower in the model animate first).
- `simultaneous` (optional, default `False`): if `False`, parts animate one at a time across the `$t ∈ [0, 1]` timeline. If `True`, all parts animate over the full timeline together.

The attribute name on the left of the assignment becomes the morph's variant name. You reference it from the CLI the same way as any other variant:

```bash
scadwright build widget.py --variant=assemble        # writes the animated .scad
scadwright preview widget.py --variant=assemble      # opens in OpenSCAD; hit Animate
scadwright morph widget.py assemble out.apng         # writes an APNG
```

## The CLI

```
scadwright morph SCRIPT MORPH_NAME OUTPUT [options]
```

The output extension picks the format:

- **`.apng`** — animated PNG. Renders in every modern browser, on GitHub READMEs, Discord, Slack, Reddit. Default — uses the vendored APNG encoder, no external dependencies beyond OpenSCAD.
- **`.scad`** — animated SCAD only, no rendering. Open in OpenSCAD's View → Animate to scrub by hand.
- **`.png`** — frame sequence; `OUTPUT` is treated as a prefix. Files are written as `PREFIX_0001.png`, `PREFIX_0002.png`, etc.

Options:

- `--frames N` — number of animation frames (default `60`).
- `--fps N` — frame rate for `.apng` output (default `30`).
- `--imgsize WxH` — image dimensions (default `800x600`).
- `--loop` / `--no-loop` — APNG loop control (default `--loop`, plays forever).
- `--keep-frames` — keep the intermediate PNG frames after encoding (path printed at end).
- `--openscad PATH` — path to the OpenSCAD binary.

## Part identity

Parts in a `Design` are class attributes (`box = MyBox()`, `lid = MyLid()`). The morph pairs parts across the two variants by **Python object identity** — both variants reference the same `Component` instance via `self.box`, so the morph knows they're the same part. No labels or names needed.

For inline geometry (a `cube(5)` or similar constructed in-place inside a variant body), the morph pairs by **structural position and `tree_hash`**: if both variants have a `cube(5)` at the same point in their CSG tree, they pair. Their transform stacks may differ — in which case the cube animates between the two positions.

```python
class Stack(Design):
    base = Base()
    body = Body()
    lid  = Lid()

    @variant
    def exploded(self):
        return union(self.base, self.body.up(50), self.lid.up(100))

    @variant(default=True)
    def assembled(self):
        return union(
            self.base,
            self.body.up(self.base.height),
            self.lid.up(self.base.height + self.body.height),
        )

    settle = morph(start="exploded", end="assembled")
```

Default order is destination-z ascending: `base` animates first (slot 0 of 3), then `body`, then `lid`. Override with `order=["lid", "body", "base"]` for a top-down "stack pulls apart" feel.

## What can't morph

The morph framework is intentionally "easy mode" — not infinitely extensible. These cases raise with clear error messages:

- **Mirrors in the difference between variants.** `self.lid.flip("z")` in one variant and `self.lid` in the other can't be interpolated (the flip is a reflection, det = -1). Replace `flip("z")` with `rotate([180, 0, 0])` — same final pose, animatable, and the morph will trace the hinge swing.
- **Non-uniform scale changes.** Uniform scale (the whole part grows) is fine; non-uniform scale (the part stretches in one direction) is not — that's shape morphing, which needs separate parts.
- **Structurally different variants.** Both variants must share the same CSG skeleton: same `union`/`difference`/`intersection`/etc. structure, same decoration wrappers (colors, anchors). Only the *transforms above each leaf* may differ.
- **Different parts in the two variants.** A part in one variant must appear in the other, in the same structural position. To add or remove parts, you need a chained morph (planned for later).
- **`Resize` wrapping animated content.** `Resize` is bbox-dependent: its scale factor is recomputed from the child's bounding box at render time. If the child is animated (rotating, translating), the bbox changes per frame and the scale factor changes with it, producing visible size-jitter as the part moves. Move the `Resize` outside the morph (apply it to the final unioned result), or replace it with `Scale` using explicit factors so the scale is constant. A `Resize` over geometry that's identical in both variants — i.e., static decoration — is fine.

For the inline-primitive case where you want to animate a `cube(5)`-like piece between variants, lift it to a class attribute (`self.spacer = cube(5)`) so both variants reference the same instance.

## Error catalog

### Mirror in the difference

```
morph: part 'lid' uses a mirror on one side but not the other.
Mirrors are reflections (det = -1) and can't be smoothly interpolated.
  Replace .flip(...) with .rotate([180, 0, 0]) (or the equivalent
  rotation) — same final pose, and the morph will animate it as a
  single hinge swing.
```

### Non-uniform scale change

```
morph: part 'widget' has non-uniform scale that differs between variants.
  start scale: (1.0, 1.0, 1.0)
  end scale:   (2.0, 1.0, 1.0)
  Only uniform scale changes can be animated; for shape morphing,
  define separate parts.
```

### Structural mismatch

```
morph: variant ASTs differ in structure — kind differs (component vs spatial).
  start has: _Lid
  end has:   Translate
  morph requires both variants to share the same CSG / decoration
  skeleton; only the transforms above leaves (Components, primitives)
  may differ.
```

### Lifting inline parts

If you see "inline primitive geometry differs at the same structural position," the morph is telling you that two variants have a `cube(...)` (or `sphere`, `cylinder`, etc.) at the same point in the CSG tree but with different transforms — and inline primitives can't pair across variants for animation.

**Why the rule exists.** A class-attribute Component (`self.spacer = MyPart()`) is a single Python object referenced from both variants; the morph pairs it across variants by `id()`. An inline `cube(10)` built inside the variant body is a fresh Python object on every call — there's no shared identity to pair with. To keep the rules simple, the morph requires the shared-identity pattern for animation.

**The fix: promote the inline part to a class attribute.** Before:

```python
class Widget(Design):
    body = MyBody()

    @variant
    def low(self):
        return union(self.body, cube(10).up(5))        # inline cube → can't animate

    @variant(default=True)
    def high(self):
        return union(self.body, cube(10).up(20))       # different transform → mismatch error

    open = morph(start="low", end="high")              # error
```

After:

```python
class Widget(Design):
    body = MyBody()
    spacer = cube(10)                                  # class attribute — shared identity

    @variant
    def low(self):
        return union(self.body, self.spacer.up(5))     # animates...

    @variant(default=True)
    def high(self):
        return union(self.body, self.spacer.up(20))    # ...via self.spacer

    open = morph(start="low", end="high")              # works
```

The class attribute can be a `Component`, a primitive (`cube(...)`, `sphere(...)`, etc.), or any expression that yields a Node — they all become shared-identity values.

**When you don't need to lift.** If the inline geometry is in the *same position* in both variants — same primitive, same parameters, same transforms — the morph sees it as static decoration and passes it through unchanged. You only need to lift when the inline thing should *move* between variants.

## Composing with viewpoint

The morph inherits the **end variant's** viewpoint by default — the user usually wants to see the final pose framed in the OpenSCAD camera. To override, use the CLI's `--vpr` / `--vpt` / `--vpd` flags (where applicable) or set viewpoint on the end variant itself.

## Troubleshooting

### The lid (or hinged part) swings the wrong way

If your morph contains a 180° rotation and the part traces an arc you didn't intend — over the back instead of over the front, or under the bottom instead of over the top — the cause is a sign ambiguity in the screw axis. A 180° rotation has two equally valid axis directions, and the heuristic picks one of them without knowing which feels right for your geometry.

**Fix:** break the symmetry by writing the rotation as something slightly off 180°, so the axis becomes uniquely determined:

```python
# Before — both arc directions are valid; heuristic guesses:
self.lid.rotate([180, 0, 0]).up(self.lid.thk).right(80)

# After — 179.99° has a unique axis; the morph picks that arc:
self.lid.rotate([179.99, 0, 0]).up(self.lid.thk).right(80)
```

The 0.01° offset is visually imperceptible in the final pose but enough to disambiguate the screw axis. The morph will now consistently pick the arc whose mid-point traces through positive y; flip the sign (`179.99° → 180.01°`, or rotate about `-X` instead of `+X`) to trace through negative y.

### The animation pulses or jitters in size

If a part inside your morph changes size frame-by-frame, the cause is a `Resize(...)` wrapper around animated content. Resize computes its scale factor from the child's bounding box at render time; an animated child has a different bbox every frame.

**Fix:** move the Resize outside the morph, or replace it with `Scale(factor=...)` using explicit factors. See the error message — it suggests both options.

### "Inline primitive geometry differs"

See [Lifting inline parts](#lifting-inline-parts) above.

## Limitations and future work

- **Chained morphs** (three-or-more-variant sequences) are out of scope for v1.
- **Ping-pong playback** (forward, then reverse) is not yet supported — coming as a `pingpong=True` knob.
- **MP4 / WebM output** requires a heavyweight encoder dependency (ffmpeg or Pillow) and is not in v1. The vendored APNG path covers the README and social-media use cases. For `.mp4` / `.gif`, output a PNG sequence and run ffmpeg yourself — the CLI's error message walks through this.
- **Collision-aware ordering** of the default destination-z order isn't implemented; the heuristic is geometric, not physical.
