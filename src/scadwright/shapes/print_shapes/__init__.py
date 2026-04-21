"""Print-oriented shapes: infill panels, text, vents, print aids."""

from scadwright.shapes.print_shapes.aids import PolyHole
from scadwright.shapes.print_shapes.infill import GridPanel, HoneycombPanel, TriGridPanel
from scadwright.shapes.print_shapes.text import EmbossedLabel, TextPlate
from scadwright.shapes.print_shapes.vents import VentSlots

__all__ = [
    "EmbossedLabel",
    "GridPanel",
    "HoneycombPanel",
    "PolyHole",
    "TextPlate",
    "TriGridPanel",
    "VentSlots",
]
