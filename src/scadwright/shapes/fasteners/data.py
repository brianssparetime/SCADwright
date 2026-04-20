"""ISO metric fastener data tables.

Dimensions in mm. Sources: ISO 4762, ISO 7380, DIN 934, ISO 4032.
"""

from __future__ import annotations

from collections import namedtuple

ScrewSpec = namedtuple("ScrewSpec", "d pitch head_d head_h clearance_d tap_d")
NutSpec = namedtuple("NutSpec", "d af h")  # af = across-flats (wrench size)
InsertSpec = namedtuple("InsertSpec", "d od h hole_d hole_depth")

# ISO metric socket-head cap screws (ISO 4762).
# d=nominal, pitch=coarse thread, head_d=head diameter, head_h=head height,
# clearance_d=through-hole diameter, tap_d=tap drill diameter.
METRIC_SOCKET_HEAD: dict[str, ScrewSpec] = {
    "M2":   ScrewSpec(d=2.0,  pitch=0.4,  head_d=3.8,  head_h=2.0,  clearance_d=2.4,  tap_d=1.6),
    "M2.5": ScrewSpec(d=2.5,  pitch=0.45, head_d=4.5,  head_h=2.5,  clearance_d=2.9,  tap_d=2.05),
    "M3":   ScrewSpec(d=3.0,  pitch=0.5,  head_d=5.5,  head_h=3.0,  clearance_d=3.4,  tap_d=2.5),
    "M4":   ScrewSpec(d=4.0,  pitch=0.7,  head_d=7.0,  head_h=4.0,  clearance_d=4.5,  tap_d=3.3),
    "M5":   ScrewSpec(d=5.0,  pitch=0.8,  head_d=8.5,  head_h=5.0,  clearance_d=5.5,  tap_d=4.2),
    "M6":   ScrewSpec(d=6.0,  pitch=1.0,  head_d=10.0, head_h=6.0,  clearance_d=6.6,  tap_d=5.0),
    "M8":   ScrewSpec(d=8.0,  pitch=1.25, head_d=13.0, head_h=8.0,  clearance_d=9.0,  tap_d=6.8),
    "M10":  ScrewSpec(d=10.0, pitch=1.5,  head_d=16.0, head_h=10.0, clearance_d=11.0, tap_d=8.5),
    "M12":  ScrewSpec(d=12.0, pitch=1.75, head_d=18.0, head_h=12.0, clearance_d=13.5, tap_d=10.2),
}

# ISO metric button-head screws (ISO 7380).
METRIC_BUTTON_HEAD: dict[str, ScrewSpec] = {
    "M2":   ScrewSpec(d=2.0,  pitch=0.4,  head_d=3.5,  head_h=1.0,  clearance_d=2.4,  tap_d=1.6),
    "M2.5": ScrewSpec(d=2.5,  pitch=0.45, head_d=4.5,  head_h=1.3,  clearance_d=2.9,  tap_d=2.05),
    "M3":   ScrewSpec(d=3.0,  pitch=0.5,  head_d=5.7,  head_h=1.5,  clearance_d=3.4,  tap_d=2.5),
    "M4":   ScrewSpec(d=4.0,  pitch=0.7,  head_d=7.6,  head_h=2.2,  clearance_d=4.5,  tap_d=3.3),
    "M5":   ScrewSpec(d=5.0,  pitch=0.8,  head_d=9.5,  head_h=2.8,  clearance_d=5.5,  tap_d=4.2),
    "M6":   ScrewSpec(d=6.0,  pitch=1.0,  head_d=10.5, head_h=3.3,  clearance_d=6.6,  tap_d=5.0),
    "M8":   ScrewSpec(d=8.0,  pitch=1.25, head_d=14.0, head_h=4.4,  clearance_d=9.0,  tap_d=6.8),
    "M10":  ScrewSpec(d=10.0, pitch=1.5,  head_d=17.5, head_h=5.5,  clearance_d=11.0, tap_d=8.5),
    "M12":  ScrewSpec(d=12.0, pitch=1.75, head_d=21.0, head_h=6.6,  clearance_d=13.5, tap_d=10.2),
}

# ISO metric hex nuts (DIN 934 / ISO 4032).
# af = across-flats (wrench size), h = nut height.
METRIC_HEX_NUT: dict[str, NutSpec] = {
    "M2":   NutSpec(d=2.0,  af=4.0,   h=1.6),
    "M2.5": NutSpec(d=2.5,  af=5.0,   h=2.0),
    "M3":   NutSpec(d=3.0,  af=5.5,   h=2.4),
    "M4":   NutSpec(d=4.0,  af=7.0,   h=3.2),
    "M5":   NutSpec(d=5.0,  af=8.0,   h=4.7),
    "M6":   NutSpec(d=6.0,  af=10.0,  h=5.2),
    "M8":   NutSpec(d=8.0,  af=13.0,  h=6.8),
    "M10":  NutSpec(d=10.0, af=16.0,  h=8.4),
    "M12":  NutSpec(d=12.0, af=18.0,  h=10.8),
}

# Common heat-set insert pocket dimensions.
# od = outer diameter of insert, h = insert length,
# hole_d = recommended hole diameter, hole_depth = recommended depth.
HEAT_SET_INSERT: dict[str, InsertSpec] = {
    "M2":  InsertSpec(d=2.0, od=3.2,  h=3.0,  hole_d=3.0,  hole_depth=3.5),
    "M3":  InsertSpec(d=3.0, od=4.0,  h=4.0,  hole_d=3.8,  hole_depth=4.5),
    "M4":  InsertSpec(d=4.0, od=5.6,  h=5.7,  hole_d=5.4,  hole_depth=6.2),
    "M5":  InsertSpec(d=5.0, od=7.0,  h=7.0,  hole_d=6.8,  hole_depth=7.5),
}


def get_screw_spec(size: str, head: str = "socket") -> ScrewSpec:
    """Look up screw dimensions by size string and head type."""
    tables = {
        "socket": METRIC_SOCKET_HEAD,
        "button": METRIC_BUTTON_HEAD,
    }
    table = tables.get(head)
    if table is None:
        raise ValueError(f"Unknown head type {head!r}. Use 'socket' or 'button'.")
    spec = table.get(size.upper())
    if spec is None:
        raise ValueError(f"Unknown screw size {size!r} for head={head!r}. Available: {sorted(table)}")
    return spec


def get_nut_spec(size: str) -> NutSpec:
    """Look up hex nut dimensions by size string."""
    spec = METRIC_HEX_NUT.get(size.upper())
    if spec is None:
        raise ValueError(f"Unknown nut size {size!r}. Available: {sorted(METRIC_HEX_NUT)}")
    return spec


def get_insert_spec(size: str) -> InsertSpec:
    """Look up heat-set insert dimensions by size string."""
    spec = HEAT_SET_INSERT.get(size.upper())
    if spec is None:
        raise ValueError(f"Unknown insert size {size!r}. Available: {sorted(HEAT_SET_INSERT)}")
    return spec
