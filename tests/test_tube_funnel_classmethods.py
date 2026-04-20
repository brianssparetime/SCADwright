"""Tests for Tube/Funnel equation-driven construction.

Replaced the former classmethod-based factories; the equation system now
solves for whichever parameter the user omits.
"""

import pytest

from scadwright.errors import ValidationError
from scadwright.shapes import Funnel, Tube


# --- Tube ---


def test_tube_id_and_od_solves_thk():
    t = Tube(h=10, id=8, od=10)
    assert t.id == 8 and t.od == 10 and t.thk == pytest.approx(1.0)


def test_tube_id_and_thk_solves_od():
    t = Tube(h=10, id=8, thk=1)
    assert t.id == 8 and t.od == pytest.approx(10.0) and t.thk == 1


def test_tube_od_and_thk_solves_id():
    t = Tube(h=10, od=10, thk=1)
    assert t.od == 10 and t.id == pytest.approx(8.0) and t.thk == 1


def test_tube_over_specified_consistent_ok():
    t = Tube(h=10, id=8, od=10, thk=1)
    assert t.thk == pytest.approx(1.0)


def test_tube_over_specified_inconsistent_raises():
    with pytest.raises(ValidationError, match="equation violated"):
        Tube(h=10, id=8, od=10, thk=2)


# --- Funnel ---


def test_funnel_ods_solve_ids():
    f = Funnel(h=10, thk=1, bot_od=20, top_od=10)
    assert f.bot_id == pytest.approx(18.0)
    assert f.top_id == pytest.approx(8.0)


def test_funnel_bot_od_top_id():
    f = Funnel(h=10, thk=1, bot_od=20, top_id=8)
    assert f.bot_id == pytest.approx(18.0)
    assert f.top_od == pytest.approx(10.0)


def test_funnel_bot_id_top_od():
    f = Funnel(h=10, thk=1, bot_id=18, top_od=10)
    assert f.bot_od == pytest.approx(20.0)
    assert f.top_id == pytest.approx(8.0)


def test_funnel_both_ids():
    f = Funnel(h=10, thk=1, bot_id=18, top_id=8)
    assert f.bot_od == pytest.approx(20.0)
    assert f.top_od == pytest.approx(10.0)
