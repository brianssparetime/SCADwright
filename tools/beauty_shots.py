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
    Arc,
    Bearing,
    BevelGear,
    Bolt,
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
    Prism,
    Pyramid,
    Rack,
    RoundedBox,
    RoundedSlot,
    Sector,
    SnapHook,
    Spring,
    SpurGear,
    Standoff,
    TextPlate,
    Torus,
    Tube,
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
    {"out": "docs/shapes/images/snap-hook.png",       "component": SnapHook,       "kwargs": {"arm_length": 12, "hook_depth": 2, "hook_height": 2, "thk": 1.5, "width": 5}},

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

    # fillets.md
    {"out": "docs/shapes/images/chamfered-box.png", "component": ChamferedBox, "kwargs": {"size": (30, 20, 10), "fillet": 2}},
    {"out": "docs/shapes/images/counterbore.png",   "component": Counterbore,  "kwargs": {"shaft_d": 4, "head_d": 7, "head_depth": 4, "shaft_depth": 12}},

    # polyhedra.md
    {"out": "docs/shapes/images/prism.png",       "component": Prism,       "kwargs": {"sides": 6, "r": 12, "h": 20}},
    {"out": "docs/shapes/images/pyramid.png",     "component": Pyramid,     "kwargs": {"sides": 4, "r": 12, "h": 20}},
    {"out": "docs/shapes/images/icosahedron.png", "component": Icosahedron, "kwargs": {"r": 15}},
    {"out": "docs/shapes/images/torus.png",       "component": Torus,       "kwargs": {"major_r": 20, "minor_r": 5}},
    {"out": "docs/shapes/images/dome.png",        "component": Dome,        "kwargs": {"r": 15, "thk": 2}},
]


EXAMPLES = [
    {"out": "examples/images/BatteryBox-display.png", "script": "examples/battery-holder.py",   "variant": "display"},
    {"out": "examples/images/BatteryBox-print.png",   "script": "examples/battery-holder.py",   "variant": "print"},
    {"out": "examples/images/BracketSet-display.png", "script": "examples/shelf-bracket.py",    "variant": "display"},
    {"out": "examples/images/BoxAndLid-display.png",  "script": "examples/box-and-lid.py",      "variant": "display"},
    {"out": "examples/images/M57Lens-display.png",    "script": "examples/lens-housing.py",     "variant": "display"},
    {"out": "examples/images/ProjectBox-display.png", "script": "examples/electronics-case.py", "variant": "display"},
]
