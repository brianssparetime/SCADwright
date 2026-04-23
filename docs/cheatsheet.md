# SCADwright cheatsheet

One-page reference. Each section links to its full docs page for details.

## Imports

```python
from scadwright import (
    Component, Param, materialize,
    positive, non_negative, minimum, maximum, in_range, one_of,
    BBox, bbox, tight_bbox, tree_hash, Matrix, SourceLocation,
    emit, emit_str, render,
    resolution,
    clearances, Clearances, DEFAULT_CLEARANCES,
    arg, parse_args,
)
from scadwright.primitives import (
    cube, sphere, cylinder, polyhedron,
    square, circle, polygon,
    text, surface, scad_import,
)
from scadwright.boolops import union, difference, intersection, hull, minkowski
from scadwright.transforms import (
    translate, rotate, scale, mirror, color, resize, offset,
    multmatrix, projection,
    highlight, background, disable, only,
    transform, get_transform, list_transforms, Transform,
)
from scadwright.extrusions import linear_extrude, rotate_extrude
from scadwright.composition_helpers import (
    linear_copy, rotate_copy, mirror_copy, halve,
    multi_hull, sequential_hull,
)
from scadwright.shapes import (
    Tube, Funnel, RoundedBox, UShapeChannel, FilletRing,
    Arc, Sector, RoundedSlot, RoundedEndsArc,
    regular_polygon, rounded_rect, rounded_square,
)
from scadwright import math as scmath             # trig in degrees, SCAD-like
from scadwright.errors import ValidationError, BuildError, EmitError, SCADwrightError
from scadwright.asserts import assert_fits_in, assert_contains, assert_bbox_equal, assert_no_collision
from scadwright.debug import force_render, echo
```

## 3D primitives &nbsp; &nbsp;[→ full](primitives_3d.md)

```python
cube([10, 20, 30])                        # or cube(5) for a uniform cube
cube([10, 20, 30], center=True)           # centered on all axes
cube([10, 20, 30], center="xy")           # only X,Y centered
sphere(r=5)                               # or sphere(d=10)
cylinder(h=10, r=3)                       # or d=6
cylinder(h=10, r1=5, r2=2)                # truncated cone
cylinder(h=10, r=3, center=True)
polyhedron(points=[...], faces=[...])
surface("heightmap.png", center=True)     # import PNG/DAT heightmap
scad_import("part.stl")                   # STL auto-parses bbox
scad_import("p.svg", bbox=((0,0,0),(100,50,0)))  # non-STL needs hint
```

## 2D primitives &nbsp; &nbsp;[→ full](primitives_2d.md)

```python
square([10, 20])                          # or square(5); center options as cube
circle(r=5)                               # or d=10
polygon(points=[[x,y], ...])
polygon(points=[...], paths=[[0,1,2,3], [4,5,6,7]])  # holes
text("Hello", size=10, halign="center", valign="center")
text("Hello", bbox=((0,0,0),(40,10,0)))   # override bbox heuristic for a known font
```

## Transformations &nbsp; &nbsp;[→ full](transformations.md)

**Chained methods** (preferred for simple expressions):

```python
cube(10).translate([5, 0, 0])             # or .translate(x=5)
cube(10).rotate([0, 45, 0])               # Euler, or .rotate(angle=30, axis=[0,0,1])
cube(10).scale(2)                         # uniform, or .scale([2, 3, 1])
cube(10).mirror([1, 0, 0])                # normal of mirror plane
cube(10).color("red")                     # name, "#3399ff", or [r,g,b] 0..1
cube(10).resize([20, 20, 20])             # + auto=True / ["x", "y"] / [bool,bool,bool]
circle(r=5).offset(r=2)                   # 2D only; r rounds, delta sharp/chamfer
circle(r=5).offset(delta=1, chamfer=True)

# Shorthands:
cube(1).up(5)     .down(5)     .left(5)
                  .right(5)    .forward(5)   .back(5)
cube(1).flip("z")                         # mirror across XY
cube(1).red()     .steelblue(alpha=0.5)   # any SVG/X11 color name

# Placement helpers:
part.center_bbox()                        # AABB centered at origin
peg.attach(plate)                         # bottom of peg on top of plate
peg.attach(plate, face="rside", at="lside")  # side-by-side
peg.attach(plate, orient=True)            # rotate to align normals
pylon.attach(floor, fuse=True)            # overlap EPS into contact face
cylinder(h=10, r=3).through(box)          # extend cutter through coincident faces
cube(5).array(count=3, spacing=10, axis="x")   # alias over linear_copy
```

