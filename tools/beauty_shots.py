"""Beauty-shot manifest for render_beauty_shots.py.

Entries use curated parameter values chosen to read well visually — not
library defaults. Expand as new shapes land in the library.

Each COMPONENTS entry:
    out        — output PNG path (relative to repo root)
    component  — Component class            (OR use `build`)
    kwargs     — kwargs to instantiate it
    build      — zero-arg callable returning a Node (used when the shape
                 needs extrusion, transform chaining, or composition that
                 a plain (cls, kwargs) pair can't express)
    name       — optional; filename stem used for the temp .scad

Each EXAMPLES entry:
    out        — output PNG path
    script     — path to the example .py (relative to repo root)
    variant    — variant name passed to `scadwright build --variant=...`
"""

from scadwright.boolops import union
from scadwright.primitives import cube
from scadwright.shapes import (
    AlignmentPin,
    Arc,
    Bearing,
    BevelGear,
    Bolt,
    Capsule,
    ChamferedBox,
    Counterbore,
    DShaft,
    Dome,
    Funnel,
    GT2Pulley,
    GridfinityBase,
    GridfinityBin,
    Helix,
    HoneycombPanel,
    Icosahedron,
    KeyedShaft,
    Keyhole,
    PieSlice,
    PolyHole,
    PressFitPeg,
    Prism,
    Prismoid,
    Pyramid,
    Rack,
    RectTube,
    RoundedBox,
    RoundedSlot,
    Sector,
    SnapHook,
    SnapPin,
    Spring,
    SpurGear,
    Standoff,
    Teardrop,
    TextPlate,
    Torus,
    Tube,
    Wedge,
    bezier_path,
    rounded_rect,
)


# --- Factories for shapes that need extrusion/composition ---

def _2d_rounded_rect():
    return rounded_rect(30, 18, 3).linear_extrude(height=3)


def _2d_sector():
    return Sector(r=15, angles=(0, 120)).linear_extrude(height=3)


def _2d_rounded_slot():
    return RoundedSlot(length=30, width=6).linear_extrude(height=3)


def _2d_arc():
    return Arc(r=15, angles=(0, 120), width=3).linear_extrude(height=3)


def _2d_teardrop():
    return Teardrop(r=5).linear_extrude(height=3)


def _2d_keyhole():
    return Keyhole(r_big=5, r_slot=2, slot_length=10).linear_extrude(height=3)


def _d_shaft():
    return DShaft(d=10, flat_depth=1.0).linear_extrude(height=40)


def _keyed_shaft():
    return KeyedShaft(d=12, key_w=3, key_h=1.5).linear_extrude(height=40)


def _transform_bend():
    return cube([2, 2, 60]).bend(radius=15)


def _transform_twist_copy():
    return cube([20, 3, 1]).twist_copy(angle=45, count=8)


def _transform_along_curve():
    path = bezier_path([(0, 0, 0), (20, 0, 10), (40, 0, 0), (60, 0, 10)])
    return Bolt(size="M3", length=8).along_curve(path=path, count=6)


