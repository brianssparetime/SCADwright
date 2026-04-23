import pytest

from scadwright import emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import Funnel, RoundedBox
def test_funnel_basic():
    f = Funnel(h=20, thk=2, bot_id=10, top_id=14, fn=24)
    assert f.bot_od == 14.0
    assert f.top_od == 18.0


def test_funnel_od_form():
    f = Funnel(h=20, thk=2, bot_od=14, top_od=18, fn=24)
    assert f.bot_id == 10.0
    assert f.top_id == 14.0


def test_funnel_mixed_id_od():
    f = Funnel(h=20, thk=2, bot_id=10, top_od=18, fn=24)
    assert f.bot_od == 14.0
    assert f.top_id == 14.0


def test_funnel_both_id_and_od_consistent_ok():
    # Consistent over-specification for one end is accepted.
    f = Funnel(h=20, thk=2, bot_id=10, bot_od=14, top_id=14)
    assert f.top_od == 18.0


def test_funnel_both_id_and_od_inconsistent_raises():
    with pytest.raises(ValidationError, match="equation violated"):
        Funnel(h=20, thk=2, bot_id=10, bot_od=15, top_id=14)  # bot_od != 10+4


def test_funnel_under_specified_raises():
    with pytest.raises(ValidationError, match="cannot solve"):
        Funnel(h=20, thk=2, top_id=14)


def test_funnel_emits_difference_of_cones():
    f = Funnel(h=20, thk=2, bot_id=10, top_id=14, fn=24)
    out = emit_str(f)
    assert "difference()" in out
    assert "r1=" in out and "r2=" in out


def test_rounded_box_basic():
    b = RoundedBox(size=(20, 10, 5), r=1, fn=12)
    out = emit_str(b)
    assert "minkowski" in out
    assert "cube([18, 8, 3]" in out
    assert "sphere(r=1" in out


def test_rounded_box_radius_too_big_raises():
    with pytest.raises(ValidationError, match=r"all\(s > 2 \* r"):
        RoundedBox(size=(10, 10, 1), r=1, fn=12)


def test_rounded_box_bad_size_dim_raises():
    with pytest.raises(ValidationError, match=r"len\(size\) == 3"):
        RoundedBox(size=(10, 10), r=1)
