"""Stock shape library: every Component whose ``build()`` uses
``difference()`` overrides ``tight_bbox`` to keep ``tight_bbox()`` and
downstream helpers like ``pack_on_bed`` working.

For 18 of the 19 affected shapes, the conservative bbox IS tight (the
Difference creates an interior void, hole, or notch — outer extents
unchanged), so the override returns ``bbox(self)`` to assert that. The
single exception is ``DShaft``, whose flat actually reduces the +x
extent; its override declares the truth explicitly.
"""

from __future__ import annotations

import pytest

from scadwright import bbox, tight_bbox
from scadwright.composition_helpers import pack_on_bed


# =============================================================================
# Drill-hole pattern: tight = bbox(self)
# =============================================================================
#
# For every shape in this set the conservative AABB equals the tight
# AABB (the Difference creates an interior void). One assertion shape
# fits all: tight_bbox(s) == bbox(s).


def _bbox_pair(part):
    return tight_bbox(part), bbox(part)


def test_tube_tight_equals_bbox():
    from scadwright.shapes import Tube
    t = Tube(h=10, id=8, thk=1)
    tb, lb = _bbox_pair(t)
    assert tb == lb


def test_funnel_tight_equals_bbox():
    from scadwright.shapes import Funnel
    f = Funnel(h=10, bot_id=10, top_id=6, thk=1)
    tb, lb = _bbox_pair(f)
    assert tb == lb


def test_filletring_outwards_tight_equals_bbox():
    from scadwright.shapes import FilletRing
    fr = FilletRing(id=4, od=10, base_angle=30)
    tb, lb = _bbox_pair(fr)
    assert tb == lb


def test_filletring_inwards_tight_equals_bbox():
    from scadwright.shapes import FilletRing
    fr = FilletRing(id=4, od=10, base_angle=30, slant="inwards")
    tb, lb = _bbox_pair(fr)
    assert tb == lb


def test_recttube_tight_equals_bbox():
    from scadwright.shapes import RectTube
    rt = RectTube(h=10, outer_w=20, outer_d=15, wall_thk=2)
    tb, lb = _bbox_pair(rt)
    assert tb == lb


def test_ushape_tight_equals_bbox():
    from scadwright.shapes import UShapeChannel
    u = UShapeChannel(
        channel_width=10, channel_height=8, wall_thk=2, channel_length=30,
    )
    tb, lb = _bbox_pair(u)
    assert tb == lb


def test_arc_tight_equals_bbox():
    from scadwright.shapes import Arc
    a = Arc(r=10, width=2, angles=(0, 90))
    tb, lb = _bbox_pair(a)
    assert tb == lb


def test_keyedshaft_tight_equals_bbox():
    from scadwright.shapes import KeyedShaft
    k = KeyedShaft(d=10, key_w=3, key_h=1.5)
    tb, lb = _bbox_pair(k)
    assert tb == lb


def test_snappin_tight_equals_bbox():
    from scadwright.shapes import SnapPin
    s = SnapPin(
        d=4, h=10, slot_width=1, slot_depth=5, barb_depth=0.5, barb_height=2,
    )
    tb, lb = _bbox_pair(s)
    assert tb == lb


def test_honeycomb_panel_tight_equals_bbox():
    from scadwright.shapes import HoneycombPanel
    p = HoneycombPanel(size=(40, 30, 3), cell_size=5, wall_thk=1)
    tb, lb = _bbox_pair(p)
    assert tb == lb


def test_grid_panel_tight_equals_bbox():
    from scadwright.shapes import GridPanel
    p = GridPanel(size=(40, 30, 3), cell_size=5, wall_thk=1)
    tb, lb = _bbox_pair(p)
    assert tb == lb


def test_trigrid_panel_tight_equals_bbox():
    from scadwright.shapes import TriGridPanel
    p = TriGridPanel(size=(40, 30, 3), cell_size=5, wall_thk=1)
    tb, lb = _bbox_pair(p)
    assert tb == lb