**Standalone (functional) forms** — all accept subject as first arg:

```python
translate(cube(10), [5, 0, 0])
rotate(cube(10), angle=30, axis=[0, 0, 1])
scale(cube(10), 2)
mirror(cube(10), [1, 0, 0])
color(cube(10), "red")
resize(cube(10), [20, 20, 20])
offset(circle(r=5), r=2)
multmatrix(cube(10), Matrix.translate(5, 0, 0))
projection(cube(10), cut=True)            # 3D → 2D
```

## Boolean operations &nbsp; &nbsp;[→ full](csg.md)

```python
union(a, b, c)             # or a | b | c
difference(a, b, c)        # or a - b - c  (first minus the rest)
intersection(a, b, c)      # or a & b & c
hull(a, b, c)              # smallest convex shape containing all
minkowski(a, sphere(r=1))  # round edges / sweep

union(a, [b, c], d)        # iterables flatten one level
```

## Composition helpers &nbsp; &nbsp;[→ full](composition_helpers.md)

```python
cube(5).linear_copy([10, 0, 0], n=5)                # 5 copies along X
cube(5).array(count=3, spacing=10, axis="y")        # simpler alias
shape.rotate_copy(angle=60, n=6, axis=[0, 0, 1])    # radial array
rotate_copy(60, shape1, shape2, n=6)                # standalone: shapes positional, n kwarg
shape.mirror_copy(normal=[1,0,0])                   # chained; also accepts positional vector
mirror_copy(cube(5).translate([10,0,0]), normal=[1,0,0])   # or ([1,0,0], shape) positional

hub.multi_hull(*spokes)                             # hull hub with each spoke
nodes_along_path.sequential_hull()                  # hull adjacent pairs

part.halve([0, 1, 0])                               # keep +y, cut -y
part.halve([1, 1, 0])                               # keep +x,+y quadrant
part.halve(y=1, size=200)                           # kwarg form + size override
```

## Extrusions &nbsp; &nbsp;[→ full](extrusions.md)

```python
circle(r=5).linear_extrude(height=10, twist=90, scale=2)
profile.rotate_extrude(angle=360)                   # default full sweep
linear_extrude(circle(r=5), height=10)              # standalone form
```

## Preview modifiers &nbsp; &nbsp;[→ full](transformations.md#preview-modifiers)

Affect preview only, not rendered output.

```python
part.highlight()           # #part — translucent red debug
part.background()          # %part — shown but not in final render
part.disable()             # *part — treated as absent
part.only()                # !part — render ONLY this subtree
```

## Components &nbsp; &nbsp;[→ full](components.md)

```python
class Tube(Component):
    equations = [
        "od == id + 2*thk",                # solver equality; variables auto-declared as floats
        "h, id, od, thk > 0",              # per-Param constraints
    ]

    def build(self):
        return difference(
            cylinder(h=self.h, r=self.od / 2),
            cylinder(h=self.h + 2, r=self.id / 2).down(1),
        )

t = Tube(h=10, id=8, thk=1)              # od solved = 10.0
t.od                                      # readable without building
render(t, "tube.scad")                    # build runs now, caches result
```

### `equations` list — five forms, classified by AST shape

```python
# 1. Solver equality (drives sympy; any one missing is solved):
"od == id + 2*thk"

# 2. Per-Param constraint (numeric RHS; attaches a validator):
"w, h, thk > 0"                            # comma-expansion OK

# 3. Cross-constraint (Param-vs-Param inequality):
"id < od"

# 4. Derivation (single =, identifier LHS; arbitrary Python RHS):
"pitch = spec.d + 2 * (clearance + wall_thk)"
"cradle_positions = tuple(-(count-1)*pitch/2 + i*pitch for i in range(count))"

# 5. Predicate (boolean; raises ValidationError if false):
"len(size) == 3"
"tray_depth < spec.length"
"all(e.dia <= throat for e in elements)"

# Optional input: prefix a variable with `?` to let the caller omit it.
# When omitted, the value is None. Constraints skip; predicates/derivations see None.
# Not allowed in `==` or on a derivation LHS.
"?fillet > 0"                                   # omit fillet and this skips
"(?fillet is None) != (?chamfer is None)"       # XOR: exactly one must be set
"edge = ?fillet if ?fillet else ?chamfer"       # pick whichever is set
```

