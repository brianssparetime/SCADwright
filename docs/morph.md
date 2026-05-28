# Morph — variant-to-variant animation

<p align="center">
  <img src="../examples/images/BoxAndLid-assemble.apng" alt="BoxAndLid morph: lid swings from its print-bed pose into its seated pose" width="600">
</p>

A morph turns two or more existing variants into a snazzy animation. Declare one line in your `Design` class, run a single CLI command, get an animated PNG ready to drop into a README:

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

    assemble = morph(stages=["print", "display"])
```

```bash
scadwright morph widget.py assemble out.apng
```

`out.apng` lands next to the script. The lid swings from the print-bed pose into the display pose along a circular arc — the path of a single rotation about a virtual hinge. No ffmpeg required.

## How it works

The morph captures every stage variant's AST, identifies which parts (`self.box`, `self.lid`, ...) appear in each, and computes the transform difference between consecutive stages. At animation time the transforms morph smoothly from one stage to the next using **Chasles' theorem**: any rigid motion in 3D is equivalent to a single rotation about a screw axis, plus an optional translation along that axis. For a 180° flip combined with a translation, this reads as a hinge swing rather than translating-and-rotating-in-midair.

The CSG structure of every stage is preserved. If `print` uses `difference(self.body, self.hole.up(5))` and `display` uses `difference(self.body, self.hole.up(10))`, the morph's output keeps the `difference()` — only `self.hole`'s position animates.

## The `morph(...)` factory

```python
morph(stages: list[str], *,
      order: list[str] | None = None,
      simultaneous: bool = False,
      pingpong: bool = False) -> _MorphSpec
```

- `stages`: list of two or more variant names (methods decorated with `@variant`). The animation runs through consecutive pairs `(stages[0], stages[1])`, `(stages[1], stages[2])`, …, each pair forming one "leg" of the chain. Two-stage morphs use `stages=["a", "b"]`; three or more entries make a chain (see [Chains](#chains) below).
- `order` (optional): list of class-attribute names specifying the order in which parts animate within each leg when `simultaneous=False`. Names not listed inherit the default order: ascending by destination z (parts that end up lower in the model animate first).
- `simultaneous` (optional, default `False`): if `False`, parts animate one at a time inside each leg's slice. If `True`, all parts in a leg animate over that leg's full slice simultaneously.
- `pingpong` (optional, default `False`): if `True`, the animation plays forward over the first half of the timeline and reverses back over the second half. The chain visits `stages[0] → … → stages[-1] → … → stages[0]` as `$t` runs from 0 to 1, ending exactly where it started — natural for looping APNGs. See [Pingpong](#pingpong) below.
- `michael_bay` (optional, default `False`): if `True`, the camera orbits 360° around world z over the animation, overriding the final stage's rotation viewpoint. See [Michael Bay shot](#michael-bay-shot) below.

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

- **`.apng`** — animated PNG. Renders in every modern browser, on GitHub READMEs, Discord, Slack, Reddit. Uses the vendored APNG encoder, no external dependencies beyond OpenSCAD.
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

Parts in a `Design` are class attributes (`box = MyBox()`, `lid = MyLid()`). The morph pairs parts across stages by **Python object identity** — every stage references the same `Component` instance via `self.box`, so the morph knows they're the same part. No labels or names needed.

For inline geometry (a `cube(5)` or similar constructed in-place inside a variant body), the morph pairs by **structural position and `tree_hash`**: if every stage has a `cube(5)` at the same point in the CSG tree, they pair. Their transform stacks may differ — in which case the cube animates between the positions.

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

    settle = morph(stages=["exploded", "assembled"])
```

Default order is destination-z ascending: `base` animates first (slot 0 of 3), then `body`, then `lid`. Override with `order=["lid", "body", "base"]` for a top-down "stack pulls apart" feel.

## Chains

A chain morph passes through three or more poses in sequence. Add intermediate stages between the start and end pose, and each consecutive pair becomes one **leg** of the chain:

```python
class BoxAndLid(Design):
    box = MyBox()
    lid = MyLid()

    @variant
    def print(self):
        return union(self.box, self.lid.rotate([180, 0, 0]).right(80))

    @variant
    def closing(self):
        # Lid hovering above the box, already right-side-up. Bridges the
        # 180° hinge swing of leg 0 to the seated drop of leg 1.
        return union(self.box, self.lid.up(self.box.height + 20))

    @variant(default=True)
    def display(self):
        return union(self.box, self.lid.up(self.box.height))

    assemble = morph(stages=["print", "closing", "display"])
```

Each leg is interpolated independently using the screw-motion path. At the boundary between legs the chain passes through the intermediate stage's pose exactly.

**Leg timing** is auto-allocated by motion magnitude: legs with bigger motion get more of the timeline. A leg with no motion (a deliberately-static intermediate stage) still receives a brief slice so it reads as a pause rather than a snap.

A part may animate in some legs and stay still in others — those legs simply don't include the part's chain. Parts that are part of every stage's CSG skeleton must remain in the same structural position; only the spatial transforms above them may differ from stage to stage.

## Pingpong

`pingpong=True` makes the animation play forward then reverse over one timeline cycle. The first half visits every stage in order; the second half visits them in reverse, landing back on `stages[0]` at the end:

