"""Print-oriented shapes: infill panels, vents, print aids.

Text decoration was previously a pair of Components (``TextPlate``,
``EmbossedLabel``); use the generic ``.add_text(...)`` chained method on
any host shape instead. See ``docs/add_text.md``.
"""

from scadwright.shapes.print_shapes.aids import PolyHole
from scadwright.shapes.print_shapes.infill import GridPanel, HoneycombPanel, TriGridPanel
from scadwright.shapes.print_shapes.vents import VentSlots

__all__ = [
    "GridPanel",
    "HoneycombPanel",
    "PolyHole",
    "TriGridPanel",
    "VentSlots",
]