COMPONENTS = [
    # tubes_and_shells.md
    {"out": "docs/shapes/images/tube.png",        "component": Tube,       "kwargs": {"od": 20, "id": 16, "h": 30}},
    {"out": "docs/shapes/images/rounded-box.png", "component": RoundedBox, "kwargs": {"size": (40, 25, 15), "r": 3}},
    {"out": "docs/shapes/images/funnel.png",      "component": Funnel,     "kwargs": {"h": 30, "thk": 2, "bot_id": 8, "top_id": 30}},
    {"out": "docs/shapes/images/rect-tube.png",   "component": RectTube,   "kwargs": {"outer_w": 30, "outer_d": 20, "wall_thk": 2, "h": 10}},

    # curves.md
    {"out": "docs/shapes/images/helix.png",  "component": Helix,  "kwargs": {"r": 10, "wire_r": 1.5, "pitch": 5, "turns": 4}},
    {"out": "docs/shapes/images/spring.png", "component": Spring, "kwargs": {"r": 8, "wire_r": 1, "pitch": 4, "turns": 5}},

    # gears.md
    {"out": "docs/shapes/images/spur-gear.png",  "component": SpurGear,  "kwargs": {"module": 1.5, "teeth": 24, "h": 6}},
    {"out": "docs/shapes/images/rack.png",       "component": Rack,      "kwargs": {"module": 2, "teeth": 10, "length": 63, "h": 5}},
    {"out": "docs/shapes/images/bevel-gear.png", "component": BevelGear, "kwargs": {"module": 2, "teeth": 20, "h": 5, "cone_angle": 45}},

    # fasteners.md
    {"out": "docs/shapes/images/bolt.png",     "component": Bolt,     "kwargs": {"size": "M5", "length": 20, "head": "socket"}},
    {"out": "docs/shapes/images/standoff.png", "component": Standoff, "kwargs": {"od": 7, "id": 3, "h": 20}},

    # print.md
    {"out": "docs/shapes/images/honeycomb-panel.png", "component": HoneycombPanel, "kwargs": {"size": (80, 60, 3), "cell_size": 8, "wall_thk": 1}},
    {"out": "docs/shapes/images/text-plate.png",      "component": TextPlate,      "kwargs": {"label": "HELLO", "plate_w": 40, "plate_h": 15, "plate_thk": 2, "depth": 0.8, "font_size": 8}},
    {"out": "docs/shapes/images/poly-hole.png",       "component": PolyHole,       "kwargs": {"d": 10, "h": 20, "sides": 8}},

    # joints.md
    {"out": "docs/shapes/images/snap-hook.png",       "component": SnapHook,       "kwargs": {"arm_length": 12, "hook_depth": 2, "hook_height": 2, "thk": 1.5, "width": 5}},
    {"out": "docs/shapes/images/snap-pin.png",        "component": SnapPin,        "kwargs": {"d": 8, "h": 22, "slot_width": 1.5, "slot_depth": 15, "barb_depth": 1.2, "barb_height": 2.5, "clearance": 0.2}},
    {"out": "docs/shapes/images/alignment-pin.png",   "component": AlignmentPin,   "kwargs": {"d": 6, "h": 16, "lead_in": 2, "clearance": 0.1}},
    {"out": "docs/shapes/images/press-fit-peg.png",   "component": PressFitPeg,    "kwargs": {"shaft_d": 4, "shaft_h": 12, "flange_d": 9, "flange_h": 2, "lead_in": 1.2, "interference": 0.1}},

    # transforms.md
    {"out": "docs/shapes/images/bend.png",        "build": _transform_bend,        "name": "bend"},
    {"out": "docs/shapes/images/twist-copy.png",  "build": _transform_twist_copy,  "name": "twist-copy"},
    {"out": "docs/shapes/images/along-curve.png", "build": _transform_along_curve, "name": "along-curve"},

    # ecosystem.md
    {"out": "docs/shapes/images/gridfinity-base.png",   "component": GridfinityBase, "kwargs": {"grid_x": 3, "grid_y": 2}},
    {"out": "docs/shapes/images/gridfinity-bin.png",    "component": GridfinityBin,  "kwargs": {"grid_x": 2, "grid_y": 1, "height_units": 4}},
    # mechanical.md
    {"out": "docs/shapes/images/bearing.png",      "component": Bearing,    "kwargs": {"series": "608"}},
    {"out": "docs/shapes/images/gt2-pulley.png",   "component": GT2Pulley,  "kwargs": {"teeth": 20, "bore_d": 5, "belt_width": 6}},
    {"out": "docs/shapes/images/d-shaft.png",      "build": _d_shaft,       "name": "d-shaft"},
    {"out": "docs/shapes/images/keyed-shaft.png",  "build": _keyed_shaft,   "name": "keyed-shaft"},

    # profiles_2d.md
    {"out": "docs/shapes/images/rounded-rect.png", "build": _2d_rounded_rect, "name": "rounded-rect"},
    {"out": "docs/shapes/images/sector.png",       "build": _2d_sector,       "name": "sector"},
    {"out": "docs/shapes/images/rounded-slot.png", "build": _2d_rounded_slot, "name": "rounded-slot"},
    {"out": "docs/shapes/images/arc.png",          "build": _2d_arc,          "name": "arc"},
    {"out": "docs/shapes/images/teardrop.png",     "build": _2d_teardrop,     "name": "teardrop"},
    {"out": "docs/shapes/images/keyhole.png",      "build": _2d_keyhole,      "name": "keyhole"},

    # fillets.md
    {"out": "docs/shapes/images/chamfered-box.png", "component": ChamferedBox, "kwargs": {"size": (30, 20, 10), "fillet": 2}},
    {"out": "docs/shapes/images/counterbore.png",   "component": Counterbore,  "kwargs": {"shaft_d": 4, "head_d": 7, "head_depth": 4, "shaft_depth": 12}},

    # polyhedra.md
    {"out": "docs/shapes/images/prism.png",       "component": Prism,       "kwargs": {"sides": 6, "r": 12, "h": 20}},
    {"out": "docs/shapes/images/pyramid.png",     "component": Pyramid,     "kwargs": {"sides": 4, "r": 12, "h": 20}},
    {"out": "docs/shapes/images/prismoid.png",    "component": Prismoid,    "kwargs": {"bot_w": 25, "bot_d": 25, "top_w": 12, "top_d": 12, "h": 18}},
    {"out": "docs/shapes/images/wedge.png",       "component": Wedge,       "kwargs": {"base_w": 20, "base_h": 12, "thk": 30}},
    {"out": "docs/shapes/images/icosahedron.png", "component": Icosahedron, "kwargs": {"r": 15}},
    {"out": "docs/shapes/images/torus.png",       "component": Torus,       "kwargs": {"major_r": 20, "minor_r": 5}},
    {"out": "docs/shapes/images/dome.png",        "component": Dome,        "kwargs": {"r": 15, "thk": 2}},
    {"out": "docs/shapes/images/capsule.png",     "component": Capsule,     "kwargs": {"r": 6, "length": 30}},
    {"out": "docs/shapes/images/pie-slice.png",   "component": PieSlice,    "kwargs": {"r": 15, "angles": (0, 120), "h": 8}},
]


EXAMPLES = [
    {"out": "examples/images/BatteryBox-display.png", "script": "examples/battery-holder.py",   "variant": "display"},
    {"out": "examples/images/BatteryBox-print.png",   "script": "examples/battery-holder.py",   "variant": "print"},
    {"out": "examples/images/BracketSet-display.png", "script": "examples/shelf-bracket.py",    "variant": "display"},
    {"out": "examples/images/BoxAndLid-display.png",  "script": "examples/box-and-lid.py",      "variant": "display"},
    {"out": "examples/images/M57Lens-display.png",    "script": "examples/lens-housing.py",     "variant": "display"},
    {"out": "examples/images/ProjectBox-display.png", "script": "examples/electronics-case.py", "variant": "display"},
]
