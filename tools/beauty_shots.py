"""Beauty-shot manifest for render_beauty_shots.py.

Entries use curated parameter values chosen to read well visually — not
library defaults. Expand as new shapes land in the library.

Each COMPONENTS entry:
    out        — output PNG path (relative to repo root)
    component  — Component class
    kwargs     — kwargs to instantiate it
    name       — optional; filename stem used for the temp .scad

Each EXAMPLES entry:
    out        — output PNG path
    script     — path to the example .py (relative to repo root)
    variant    — variant name passed to `scadwright build --variant=...`
"""

from scadwright.shapes import (
    Bolt,
    BevelGear,
    Funnel,
    Helix,
    HoneycombPanel,
    Rack,
    RoundedBox,
    SnapHook,
    Spring,
    SpurGear,
    Standoff,
    TextPlate,
    Tube,
)


COMPONENTS = [
    # tubes_and_shells.md
    {
        "out": "docs/shapes/images/tube.png",
        "component": Tube,
        "kwargs": {"od": 20, "id": 16, "h": 30},
    },
    {
        "out": "docs/shapes/images/rounded-box.png",
        "component": RoundedBox,
        "kwargs": {"size": (40, 25, 15), "r": 3},
    },
    {
        "out": "docs/shapes/images/funnel.png",
        "component": Funnel,
        "kwargs": {"h": 30, "thk": 2, "bot_id": 8, "top_id": 30},
    },

    # curves.md
    {
        "out": "docs/shapes/images/helix.png",
        "component": Helix,
        "kwargs": {"r": 10, "wire_r": 1.5, "pitch": 5, "turns": 4},
    },
    {
        "out": "docs/shapes/images/spring.png",
        "component": Spring,
        "kwargs": {"r": 8, "wire_r": 1, "pitch": 4, "turns": 5},
    },

    # gears.md
    {
        "out": "docs/shapes/images/spur-gear.png",
        "component": SpurGear,
        "kwargs": {"module": 1.5, "teeth": 24, "h": 6},
    },
    {
        "out": "docs/shapes/images/rack.png",
        "component": Rack,
        "kwargs": {"module": 2, "teeth": 10, "length": 63, "h": 5},
    },
    {
        "out": "docs/shapes/images/bevel-gear.png",
        "component": BevelGear,
        "kwargs": {"module": 2, "teeth": 20, "h": 5, "cone_angle": 45},
    },

    # fasteners.md
    {
        "out": "docs/shapes/images/bolt.png",
        "component": Bolt,
        "kwargs": {"size": "M5", "length": 20, "head": "socket"},
    },
    {
        "out": "docs/shapes/images/standoff.png",
        "component": Standoff,
        "kwargs": {"od": 7, "id": 3, "h": 20},
    },

    # print.md
    {
        "out": "docs/shapes/images/honeycomb-panel.png",
        "component": HoneycombPanel,
        "kwargs": {"size": (80, 60, 3), "cell_size": 8, "wall_thk": 1},
    },
    {
        "out": "docs/shapes/images/text-plate.png",
        "component": TextPlate,
        "kwargs": {"label": "HELLO", "plate_w": 40, "plate_h": 15, "plate_thk": 2, "depth": 0.8, "font_size": 8},
    },
    {
        "out": "docs/shapes/images/snap-hook.png",
        "component": SnapHook,
        "kwargs": {"arm_length": 12, "hook_depth": 2, "thk": 1.5, "width": 5},
    },
]


EXAMPLES = [
    {
        "out": "examples/images/BatteryBox-display.png",
        "script": "examples/battery-holder.py",
        "variant": "display",
    },
    {
        "out": "examples/images/BatteryBox-print.png",
        "script": "examples/battery-holder.py",
        "variant": "print",
    },
    {
        "out": "examples/images/BracketSet-display.png",
        "script": "examples/shelf-bracket.py",
        "variant": "display",
    },
    {
        "out": "examples/images/BoxAndLid-display.png",
        "script": "examples/box-and-lid.py",
        "variant": "display",
    },
    {
        "out": "examples/images/M57Lens-display.png",
        "script": "examples/lens-housing.py",
        "variant": "display",
    },
    {
        "out": "examples/images/ProjectBox-display.png",
        "script": "examples/electronics-case.py",
        "variant": "display",
    },
]
