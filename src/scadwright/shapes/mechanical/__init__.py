"""Mechanical components: bearings, pulleys, shaft profiles, clamps, grommets."""

from scadwright.shapes.mechanical.bearing import (
    BEARING_DATA, Bearing, BearingSpec, get_bearing_spec,
)
from scadwright.shapes.mechanical.clamp import TubeClamp
from scadwright.shapes.mechanical.grommet import Grommet
from scadwright.shapes.mechanical.pulley import GT2Pulley, HTDPulley
from scadwright.shapes.mechanical.shaft import DShaft, KeyedShaft

__all__ = [
    "BEARING_DATA",
    "Bearing",
    "BearingSpec",
    "DShaft",
    "GT2Pulley",
    "Grommet",
    "HTDPulley",
    "KeyedShaft",
    "TubeClamp",
    "get_bearing_spec",
]
