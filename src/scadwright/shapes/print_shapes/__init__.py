"""Print-oriented shapes: infill panels, text, vents, joints."""

from scadwright.shapes.print_shapes.infill import GridPanel, HoneycombPanel, TriGridPanel
from scadwright.shapes.print_shapes.joints import GripTab, SnapHook, TabSlot
from scadwright.shapes.print_shapes.text import EmbossedLabel, TextPlate
from scadwright.shapes.print_shapes.vents import VentSlots

__all__ = [
    "EmbossedLabel",
    "GridPanel",
    "GripTab",
    "HoneycombPanel",
    "SnapHook",
    "TabSlot",
    "TextPlate",
    "TriGridPanel",
    "VentSlots",
]
