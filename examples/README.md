# SCADwright examples

Each file is a self-contained SCADwright project that renders to one or more `.scad` files you can open in OpenSCAD. Run them with either:

```
python examples/<name>.py                           # default variant
python examples/<name>.py --variant=<name>          # pick a specific variant
scadwright preview examples/<name>.py --variant=<name>
```

The examples are arranged below from simplest to most complex. Each one introduces new ideas on top of what earlier ones showed, so reading them in order is the recommended learning path. See also [Organizing a project](../docs/organizing_a_project.md) for how to structure your own projects.

| Complexity | File | What it demonstrates |
| --- | --- | --- |
| Simple | [`simple-plate.py`](simple-plate.py) | Flat script, no Components -- primitives + booleans + `render()` |
| Simple | [`convex-caliper.py`](convex-caliper.py) | One primitive + two shape-library Components stacked with `attach()`; single-variant Design |
| Intermediate | [`v-block.py`](v-block.py) | First real Component -- trig `equations` (`sin`/`tan`), cross-constraints for physical bounds, concrete subclasses pinned by different pairs |
| Intermediate | [`wall-hook.py`](wall-hook.py) | Class-scope `anchor()` declarations on two Components, `attach(parent, face="...", fuse=True)` for anchor-based assembly |
| Intermediate | [`battery-holder.py`](battery-holder.py) | Custom transform, loop-based derivation in `equations`, namedtuple-field predicate, `Param(namedtuple)` for structured spec data, multi-instantiation |
| Intermediate | [`box-and-lid.py`](box-and-lid.py) | Generator `build()`, cross-Component publishing (`Lid` takes a `Box` as a Param), `@transform` chained via `bbox()` |
| Complex | [`electronics-case.py`](electronics-case.py) | Spec namedtuples as data contracts, derivations that subscript and iterate namedtuple fields, three custom transforms, multi-variant print-splitting |
| Complex | [`lens-housing.py`](lens-housing.py) | Element factory precomputing geometric fields, conditional-geometry derivations, single-line element-validation predicate, `halve()` section view, `attach(fuse=True)` + `bbox()` for assembly layout |

---

## 0. [`simple-plate.py`](simple-plate.py)

A plate with two holes. No Components, no Design -- just primitives, booleans, and a `render()` call. This is the simplest possible SCADwright script and shows that SCADwright starts looking like OpenSCAD code.

- `render()` writes a `.scad` directly from a Node expression -- no Design class needed for flat scripts
- `difference()` as a variadic call (one parent, many cutters)
- `.left()` / `.right()` directional helpers replacing `.translate([x, 0, 0])`
- `center="xy"` on a primitive to straddle the origin in plan

