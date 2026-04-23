# Shape library

![Shape library catalog](images/hero.png)

SCADwright ships a library of ready-made shapes so you don't spend half your project reinventing tubes, gears, and screw holes. Every shape is either a Component (capitalized, with readable attributes and equation solving) or a factory function (lowercase, returns a primitive).

## Using shapes

Import from `scadwright.shapes`:

```python
from scadwright.shapes import Tube, SpurGear, Bolt, rounded_rect
```

Component shapes are parametric -- specify the dimensions you have, and the framework solves for the rest:

```python
t = Tube(h=10, id=8, thk=1)    # od solved = 10
t.od                             # readable without rendering
```

For a design where you'll reuse the same dimensions, specialize with a concrete subclass and reference it by name:

```python
class PowerSupplyStandoff(Standoff):
    od = 7
    id = 3
    h = 12

# Elsewhere in the design:
base.attach(PowerSupplyStandoff())
```

See [Organizing a project](../organizing_a_project.md#concrete-subclasses) for the full REUSABLE / CONCRETE / DESIGN pattern.

Shapes work with all the same operations as primitives: transforms, booleans, `attach()`, `through()`, `center=`, and `bbox()`.

For shapes that take explicit imports by group:

```python
from scadwright.shapes.gears import SpurGear, gear_dimensions
from scadwright.shapes.fasteners import Bolt, clearance_hole
```

Both styles work -- the top-level `scadwright.shapes` re-exports everything.

## Catalog

One line per shape; click the name to jump to the full entry.

### [2D profiles](profiles_2d.md)

- [`rounded_rect`](profiles_2d.md#rounded_rectx-y-r--fnnone) — rectangle with corners rounded by radius `r`
- [`rounded_square`](profiles_2d.md#rounded_squaresize-r--fnnone) — square (or rectangle) with rounded corners
- [`regular_polygon`](profiles_2d.md#regular_polygonsides-r) — regular N-gon inscribed in radius `r`
- [`Sector`](profiles_2d.md#sectorr-angles-fnnone) — pie slice between two angles
- [`Arc`](profiles_2d.md#arcr-angles-width-fnnone) — annular band between two angles
- [`RoundedEndsArc`](profiles_2d.md#roundedendsarcr-angles-width-end_r-fnnone) — arc with rounded (capsule) endpoints
- [`RoundedSlot`](profiles_2d.md#roundedslotlength-width-fnnone) — stadium / capsule: rectangle with semicircular caps
- [`Teardrop`](profiles_2d.md#teardropr-tip_angle45-cap_hnone) — FDM-friendly profile for horizontal holes
- [`Keyhole`](profiles_2d.md#keyholer_big-r_slot-slot_length) — circular head with a narrower slot extending out

### [Tubes and shells](tubes_and_shells.md)

- [`Tube`](tubes_and_shells.md#tubeh-idodthk) — hollow cylinder; specify any two of (id, od, thk)
- [`Funnel`](tubes_and_shells.md#funnelh-thk-top_-bot_) — tapered tube (truncated cone with wall thickness)
- [`RoundedBox`](tubes_and_shells.md#roundedboxsize-r) — box with every edge rounded by a sphere of radius `r`
- [`UShapeChannel`](tubes_and_shells.md#ushapechannelchannel_width-channel_height-outer_width-outer_height-wall_thk-channel_length) — three-sided rectangular tube open on one side
- [`RectTube`](tubes_and_shells.md#recttubeouter_w-outer_d-inner_w-inner_d-wall_thk-h) — rectangular hollow tube

### [Polyhedra](polyhedra.md)

- [`Prism`](polyhedra.md#prismsides-r-h) — N-sided prism (or frustum when top_r differs)
- [`Pyramid`](polyhedra.md#pyramidsides-r-h) — N-sided pyramid tapering to a point
- [`Prismoid`](polyhedra.md#prismoidbot_w-bot_d-top_w-top_d-h-shift0-0) — rectangular frustum with independent top dimensions
- [`Wedge`](polyhedra.md#wedgebase_w-base_h-thk-fillet0) — right-triangular prism; also the standard rib / gusset shape
- [`Tetrahedron`, `Octahedron`, `Dodecahedron`, `Icosahedron`](polyhedra.md#platonic-solids) — platonic solids inscribed in radius `r`
- [`Torus`](polyhedra.md#torusmajor_r-minor_r) — full or partial torus (quarter-toroid elbow via `angle=90`)
- [`Dome`](polyhedra.md#domer) — hemisphere with optional wall thickness
- [`SphericalCap`](polyhedra.md#sphericalcapany-two-of-six-params) — portion of a sphere sliced off by a plane
- [`Capsule`](polyhedra.md#capsuler-length) — pill / stadium solid: cylinder with hemispherical caps
- [`PieSlice`](polyhedra.md#pieslicer-angles-h) — `Sector` profile extruded along +z

### [Fillets and chamfers](fillets.md)

- [`ChamferedBox`](fillets.md#chamferedboxsize-fillet-or-chamfer) — box with edges rounded (fillet) or cut at 45° (chamfer)
- [`FilletMask`](fillets.md#filletmaskr-length-axisz) — quarter-cylinder fillet piece for axis-aligned edges
- [`ChamferMask`](fillets.md#chamfermasksize-length-axisz) — subtractable chamfer mask for axis-aligned edges
- [`FilletRing`](fillets.md#filletringid-od-base_angle) — right-triangle-cross-section ring between `id` and `od`
- [`Countersink`](fillets.md#countersinkshaft_d-head_d-head_depth-shaft_depth) — conical recess profile for flat-head screws
- [`Counterbore`](fillets.md#counterboreshaft_d-head_d-head_depth-shaft_depth) — cylindrical recess profile for socket-head screws

### [Fasteners and hardware](fasteners.md)

ISO metric data tables for M2–M12. Spec-driven Components offer `Cls.of("M5")` for canned ISO sizes and `Cls(spec=...)` for custom dimensions; `Bolt` keeps the simpler `size=` API.

- [`Bolt`](fasteners.md#boltsize-length) — ISO metric bolt with selectable head (socket, hex, flat, button, pan)
- [`HexNut`, `SquareNut`](fasteners.md#hexnutofsize--squarenutofsize) — ISO metric hex nut and DIN 562 square nut
- [`Standoff`](fasteners.md#standoffod-id-h) — screw-mount standoff column
- [`HeatSetPocket`](fasteners.md#heatsetpocketofsize) — pocket sized for a common brass heat-set insert
- [`CaptiveNutPocket`](fasteners.md#captivenutpocketofsize-depth) — hex pocket with insertion channel for a captive nut
- [`clearance_hole`, `tap_hole`](fasteners.md#clearance_holesize-depth--tap_holesize-depth) — pre-sized clearance / tap-drill cylinders

### [Gears and motion](gears.md)

Involute tooth profiles with published pitch radii.

- [`SpurGear`](gears.md#spurgearmodule-teeth-h) — involute spur gear
- [`RingGear`](gears.md#ringgearmodule-teeth-h-rim_thk) — internal gear: teeth on the inside of a ring
- [`Rack`](gears.md#rackmodule-teeth-length-h) — linear gear rack that meshes with a matching-module spur gear
- [`BevelGear`](gears.md#bevelgearmodule-teeth-h) — spur gear profile tapered to a cone
- [`Worm`, `WormGear`](gears.md#wormmodule-length-shaft_r--wormgearmodule-teeth-h) — screw gear and mating worm wheel pair

### [Mechanical components](mechanical.md)

- [`Bearing`](mechanical.md#bearingofseries-or-bearingspec) — ball-bearing dummy for fit-check (`Bearing.of("608")`, 6xx-series, etc.)
- [`GT2Pulley`](mechanical.md#gt2pulleyteeth-bore_d-belt_width) — GT2 timing belt pulley
- [`HTDPulley`](mechanical.md#htdpulleyteeth-bore_d-belt_width-pitch) — HTD (High Torque Drive) timing belt pulley
- [`DShaft`](mechanical.md#dshaftd-flat_depth-2d) — D-shaped shaft cross-section (2D)
- [`KeyedShaft`](mechanical.md#keyedshaftd-key_w-key_h-2d) — shaft cross-section with a keyway slot (2D)

### [Curves and sweep](curves.md)

- [`path_extrude`](curves.md#path_extrudeprofile-path) — sweep a 2D profile along a 3D path
- [`circle_profile`](curves.md#circle_profiler-segments16) — circular cross-section generator for `path_extrude`
- [`helix_path`](curves.md#helix_pathr-pitch-turns) — helical path generator
- [`bezier_path`](curves.md#bezier_pathcontrol_points-steps32) — cubic-Bezier path through control points
- [`catmull_rom_path`](curves.md#catmull_rom_pathpoints-steps_per_segment16) — smooth path through a sequence of points (Catmull-Rom spline)
- [`Helix`](curves.md#helix) — solid helix: circular cross-section swept along a helical path
- [`Spring`](curves.md#spring) — compression spring: helix with flat ends for stable resting

### [Curve transforms](transforms.md)

Registered as chainable methods on every shape.

- [`.along_curve()`](transforms.md#along_curvepath-count) — distribute copies of a shape along a path
- [`.bend()`](transforms.md#bendradius-axisz) — bend a shape along a circular arc around an axis
- [`.twist_copy()`](transforms.md#twist_copyangle-count) — duplicate and rotate copies through a total angle

### [Print-oriented shapes](print.md)

- [`HoneycombPanel`](print.md#honeycombpanelsize-cell_size-wall_thk) — hex-grid infill panel
- [`GridPanel`](print.md#gridpanelsize-cell_size-wall_thk) — square-grid infill panel
- [`TriGridPanel`](print.md#trigridpanelsize-cell_size-wall_thk) — triangular-grid infill panel
- [`TextPlate`](print.md#textplatelabel-plate_w-plate_h-plate_thk-depth-font_size) — rectangular plate with raised text
- [`EmbossedLabel`](print.md#embossedlabellabel-plate_w-plate_h-plate_thk-depth-font_size) — rectangular plate with engraved (recessed) text
- [`VentSlots`](print.md#ventslotswidth-height-thk-slot_width-slot_height-slot_count) — row of rectangular ventilation slots in a panel
- [`PolyHole`](print.md#polyholed-h-sides) — Laird-compensated polygonal hole cutter for accurate printed circles

### [Joints](joints.md)

Fit tolerances flow through the project-wide [Clearances](../clearances.md) system.

- [`TabSlot`](joints.md#tabslottab_w-tab_h-tab_d) — finger-joint tab with matching slot cutter (`finger` clearance)
- [`GripTab`](joints.md#griptabtab_w-tab_h-tab_d-taper) — press-fit tab for joining separately-printed parts
- [`SnapHook`](joints.md#snaphookarm_length-hook_depth-hook_height-thk-width) — cantilever snap-fit hook with a ramped barb
- [`SnapPin`](joints.md#snappind-h-slot_width-slot_depth-barb_depth-barb_height) — split-tined compliant pin with retaining barbs (`snap` clearance)
- [`AlignmentPin`](joints.md#alignmentpind-h-lead_in) — cylindrical locator; not load-bearing (`sliding` clearance)
- [`PressFitPeg`](joints.md#pressfitpegshaft_d-shaft_h-flange_d-flange_h-lead_in) — flanged peg for press-fit sheet-to-sheet assembly (`press` clearance)

### [Ecosystem](ecosystem.md)

- [`GridfinityBase`](ecosystem.md#gridfinitybasegrid_x-grid_y) — Gridfinity baseplate
- [`GridfinityBin`](ecosystem.md#gridfinitybingrid_x-grid_y-height_units) — Gridfinity storage bin
