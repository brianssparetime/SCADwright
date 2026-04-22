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
| Simple | [`simple-plate.py`](simple-plate.py) | Flat script, no Components -- primitives + booleans + render |
| Simple | [`convex-caliper.py`](convex-caliper.py) | One primitive + two shape-library Components stacked with `attach()`; single print variant |
| Intermediate | [`battery-holder.py`](battery-holder.py) | Custom transform per cradle, multi-instantiation, concrete subclass per battery type |
| Intermediate | [`v-block.py`](v-block.py) | Equation solving with trig (sin/tan); three concrete blocks pinned by different pairs; no `setup()` |
| Intermediate | [`box-and-lid.py`](box-and-lid.py) | Generator `build()`, cross-Component publishing, equations, print/display variants |
| Intermediate | [`lens-housing.py`](lens-housing.py) | Multiple instantiation (element stack), `halve` for section view, equations |
| Complex | [`electronics-case.py`](electronics-case.py) | Spec namedtuples, three custom transforms, multi-variant print-splitting |

---

## 0. [`simple-plate.py`](simple-plate.py)

A plate with two holes. No Components, no Design -- just primitives, booleans, and a `render()` call. This is the simplest possible SCADwright script and shows that SCADwright starts looking like OpenSCAD code.

---

## 1. [`convex-caliper.py`](convex-caliper.py)

A tool that slips over the jaws of a measuring caliper so it can span a part whose outer faces are both concave -- the central thickness of a biconcave lens, or the web left between two opposing countersunk holes drilled from each side of a plate. The spherical-cap feeler nests into each concavity so the caliper reads the distance between the feelers' outer domes. One primitive (`cylinder`) and two shape-library Components (`UShapeChannel`, `SphericalCap`) stacked with `attach()`.

- Composition with `attach()` -- each piece auto-positions on top of the previous one, no manual z-offsets
- Published attributes on shape-library Components (`clip.bottom_width`, `clip.outer_width`) drive downstream geometry
- Single `Design` with one `print` variant laying a mirrored pair side-by-side for a single print job

![Convex caliper](images/ConvexCaliper-print.png)

*print variant -- two mirrored heads on the bed, one per caliper jaw*

---

## 2. [`battery-holder.py`](battery-holder.py)

A desk-tray battery caddy: N cylindrical cells of a chosen type sit in wells along a rounded-corner tray. Each well has a tall rounded-slot finger window in the outer wall -- oriented along the battery's long axis -- so you can see the cell and pinch it out from the side.

- Shape-library 2D profile (`RoundedSlot`) extruded into a custom cutter
- Custom transform (`@transform("finger_scoop")`) applied once per cradle
- Per-battery concrete subclasses (`AA6Holder`, `Holder18650x4`)
- Dimension derivation in `setup`; multi-instantiation from a computed `cradle_positions` list
- Print and display `@variant`s

![Battery holder](images/BatteryBox.png)

*left: display variant -- six ghost AA cells seated in their cradles, tops protruding above the tray; right: print variant -- the bare tray showing the cradle geometry*

---

## 3. [`v-block.py`](v-block.py)

A machinist's V-block: a rectangular block with a V-shaped groove along its length, sized to cradle round stock tangent to both groove faces. Three concrete blocks, each pinned by a different pair of primary variables; the equations solve the rest.

- Trig in `equations` -- `sin` relates groove angle to the rod diameter it cradles; `tan` derives the opening width at the top
- All arithmetic lives in `equations`; **no `setup()`**, no `params=`, no explicit `Param`
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

---

## 4. [`box-and-lid.py`](box-and-lid.py)

A snap-on enclosure: a rounded-corner box with chamfered top/bottom edges and four interior screw pylons, plus a matching lid with countersunk corner holes and a centering lip that drops into the box mouth.

- Cross-Component dimension publishing -- `Lid` takes a `Box` instance as a Param and reads `box.outer_size`, `box.pylon_positions`, `box.screw` directly off it
- Custom transform (`chamfer_top`) applied to pylon tops
- Generator-style `build()` yielding parts to be auto-unioned
- Concrete subclasses (`MyBox`, `MyLid`) in the CONCRETE zone
- `params` with inequality constraints for positive and non-negative groups

![Box and lid](images/BoxAndLid.png)

*left: display variant -- lid floated above the box, centering lip and pylons visible through the gap; right: print variant -- box and inverted lid laid out on the bed*

---

## 5. [`lens-housing.py`](lens-housing.py)

An M57-threaded optical lens barrel: holds three stacked lens elements in grip-lip holders, with an expansion funnel for an element that's wider than the throat, a front fillet that continues the cone angle of a matching clip-on hood.

- `halve` composition helper producing a clean section view in the print variant
- `@classmethod` on `ElementHolder` to query dimensions before instantiation -- the classic chicken-and-egg pattern when one component's dimensions depend on another's
- `Element` namedtuple driving multi-instantiation (one holder per element)
- Derived dimensions computed in `setup`
- Concrete subclasses (`M57LensHousing`, `M57LensHood`); print-variant splay plus assembled display variant

![Lens housing](images/M57Lens.png)

*left: display variant -- housing with clip-on hood floated above it; right: print variant -- housing halved and splayed for a section view alongside the hood*

---

## 6. [`electronics-case.py`](electronics-case.py)

A parametric 3D-printable case for a Raspberry Pi 4. Base tray with standoffs at the PCB's mount holes, port cutouts for USB, HDMI, audio, and Ethernet connectors, and a screw-on lid with a ventilation slot array.

- Spec dataclasses (`PCBSpec`, `PortSpec`) as data contracts -- swapping in an `ArduinoUno` spec would produce a valid Arduino case with no Component changes
- Three custom transforms (`port_cutout`, `countersunk_hole`, `vent_slot_array`) each applied many times
- Cross-Component publishing -- `CaseLid` reads `base.mount_positions`, `base.outer_size`
- Multi-variant print-splitting: `print_base` and `print_lid` are bed-ready orientations, `display` is the assembled view
- Multi-instantiation driven by spec data (one standoff per mount hole, one port cutout per `PortSpec`)

![Project box](images/ProjectBox.png)

*left to right: display variant (assembled, PCB visible through the port cutouts), `print_base` (the tray alone, as it sits on the bed), `print_lid` (the lid flipped for the bed)*

---

## Appendix: original source

[`s2-lens-v2b.scad`](s2-lens-v2b.scad) is the pre-SCADwright OpenSCAD file that `lens-housing.py` was ported from. Useful as a side-by-side read: roughly the same geometry in 463 lines of SCAD vs. ~320 lines of Python.
