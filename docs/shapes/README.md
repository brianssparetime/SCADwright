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

Shapes work with all the same operations as primitives: transforms, booleans, `attach()`, `through()`, `center=`, and `bbox()`.

For shapes that take explicit imports by group:

```python
from scadwright.shapes.gears import SpurGear, gear_dimensions
from scadwright.shapes.fasteners import Bolt, clearance_hole
```

Both styles work -- the top-level `scadwright.shapes` re-exports everything.

## Catalog

### [2D profiles](profiles_2d.md)

[`rounded_rect`](profiles_2d.md#rounded_rectx-y-r--fnnone), [`rounded_square`](profiles_2d.md#rounded_squaresize-r--fnnone), [`regular_polygon`](profiles_2d.md#regular_polygonsides-r), [`Sector`](profiles_2d.md#sectorr-angles-fnnone), [`Arc`](profiles_2d.md#arcr-angles-width-fnnone), [`RoundedEndsArc`](profiles_2d.md#roundedendsarcr-angles-width-end_r-fnnone), [`RoundedSlot`](profiles_2d.md#roundedslotlength-width-fnnone), [`Teardrop`](profiles_2d.md#teardropr-tip_angle45-cap_hnone), [`Keyhole`](profiles_2d.md#keyholer_big-r_slot-slot_length)

### [Tubes and shells](tubes_and_shells.md)

[`Tube`](tubes_and_shells.md#tubeh-idodthk), [`Funnel`](tubes_and_shells.md#funnelh-thk-top_-bot_), [`RoundedBox`](tubes_and_shells.md#roundedboxsize-r), [`UShapeChannel`](tubes_and_shells.md#ushapechannelchannel_width-channel_height-outer_width-outer_height-wall_thk-channel_length), [`RectTube`](tubes_and_shells.md#recttubeouter_w-outer_d-inner_w-inner_d-wall_thk-h)

### [Polyhedra](polyhedra.md)

[`Prism`](polyhedra.md#prismsides-r-h), [`Pyramid`](polyhedra.md#pyramidsides-r-h), [`Prismoid`](polyhedra.md#prismoidbot_w-bot_d-top_w-top_d-h-shift0-0), [`Wedge`](polyhedra.md#wedgebase_w-base_h-thk-fillet0), [`Tetrahedron`, `Octahedron`, `Dodecahedron`, `Icosahedron`](polyhedra.md#platonic-solids), [`Torus`](polyhedra.md#torusmajor_r-minor_r), [`Dome`](polyhedra.md#domer), [`SphericalCap`](polyhedra.md#sphericalcapany-two-of-six-params), [`Capsule`](polyhedra.md#capsuler-length), [`PieSlice`](polyhedra.md#pieslicer-angles-h)

### [Fillets and chamfers](fillets.md)

[`ChamferedBox`](fillets.md#chamferedboxsize-fillet-or-chamfer), [`FilletMask`](fillets.md#filletmaskr-length-axisz), [`ChamferMask`](fillets.md#chamfermasksize-length-axisz), [`FilletRing`](fillets.md#filletringid-od-base_angle), [`Countersink`](fillets.md#countersinkshaft_d-head_d-head_depth-shaft_depth), [`Counterbore`](fillets.md#counterboreshaft_d-head_d-head_depth-shaft_depth)

### [Fasteners and hardware](fasteners.md)

[`Bolt`](fasteners.md#boltsize-length), [`HexNut`, `SquareNut`](fasteners.md#hexnutsize--squarenutsize), [`Standoff`](fasteners.md#standoffod-id-h), [`HeatSetPocket`](fasteners.md#heatsetpocketsize), [`CaptiveNutPocket`](fasteners.md#captivenutpocketsize-depth), [`clearance_hole`, `tap_hole`](fasteners.md#clearance_holesize-depth--tap_holesize-depth) -- with ISO metric data tables for M2-M12

### [Gears and motion](gears.md)

[`SpurGear`](gears.md#spurgearmodule-teeth-h), [`RingGear`](gears.md#ringgearmodule-teeth-h-rim_thk), [`Rack`](gears.md#rackmodule-teeth-length-h), [`BevelGear`](gears.md#bevelgearmodule-teeth-h), [`Worm`, `WormGear`](gears.md#wormmodule-length-shaft_r--wormgearmodule-teeth-h) -- involute tooth profiles with published pitch radii

### [Mechanical components](mechanical.md)

[`Bearing`](mechanical.md#bearingseries-or-bearingspec) (608, 625, 6000-series, etc.), [`GT2Pulley`](mechanical.md#gt2pulleyteeth-bore_d-belt_width), [`HTDPulley`](mechanical.md#htdpulleyteeth-bore_d-belt_width-pitch), [`DShaft`](mechanical.md#dshaftd-flat_depth-2d), [`KeyedShaft`](mechanical.md#keyedshaftd-key_w-key_h-2d)

### [Curves and sweep](curves.md)

[`path_extrude`](curves.md#path_extrudeprofile-path), [`circle_profile`](curves.md#circle_profiler-segments16), [`helix_path`](curves.md#helix_pathr-pitch-turns), [`bezier_path`](curves.md#bezier_pathcontrol_points-steps32), [`catmull_rom_path`](curves.md#catmull_rom_pathpoints-steps_per_segment16), [`Helix`](curves.md#helix), [`Spring`](curves.md#spring)

### [Curve transforms](transforms.md)

[`.along_curve()`](transforms.md#along_curvepath-count), [`.bend()`](transforms.md#bendradius-axisz), [`.twist_copy()`](transforms.md#twist_copyangle-count) -- registered as chainable methods on every shape

### [Print-oriented shapes](print.md)

[`HoneycombPanel`](print.md#honeycombpanelsize-cell_size-wall_thk), [`GridPanel`](print.md#gridpanelsize-cell_size-wall_thk), [`TriGridPanel`](print.md#trigridpanelsize-cell_size-wall_thk), [`TextPlate`](print.md#textplatelabel-plate_w-plate_h-plate_thk-depth-font_size), [`EmbossedLabel`](print.md#embossedlabellabel-plate_w-plate_h-plate_thk-depth-font_size), [`VentSlots`](print.md#ventslotswidth-height-thk-slot_width-slot_height-slot_count), [`PolyHole`](print.md#polyholed-h-sides)

### [Joints](joints.md)

[`TabSlot`](joints.md#tabslottab_w-tab_h-tab_d), [`GripTab`](joints.md#griptabtab_w-tab_h-tab_d-taper), [`SnapHook`](joints.md#snaphookarm_length-hook_depth-hook_height-thk-width), [`SnapPin`](joints.md#snappind-h-slot_width-slot_depth-barb_depth-barb_height), [`AlignmentPin`](joints.md#alignmentpind-h-lead_in), [`PressFitPeg`](joints.md#pressfitpegshaft_d-shaft_h-flange_d-flange_h-lead_in)

### [Ecosystem](ecosystem.md)

[`GridfinityBase`](ecosystem.md#gridfinitybasegrid_x-grid_y), [`GridfinityBin`](ecosystem.md#gridfinitybingrid_x-grid_y-height_units)
