"""Fasteners: bolts, nuts, inserts, standoffs, clearance/tap holes."""

from scadwright.shapes.fasteners.data import (
    METRIC_SOCKET_HEAD,
    METRIC_BUTTON_HEAD,
    METRIC_HEX_NUT,
    HEAT_SET_INSERT,
    get_insert_spec,
    get_nut_spec,
    get_screw_spec,
)
from scadwright.shapes.fasteners.inserts import CaptiveNutPocket, HeatSetPocket
from scadwright.shapes.fasteners.nuts import HexNut, SquareNut
from scadwright.shapes.fasteners.screws import Bolt, clearance_hole, tap_hole
from scadwright.shapes.fasteners.standoff import Standoff

__all__ = [
    "Bolt",
    "CaptiveNutPocket",
    "HeatSetPocket",
    "HexNut",
    "SquareNut",
    "Standoff",
    "clearance_hole",
    "get_insert_spec",
    "get_nut_spec",
    "get_screw_spec",
    "tap_hole",
]