Derivations and predicates see a curated namespace (`range`/`tuple`/`len`/`min`/`max`/`all`/`any`/math funcs) plus instance Params and earlier derivations. Both run after the solver and cross-constraints; predicates run after derivations.

### Declaring params

```python
# 1. equations (primary) — auto-declares floats, solves, constrains
equations = [
    "od == id + 2*thk",                # equality feeds the solver
    "h, id, od, thk > 0",              # constraint auto-declares + validates
    "base_angle > 0", "base_angle < 90",
]

# 2. params — only for unbounded floats that don't appear in any equation (rare)
params = "phase_offset"

# 3. Param — non-floats, defaults, enums
label = Param(str)
count = Param(int, positive=True)
mode = Param(str, default="A", one_of=("A","B"))

# 4. anchor — named attachment points (→ anchors.md)
mount = anchor(at="w/2, w/2, thk", normal=(0, 0, 1))
tip   = anchor(at=(0, 0, 10), normal=(0, 0, 1))
```

Equations require `pip install 'scadwright[equations]'` (sympy). Components with equations, derivations, or predicates are frozen after construction.

### Composite build(): yield parts, auto-unioned

```python
class Widget(Component):
    def build(self):                       # generator form
        yield cube(10)
        yield cylinder(h=20, r=2).up(10)
        yield sphere(r=3).up(20).right(5)
```

Returning a Node still works; prefer the generator form whenever a Component emits more than one part.

## Custom transforms &nbsp; &nbsp;[→ full](custom_transforms.md)

```python
@transform("chamfer_top")
def chamfer_top(node, *, depth):
    return minkowski(node, sphere(r=depth, fn=8))

cube([10, 10, 5]).chamfer_top(depth=1)    # now a method on every shape
```

Signature rule: positional shape first, `*` separator, everything else keyword-only. For transforms that need to inspect the shape's attributes, add `inline=True`.

## Shape library &nbsp; &nbsp;[→ full](shapes/README.md)