```python
assemble = morph(stages=["print", "display"], pingpong=True)
# $t = 0     → print
# $t = 0.5   → display
# $t = 1     → print (back to start, ready to loop)
```

For chains, the reversal applies symmetrically:

```python
assemble = morph(stages=["print", "closing", "display"], pingpong=True)
# Forward over [0, 0.5]:  print → closing → display
# Reverse over [0.5, 1]:  display → closing → print
```

The pingpong reshape happens at the SCAD layer (a triangle wave on `$t`), so the same `.scad` previews correctly in OpenSCAD's animator and renders to an APNG with no extra frames — the file is the same size as the non-pingpong version. Useful when you want a looping animation that doesn't snap back to the start at the seam.

## Michael Bay shot

`michael_bay=True` orbits the camera 360° around world z over the animation. The model assembles (or whatever the morph is doing) while the camera swings around it.

```python
assemble = morph(stages=["print", "display"], michael_bay=True)
```

Combined with `pingpong=True`, the camera completes one full revolution while the model plays forward then back — the kind of one-second loop that draws eyes on a README.

The orbit overrides the final stage's `rotation` viewpoint, but the stage's `target`, `distance`, and `fov` still apply if set — so framing carries through. The pitch is fixed at 60° (a looking-down-from-above 3D shot); if you need a different pitch, write the viewpoint by hand using `t()` math and leave `michael_bay=False`.

## What can't morph

The morph framework is intentionally "easy mode" — not infinitely extensible. These cases raise with clear error messages:

- **Mirrors in the difference between stages.** `self.lid.flip("z")` in one stage and `self.lid` in another can't be interpolated (the flip is a reflection, det = -1). Replace `flip("z")` with `rotate([180, 0, 0])` — same final pose, animatable, and the morph will trace the hinge swing.
- **Non-uniform scale changes.** Uniform scale (the whole part grows) is fine; non-uniform scale (the part stretches in one direction) is not — that's shape morphing, which needs separate parts.
- **Structurally different stages.** Every stage must share the same CSG skeleton: same `union`/`difference`/`intersection`/etc. structure, same decoration wrappers (colors, anchors). Only the *transforms above each leaf* may differ.
- **Different parts in different stages.** A part in one stage must appear in every stage, in the same structural position.
- **`Resize` wrapping animated content.** `Resize` is bbox-dependent: its scale factor is recomputed from the child's bounding box at render time. If the child is animated (rotating, translating), the bbox changes per frame and the scale factor changes with it, producing visible size-jitter as the part moves. Move the `Resize` outside the morph (apply it to the final unioned result), or replace it with `Scale` using explicit factors so the scale is constant. A `Resize` over geometry that's identical in every stage — i.e., static decoration — is fine.

For the inline-primitive case where you want to animate a `cube(5)`-like piece between stages, lift it to a class attribute (`self.spacer = cube(5)`) so every stage references the same instance.

## Lifting inline parts

If you see "inline primitive geometry differs at the same structural position," the morph is telling you that two stages have a `cube(...)` (or `sphere`, `cylinder`, etc.) at the same point in the CSG tree but with different transforms — and inline primitives can't pair across stages for animation.

**Why the rule exists.** A class-attribute Component (`self.spacer = MyPart()`) is a single Python object referenced from every stage; the morph pairs it across stages by `id()`. An inline `cube(10)` built inside the variant body is a fresh Python object on every call — there's no shared identity to pair with. To keep the rules simple, the morph requires the shared-identity pattern for animation.

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

    open = morph(stages=["low", "high"])               # error
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

    open = morph(stages=["low", "high"])               # works
```

The class attribute can be a `Component`, a primitive (`cube(...)`, `sphere(...)`, etc.), or any expression that yields a Node — they all become shared-identity values.

**When you don't need to lift.** If the inline geometry is in the *same position* in every stage — same primitive, same parameters, same transforms — the morph sees it as static decoration and passes it through unchanged. You only need to lift when the inline thing should *move* between stages.

## Composing with viewpoint

The morph inherits the **final stage's** viewpoint by default — the user usually wants to see the final pose framed in the OpenSCAD camera. To override, use the CLI's `--vpr` / `--vpt` / `--vpd` flags (where applicable) or set viewpoint on the final stage variant itself.

## Troubleshooting

### The animated part cuts through other geometry on its arc

If your morph's arc passes through another part on its way to the end pose — a lid that swings sideways into the box rather than over the top, for example — the rotation axis is parallel to the translation between the poses. The arc plane is perpendicular to the screw axis (which follows the rotation), so a rotation aligned with the translation produces an arc that sweeps sideways at constant height instead of lifting up and over.

**Fix:** rotate the start pose about an axis perpendicular to the translation.

```python
# Before — rotation about X is parallel to the +X translation; arc sweeps in YZ.
self.lid.rotate([180, 0, 0]).up(2).right(80)

# After — rotation about Y is perpendicular to +X; arc lifts in XZ.
self.lid.rotate([0, 180, 0]).up(2).right(80)
```

For parts with rotational symmetry about z — a square lid, a centered cylinder — both rotation axes produce the same final pose, so pick whichever gives the right arc. For asymmetric parts where the final orientation depends on which axis you flipped about, use a chain morph with an explicit intermediate stage (`stages=["print", "midair", "display"]`) so you can draw the path by hand.

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
