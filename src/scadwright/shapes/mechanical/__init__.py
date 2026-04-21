"""Mechanical components: bearings, pulleys, shaft profiles."""

from scadwright.shapes.mechanical.bearing import BEARING_DATA, Bearing, BearingSpec
from scadwright.shapes.mechanical.pulley import GT2Pulley, HTDPulley
from scadwright.shapes.mechanical.shaft import DShaft, KeyedShaft

__all__ = [
    "BEARING_DATA",
    "Bearing",
    "BearingSpec",
    "DShaft",
    "GT2Pulley",
    "HTDPulley",
    "KeyedShaft",
]