```python
# Tubes and shells:
Tube(h=10, id=8, thk=1)                           # hollow cylinder, od solved
Funnel(h=20, thk=2, bot_id=10, top_od=18)         # tapered tube
RoundedBox(size=(20, 10, 5), r=1)                 # minkowski-rounded box
UShapeChannel(wall_thk=2, channel_length=50, channel_width=10)
RectTube(outer_w=30, outer_d=20, wall_thk=2, h=10)   # rect sibling of Tube

# Polyhedra and basic 3D shapes:
Prism(sides=6, r=10, h=20)                        # hex prism (or frustum with top_r=)
Prismoid(bot_w=20, bot_d=20, top_w=10, top_d=10, h=15)    # rect frustum (+ shift=)
Wedge(base_w=10, base_h=6, thk=20)                # triangular-prism ramp/rib (+ fillet=)
Torus(major_r=20, minor_r=5)                      # donut (partial with angle=)
Dome(r=15, thk=2)                                 # hollow hemisphere
SphericalCap(sphere_r=20, cap_height=8)           # equation-solved cap
Capsule(r=3, length=20)                           # cylinder + hemisphere caps (z-axis)
PieSlice(r=10, angles=(0, 90), h=5)               # cylindrical sector

# Fillets:
ChamferedBox(size=(30, 20, 10), fillet=2)         # rounded edges (or chamfer=)
FilletMask(r=3, length=20)                        # subtractable edge fillet
FilletRing(id=20, od=30, base_angle=30)           # flange fillet ring

# Fasteners (spec-driven; .of(size) for canned ISO sizes):
Bolt(size="M3", length=10)                        # ISO metric, socket or button head
HexNut.of("M5")                                   # canned; publishes .af, .h, .d
HexNut(spec=NutSpec(d=4, af=7, h=3))              # custom dims
HeatSetPocket.of("M3")                            # publishes .hole_d, .hole_depth
CaptiveNutPocket.of("M3", depth=3)
clearance_hole("M3", depth=10)                    # sized for through-hole
Standoff(od=7, id=3, h=8)                         # mount post with anchor

# Gears:
SpurGear(module=2, teeth=20, h=5)                 # involute profile
Rack(module=2, teeth=10, length=63, h=5)          # linear gear

# Mechanical:
Bearing.of("608")                                 # fit-check dummy; publishes .id, .od, .width
Bearing(spec=BearingSpec(id=10, od=30, width=9))  # custom
GT2Pulley(teeth=20, bore_d=5, belt_width=6)

# Curves:
path_extrude(circle_profile(2), helix_path(10, 5, 3))  # sweep along path
Helix(r=10, wire_r=1, pitch=5, turns=3)           # solid helix
Spring(r=8, wire_r=0.5, pitch=3, turns=5)         # with flat ends

# Print:
HoneycombPanel(size=(80, 60, 3), cell_size=8, wall_thk=1)
TextPlate(label="HELLO", plate_w=40, plate_h=15, plate_thk=2, depth=0.5, font_size=8)
PolyHole(d=6, h=10, sides=8)                      # Laird-compensated FDM hole

# Joints (clearance auto-resolves via the clearance chain; pass `clearance=` to override):
TabSlot(tab_w=5, tab_h=3, tab_d=10)                      # finger joint (.slot cutter)
SnapHook(arm_length=10, hook_depth=2, hook_height=2, thk=1.5, width=5)
SnapPin(d=5, h=15, slot_width=1, slot_depth=10, barb_depth=0.8, barb_height=1.5)
AlignmentPin(d=4, h=8, lead_in=1)                        # locator pin (.socket cutter)
PressFitPeg(shaft_d=3, shaft_h=6, flange_d=6, flange_h=1.5, lead_in=0.5)

# 2D profiles:
rounded_rect(20, 10, r=2)                         # rounded rectangle
regular_polygon(sides=6, r=5)                     # n-gon
Arc(r=10, angles=(0, 90), width=2)                # ring segment
RoundedSlot(length=20, width=4)                   # capsule/stadium
Teardrop(r=3)                                     # FDM horizontal-hole profile
Keyhole(r_big=5, r_slot=2, slot_length=10)        # wall-mount keyhole
```

## Resolution (smoothness) &nbsp; &nbsp;[→ full](resolution.md)

```python
sphere(r=10, fn=64)                       # per-call wins
sphere(r=10, fa=6, fs=0.5)                # angle/size caps

with resolution(fn=64):                   # context for a block
    body = sphere(r=10)

class Gear(Component):                    # class-level default
    fn = 128
    def build(self): ...
```

**Precedence:** per-call > Component instance attr > Component class attr > outer `resolution()` context.

## Clearances (joint fit tolerances) &nbsp; &nbsp;[→ full](clearances.md)

```python
from scadwright import Clearances, DEFAULT_CLEARANCES, clearances

# Four named fit categories — sliding / press / snap / finger.
DEFAULT_CLEARANCES               # Clearances(sliding=0.1, press=0.1, snap=0.2, finger=0.2)

# Scope it:
with clearances(Clearances(sliding=0.05)):
    peg = AlignmentPin(d=4, h=8, lead_in=1)    # sliding=0.05

# Project-wide:
class MyProject(Design):
    clearances = Clearances(sliding=0.05, press=0.08, snap=0.2, finger=0.2)

# Per-call (highest priority):
AlignmentPin(d=4, h=8, lead_in=1, clearance=0.3)
```

**Precedence:** per-call kwarg > Component class attr (inner scope during build) > `with clearances()` scope > Design class attr > `DEFAULT_CLEARANCES`. Partial `Clearances(...)` specs compose per-field.

## Animation and viewpoints &nbsp; &nbsp;[→ full](animation.md)

```python
from scadwright.animation import t, cond, viewpoint

cube(10).rotate([0, 0, t() * 360])              # animate via $t
sphere(r=t() * 20 + 1)                          # symbolic primitive sizes
ping = cond(t() < 0.5, 2 * t(), 2 - 2 * t())    # SCAD ternary

with viewpoint(rotation=[60, 0, 30], distance=200):
    render(MODEL, "out.scad")                   # writes top-level $vpr/$vpd
```