**Reference:** [primitives](../docs/primitives_3d.md) · [CSG operations](../docs/csg.md) · [directional helpers](../docs/transformations.md) · [organizing a project (Stage 1)](../docs/organizing_a_project.md#stage-1-flat-script)

---

## 1. [`convex-caliper.py`](convex-caliper.py)

A tool that slips over the jaws of a measuring caliper so it can span a part whose outer faces are both concave -- the central thickness of a biconcave lens, or the web left between two opposing countersunk holes drilled from each side of a plate. The spherical-cap feeler nests into each concavity so the caliper reads the distance between the feelers' outer domes. One primitive (`cylinder`) and two shape-library Components (`UShapeChannel`, `SphericalCap`) stacked with `attach()`.

- Composition with `attach()` -- each piece auto-positions on top of the previous one, no manual z-offsets
- Published attributes on shape-library Components (`clip.bottom_width`, `clip.outer_width`) drive downstream sizing
- `center="xy"` on the `UShapeChannel` so the stacked head is X-symmetric before the print-pair split
- Single-variant `Design` -- one `print` variant lays a mirrored pair side-by-side for a single print job

![Convex caliper](images/ConvexCaliper-print.png)

*print variant -- two mirrored heads on the bed, one per caliper jaw*

**Reference:** [shape library](../docs/shapes/README.md) · [attach()](../docs/anchors.md#basic-usage) · [Design + @variant](../docs/variants.md) · [centering](../docs/components.md#centering)

---

## 2. [`v-block.py`](v-block.py)

A machinist's V-block: a rectangular block with a V-shaped groove along its length, sized to cradle round stock tangent to both groove faces. Three concrete blocks, each pinned by a different pair of primary variables; the equations solve the rest.

- Trig in `equations` -- `sin` relates groove angle to the rod diameter it cradles; `tan` derives the opening width at the top
- All arithmetic lives in `equations`; no `params=`, no explicit `Param`
- Cross-constraints enforce physical bounds (`angle < 180`, `groove_depth < block_h`, `contact_width < block_w`)
- Three concrete subclasses, each fixing a different pair: `(angle, max_d)`, `(angle, groove_depth)`, `(max_d, groove_depth)`
- Chained `.through(parent, axis="x").through(parent, axis="z")` for the V-cutter -- no manual EPS, resolves coplanar faces at both ends and the top

```python
equations = [
    "half_angle == angle / 2",
    "max_d == 2 * groove_depth * sin(half_angle * pi / 180)",
    "contact_width == 2 * groove_depth * tan(half_angle * pi / 180)",
    "angle, max_d, groove_depth, contact_width, block_w, block_l, block_h > 0",
    "angle < 180",
    "groove_depth < block_h",
    "contact_width < block_w",
]
```

![V-block set](images/VBlockSet.png)

*left: display variant -- three V-blocks with a rod seated in each, showing that different specification pairs yield different angles, depths, and rod capacities; right: print variant -- single V-block*

**Reference:** [equations](../docs/components.md#equations) · [cross-constraints](../docs/components.md#declaring-parameters) · [through()](../docs/auto-eps_fuse_and_through.md) · [concrete subclasses](../docs/organizing_a_project.md#concrete-subclasses)

---

## 3. [`wall-hook.py`](wall-hook.py)

A wall-mount coat hook: a plate with two countersunk screw holes and a J-hook that attaches via a named anchor. Two small Components joined by `attach()` at a specific anchor on the parent -- no manual coordinate math.

- Class-scope `anchor(at=..., normal=...)` declarations on both Components -- `WallPlate.hook_mount` and `JHook.base`
- A second anchor (`WallPlate.top_edge`) published purely for extensibility, unused by this example but showing that a reusable Component can declare multiple attachment points
- `attach(parent, face="hook_mount", fuse=True)` picks a specific anchor on the parent; the normals already oppose, so no `orient=True` is needed
- `Torus(angle=90)` from the shape library composes a smooth quarter-toroid elbow between the stem and tip
- `.through(parent, axis="z")` on both the screw-hole shafts and countersink cutters -- no manual EPS

![Wall hook](images/CoatHook.png)

*left: display variant -- plate with J-hook attached at `hook_mount`; right: print variant -- plate and hook laid flat on the bed*

**Reference:** [anchors and attach()](../docs/anchors.md) · [attach(fuse=True)](../docs/auto-eps_fuse_and_through.md) · [through()](../docs/auto-eps_fuse_and_through.md) · [variants](../docs/variants.md)

---

## 4. [`battery-holder.py`](battery-holder.py)

A desk-tray battery caddy: N cylindrical cells of a chosen type sit in wells along a rounded-corner tray. Each well has a tall rounded-slot finger window in the outer wall -- oriented along the battery's long axis -- so you can see the cell and pinch it out from the side.

- `Param(BatterySpec)` accepting a `namedtuple` as a structured spec -- all dimensions for one battery flow from a single value
- Custom transform (`@transform("finger_scoop", inline=True)`) applied once per cradle, extruding a shape-library 2D profile (`RoundedSlot`) into the cutter
- Derivations in `equations` compute `pitch`, `outer_w`, `outer_l`, `cradle_positions` (loop-generated tuple) directly from the spec and Params -- no `setup()`
- Predicate (`"tray_depth < spec.length"`) validates against a namedtuple field the solver can't reach
- Per-battery concrete subclasses (`AA6Holder`, `Holder18650x4`) with all dimensions as class attributes
- Print and display `@variant`s

![Battery holder](images/BatteryBox.png)

*left: display variant -- six ghost AA cells seated in their cradles, tops protruding above the tray; right: print variant -- the bare tray showing the cradle geometry*

**Reference:** [Param() for non-floats](../docs/components.md#declaring-parameters) · [custom transforms](../docs/custom_transforms.md) · [derivations and predicates](../docs/components.md#derivations-loops-conditionals-namedtuple-fields) · [variants](../docs/variants.md) · [shape library](../docs/shapes/README.md)

---

## 5. [`box-and-lid.py`](box-and-lid.py)

A snap-on enclosure: a rounded-corner box with chamfered bottom edges and four interior screw pylons, plus a matching lid with countersunk corner holes and a centering lip that rises from the inner rim into a recess in the lid.

- Cross-Component dimension publishing -- `Lid` takes a `Box` instance as a `Param` and reads `box.outer_w`, `box.pylon_positions`, `box.screw`, `box.inner_corner_r` directly off it
- Generator-style `build()` yielding parts that the framework auto-unions
- Custom transform (`chamfer_top`) using `bbox()` to size itself to whatever it's applied to
- `equations` block mixing derived equalities (`inner_w == outer_w - 2*wall_thk`), positivity groups, non-negative groups, and a cross-constraint (`lip_thk < wall_thk`)
- `.through(parent)` on the lip cutout and lid recess -- no manual EPS for coplanar-face cleanup

![Box and lid](images/BoxAndLid.png)

*left: display variant -- lid floated above the box, centering lip and pylons visible through the gap; right: print variant -- box and inverted lid laid out on the bed*

**Reference:** [Param(Component)](../docs/components.md#declaring-parameters) · [generator build()](../docs/components.md#composite-parts-yield-the-pieces) · [custom transforms](../docs/custom_transforms.md) · [through()](../docs/auto-eps_fuse_and_through.md) · [bbox()](../docs/introspection.md#bounding-boxes)

---

## 6. [`electronics-case.py`](electronics-case.py)

A parametric 3D-printable case for a Raspberry Pi 4. Base tray with standoffs at the PCB's mount holes, port cutouts for USB, HDMI, audio, and Ethernet connectors, and a screw-on lid with a ventilation slot array.

- Spec dataclasses (`PCBSpec`, `PortSpec`) as data contracts -- swapping in an `ArduinoUno` spec would produce a valid Arduino case with no Component changes
- Three custom transforms (`port_cutout`, `countersunk_hole`, `vent_slot_array`) each applied many times; all three auto-size themselves via `bbox(node)` + `through(node, axis=...)` instead of magic-number cutter depths
- Cross-Component publishing -- `CaseLid` reads `base.mount_positions`, `base.outer_size`
- Multi-variant print-splitting: `print_base` and `print_lid` are bed-ready orientations, `display` is the assembled view
- Multi-instantiation driven by spec data (one standoff per mount hole, one port cutout per `PortSpec`)

![Project box](images/ProjectBox.png)

*left to right: display variant (assembled, PCB visible through the port cutouts), `print_base` (the tray alone, as it sits on the bed), `print_lid` (the lid flipped for the bed)*

**Reference:** [custom transforms](../docs/custom_transforms.md) · [through()](../docs/auto-eps_fuse_and_through.md) · [bbox()](../docs/introspection.md#bounding-boxes) · [variants](../docs/variants.md) · [organizing a project](../docs/organizing_a_project.md)

---

## 7. [`lens-housing.py`](lens-housing.py)

An M57-threaded optical lens barrel: holds three stacked lens elements in grip-lip holders, with an expansion funnel for an element that's wider than the throat, a front fillet that continues the cone angle of a matching clip-on hood.

- `element(...)` factory precomputes each element's geometric fields (`face_z_top`, `face_z_bot`, `constricted`, `throat_dia_required`) so the housing's `equations` list can reason about them through attribute access alone
- Conditional geometry: derivation `upper_housing_od = (max_upper_ele_dia + barrel_thk) if is_wide else flange_flange_od` picks between funnel-flared and straight barrel
- `Element` namedtuple driving multi-instantiation; a single predicate (`"all(not e.constricted or e.throat_dia_required <= lower_housing_id for e in elements)"`) validates that every constricted element fits the throat
- `halve(...).rotate(...)` composition producing a clean section view in the print variant
- `attach(parent, fuse=True)` for stacking barrel segments; `bbox(self.housing)` in the display variant to get the true housing top (the front fillet extends beyond `upper_housing_len`)
- Module-level `trunc_fillet_ring()` helper -- a custom-transform alternative that returns a composed Node directly

![Lens housing](images/M57Lens.png)

*left: display variant -- housing with clip-on hood floated above it; right: print variant -- housing halved and splayed for a section view alongside the inverted hood*

**Reference:** [derivations and predicates](../docs/components.md#derivations-loops-conditionals-namedtuple-fields) · [halve()](../docs/composition_helpers.md#halve) · [attach(fuse=True)](../docs/auto-eps_fuse_and_through.md) · [bbox()](../docs/introspection.md#bounding-boxes)

---

## Appendix: original source

[`s2-lens-v2b.scad`](s2-lens-v2b.scad) is the pre-SCADwright OpenSCAD file that `lens-housing.py` was ported from. Useful as a side-by-side read: roughly the same geometry in 463 lines of SCAD vs. ~320 lines of Python.
