# Mechanical components

Bearings, timing pulleys, shaft profiles, tube clamps, and grommets.

```python
from scadwright.shapes import (
    Bearing, GT2Pulley, HTDPulley,
    DShaft, KeyedShaft,
    TubeClamp, Grommet,
)
```

## `Bearing.of(series)` or `Bearing(spec=)`

Ball bearing dummy for fit-check and visualization. Use the `.of("608")` classmethod for canned 6xx-series sizes, or pass a `BearingSpec` for custom dimensions.

```python
from scadwright.shapes import Bearing, BearingSpec

Bearing.of("608")                                     # 8x22x7mm
Bearing.of("625")                                     # 5x16x5mm
Bearing(spec=BearingSpec(id=10, od=30, width=9))      # custom
```

You can read `id`, `od`, and `width` off the bearing. Available series: 604-609, 623-626, 6000-6005, 6200-6205.

![Bearing](images/bearing.png)

*`Bearing.of("608")` — 608-series ball bearing (8×22×7 mm).*

## `GT2Pulley(teeth, bore_d, belt_width)`

GT2 timing belt pulley (2mm pitch) with flanges and bore.

```python
GT2Pulley(teeth=20, bore_d=5, belt_width=6)
```

You can read `pitch_d` and `od` off the pulley.

![GT2 pulley](images/gt2-pulley.png)

*`GT2Pulley(teeth=20, bore_d=5, belt_width=6)` — 2mm-pitch timing belt pulley with flanges.*

## `HTDPulley(teeth, bore_d, belt_width, pitch)`

HTD timing belt pulley. Specify `pitch` (e.g. 5 for HTD-5M).

```python
HTDPulley(teeth=20, bore_d=8, belt_width=15, pitch=5)
```

## `DShaft(d, flat_depth)` (2D)

D-shaped shaft cross-section. Extrude for a 3D shaft.

```python
DShaft(d=5, flat_depth=0.5).linear_extrude(height=20)
```

![D-shaft](images/d-shaft.png)

*`DShaft(d=10, flat_depth=1.0).linear_extrude(height=40)` — motor shaft profile with a flat for a set-screw grip.*

## `KeyedShaft(d, key_w, key_h)` (2D)

Shaft cross-section with a rectangular keyway. Extrude for 3D.

```python
KeyedShaft(d=10, key_w=3, key_h=1.5).linear_extrude(height=30)
```

![Keyed shaft](images/keyed-shaft.png)

*`KeyedShaft(d=12, key_w=3, key_h=1.5).linear_extrude(height=40)` — shaft with a rectangular keyway.*

## `TubeClamp(tube_d|tube_w, clamp_length, wall_thk, bolt_offset)`

Clamp that holds a tube against a parent surface. Round (`tube_d`) or rectangular (`tube_w` plus optional `tube_h` — defaults to `tube_w` for square tubes), in two styles:

- `style="saddle"` (default) — open-top cradle. The tube rests in a semicircular or rectangular pocket cut into the top of a block. Mounting bolts pass through the body on either side of the tube into a parent below.
- `style="split"` — full enclosure with a saw-cut on top and a perpendicular pinch bolt that draws the two halves together, gripping the tube.

```python
TubeClamp(tube_d=12, clamp_length=20, wall_thk=3, bolt_offset=5)   # round saddle
TubeClamp(tube_w=10, clamp_length=20, wall_thk=3, bolt_offset=5)   # square saddle
TubeClamp(tube_w=10, tube_h=15, clamp_length=20, wall_thk=3, bolt_offset=5)
TubeClamp(tube_d=12, clamp_length=20, wall_thk=3, bolt_offset=5, style="split")
TubeClamp(tube_d=12, clamp_length=30, wall_thk=3, bolt_offset=5, n_bolts=4)   # corners
```

The tube axis runs along +X. The clamp's base sits on z=0, so the bbox-derived `bottom` anchor is the mount-to-parent face. Default `screw="M3"`, `n_bolts=2`, `saw_cut_width=0.5`. For 4-bolt placement, the axial inset of the corner holes from each end defaults to `wall_thk + 2`; override with `bolt_axial_inset=`.

Common applications: drone-frame arm mounts, conduit and PVC pipe holders, garden-hose mounts, cable bundle clamps, robot-arm members, telescope tube saddles.

## `Grommet(plate_thk, plate_hole_d, flange_d)`

Vibration-isolating sleeve that sits in a plate's hole. The barrel passes through the plate; flanges above and below sandwich the plate. An optional equatorial groove around the barrel seats in the plate hole — useful for printable TPU grommets where the groove is what catches the plate edge.

```python
Grommet(plate_thk=1.6, plate_hole_d=4, flange_d=6)              # default M3 bore, flange_thk=0.6
Grommet(plate_thk=2,   plate_hole_d=4, flange_d=7, screw="M3")
Grommet(plate_thk=1.6, plate_hole_d=4, flange_d=6,
        groove_depth=0.3, groove_width=0.8)                      # TPU with seat groove
```

Sits centered on the origin with its axis along +Z. Total height is `plate_thk + 2 * flange_thk`; the bottom flange face is at z=0. Defaults: `flange_thk=0.6`, `slip=0.1` (barrel undersize), `screw="M3"`, `groove_depth=0` (no groove).

Anchors: `top` and `bottom` are planar with `rim_radius=flange_d/2`, so `add_text` arc-on-rim and `attach(angle=, at_radial=)` both work on either flange face.

Common applications: flight-controller soft-mounting on a drone frame, sensor isolation on machine equipment, panel-mount strain relief for cabling.

### See also

- [Gears](gears.md) -- spur gears, racks, and worm drives to mount on shafts
- [Fasteners](fasteners.md) -- bolts and standoffs for mounting
- [`hole_grid`](../composition_helpers.md#hole_grid) -- generate a rectangular grid of holes for FC stacks, VESA mounts, vent arrays