def test_vent_slots_tight_equals_bbox():
    from scadwright.shapes import VentSlots
    v = VentSlots(
        width=40, height=30, thk=2,
        slot_width=20, slot_height=2, slot_count=5,
    )
    tb, lb = _bbox_pair(v)
    assert tb == lb


def test_dome_tight_equals_bbox():
    from scadwright.shapes import Dome
    # Dome's build is an Intersection; the override returns the same
    # answer the generic walker would.
    d = Dome(sphere_r=10, cap_height=10)
    tb, lb = _bbox_pair(d)
    assert tb == lb


def test_fillet_mask_tight_equals_bbox():
    from scadwright.shapes import FilletMask
    m = FilletMask(r=2, length=20)
    tb, lb = _bbox_pair(m)
    assert tb == lb


def test_chamfer_mask_tight_equals_bbox():
    from scadwright.shapes import ChamferMask
    m = ChamferMask(size=2, length=20)
    tb, lb = _bbox_pair(m)
    assert tb == lb


def test_hex_nut_tight_equals_bbox():
    from scadwright.shapes import HexNut
    n = HexNut.of("M3")
    tb, lb = _bbox_pair(n)
    assert tb == lb


def test_square_nut_tight_equals_bbox():
    from scadwright.shapes import SquareNut
    n = SquareNut.of("M3")
    tb, lb = _bbox_pair(n)
    assert tb == lb


def test_gridfinity_base_tight_equals_bbox():
    from scadwright.shapes import GridfinityBase
    g = GridfinityBase(grid_x=2, grid_y=2)
    tb, lb = _bbox_pair(g)
    assert tb == lb


def test_gridfinity_bin_tight_equals_bbox():
    from scadwright.shapes import GridfinityBin
    g = GridfinityBin(grid_x=2, grid_y=2, height_units=3)
    tb, lb = _bbox_pair(g)
    assert tb == lb


# =============================================================================
# DShaft: explicit BBox computation (the flat reduces +x extent)
# =============================================================================


def test_dshaft_tight_reflects_flat():
    """The flat cuts into the circle from +x, reducing the +x extent
    from r to r - flat_depth. The conservative bbox would say +r —
    the override is the only thing that gets this right."""
    from scadwright import BBox
    from scadwright.shapes import DShaft

    s = DShaft(d=10, flat_depth=1)
    tb = tight_bbox(s)
    # r = 5, flat_depth = 1, so +x extent shrinks to 4.
    assert tb == BBox(min=(-5, -5, 0), max=(4, 5, 0))


def test_dshaft_tight_is_strictly_tighter_than_bbox():
    """DShaft is the one shape whose tight bbox differs from the
    conservative one — pin the inequality so a regression that
    silently aliases tight to conservative is caught."""
    from scadwright.shapes import DShaft

    s = DShaft(d=10, flat_depth=1)
    tb = tight_bbox(s)
    lb = bbox(s)
    assert tb.max[0] < lb.max[0]


# =============================================================================
# pack_on_bed integration: the user's failing case is the smoke test
# =============================================================================


def test_pack_on_bed_with_tube():
    """The original failure mode: pack_on_bed of a Tube raises because
    tight_bbox couldn't tighten through Difference. With the override,
    it works."""
    from scadwright.shapes import Tube
    out = pack_on_bed(Tube(h=10, id=8, thk=1))
    bb = bbox(out)
    assert bb.min == (0, 0, 0)


def test_pack_on_bed_with_mixed_difference_shapes():
    """A more complex layout: several stock shapes that all use
    Difference internally, packed together. None of them should raise
    after the overrides."""
    from scadwright.shapes import GridfinityBase, HexNut, Tube
    out = pack_on_bed(
        Tube(h=10, id=8, thk=1),
        HexNut.of("M3"),
        GridfinityBase(grid_x=1, grid_y=1),
        gap=5, plate=(300, 300),
    )
    bb = bbox(out)
    assert bb.min == (0, 0, 0)
