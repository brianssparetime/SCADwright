"""Gear Components: spur, ring, rack, bevel, worm."""

from scadwright.shapes.gears.bevel import BevelGear
from scadwright.shapes.gears.involute import gear_dimensions
from scadwright.shapes.gears.rack import Rack
from scadwright.shapes.gears.ring import RingGear
from scadwright.shapes.gears.spur import SpurGear
from scadwright.shapes.gears.worm import Worm, WormGear

__all__ = [
    "BevelGear",
    "Rack",
    "RingGear",
    "SpurGear",
    "Worm",
    "WormGear",
    "gear_dimensions",
]