## Variants &nbsp; &nbsp;[→ full](variants.md)

```python
from scadwright.design import Design, run, variant

class WidgetProject(Design):
    widget = MyWidget()

    @variant(fn=48, default=True)
    def print(self):
        return self.widget

    @variant(fn=48)
    def display(self):
        return union(self.widget, stand_in_hardware())

if __name__ == "__main__":
    run()                                  # replaces render() when using Design
```

## Math helpers &nbsp; &nbsp;[→ full](math.md)

```python
from scadwright import math as scmath
scmath.sin(45)   scmath.cos(0)   scmath.tan(45)            # trig in DEGREES
scmath.asin(1)   scmath.acos(0)  scmath.atan2(1, 1)
scmath.sqrt(16)  scmath.pow(2, 10)  scmath.log(100)        # log base 10
scmath.ln(2.71828)  scmath.exp(1)
scmath.round(2.5)                                          # 3 (half-away-from-zero)
scmath.norm([3, 4])          scmath.cross([1,0,0], [0,1,0])
scmath.min([3, 1, 2])        scmath.max(1, 2, 3)
scmath.abs(-5)               scmath.sign(-3)
```

## Matrix &nbsp; &nbsp;[→ full](matrix.md)

```python
Matrix.identity()
Matrix.translate(x, y=0, z=0)
Matrix.scale(x, y=None, z=None)
Matrix.rotate_x(deg)   Matrix.rotate_y(deg)   Matrix.rotate_z(deg)
Matrix.rotate_euler(x, y, z)                              # ZYX order
Matrix.rotate_axis_angle(deg, axis)
Matrix.mirror(normal)

a @ b                                       # compose (b first, then a)
m.apply_point((x, y, z))                    # transform a position
m.apply_vector((x, y, z))                   # direction only (no translation)
m.invert(tol=1e-9)                          # raises if |det| <= tol
m.determinant()    m.is_invertible(tol=1e-9)             # agree at matching tol
m.translation                               # (tx, ty, tz)
m.is_identity
```

## Bounding boxes and tests &nbsp; &nbsp;[→ full](introspection.md)

```python
bb = bbox(shape)                            # world AABB
bb.min   bb.max   bb.size   bb.center
bb.contains(other)    bb.overlaps(other)
bb.union(other)       bb.intersection(other)
bb.transformed(matrix)

h = tree_hash(shape)                        # 16-char hex, ignores source_location

from scadwright.asserts import *
assert_fits_in(part, ((0,0,0), (200,200,50)))
assert_contains(outer, inner)
assert_no_collision(a, b)
assert_bbox_equal(part, ((0,0,0), (10,10,10)))
```

## Emit and render &nbsp; &nbsp;[→ full](cli_and_args.md)

```python
render(shape, "out.scad")                                # writes a file
s = emit_str(shape)                                      # as a string
emit(shape, sys.stdout, pretty=True, debug=False)

render(shape, "out.scad",
       scad_use=["libs/helpers.scad"],                   # escape hatch:
       scad_include=["base.scad"])                       # legacy SCAD integration
```

## Debug helpers &nbsp; &nbsp;[→ full](debug.md)

```python
complex_part.force_render(convexity=5)                   # force CGAL in preview
cube(10).echo("size=10")                                 # wrap with echo
echo("starting")                                         # bare echo statement
echo("count:", n=4, _node=cube(1))                       # mixed args + wrap
```

## CLI &nbsp; &nbsp;[→ full](cli_and_args.md)

```python
# In widget.py:
from scadwright import arg
from scadwright.primitives import cube
width = arg("width", default=40, type=float, help="widget width")

MODEL = cube([width, width, 20])
```

```bash
scadwright build widget.py --width=80 --fn=128
scadwright build widget.py --variant=print -o widget_print.scad
scadwright build widget.py --help
scadwright preview widget.py                                # build + open in OpenSCAD GUI
scadwright render widget.py -o widget.stl                   # build + headless STL render
```

## Errors &nbsp; &nbsp;[→ full](errors_and_logging.md)

```python
from scadwright.errors import ValidationError, BuildError, EmitError, SCADwrightError
```

All SCADwright errors carry a `.source_location` with the user's file and line. `SCADwrightError` is the common base; catch it to catch anything SCADwright raises.
