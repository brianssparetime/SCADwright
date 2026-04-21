import pytest

from scadwright import emit_str
from scadwright.errors import ValidationError
from scadwright.shapes import Tube


def test_tube_id_thk_computes_od():
    t = Tube(h=10, id=10, thk=2, fn=24)
    assert t.od == 14.0


def test_tube_od_thk_computes_id():
    t = Tube(h=10, od=14, thk=2, fn=24)
    assert t.id == 10.0


def test_tube_id_od_computes_thk():
    t = Tube(h=10, id=10, od=14, fn=24)
    assert t.thk == 2.0


def test_tube_under_specified_raises():
    with pytest.raises(ValidationError, match="cannot solve"):
        Tube(h=10, id=10)


def test_tube_over_specified_consistent_ok():
    # Consistent over-specification is accepted under the equation model.
    t = Tube(h=10, id=10, od=14, thk=2)
    assert t.id == 10.0 and t.od == 14.0 and t.thk == 2.0


def test_tube_over_specified_inconsistent_raises():
    with pytest.raises(ValidationError, match="equation violated"):
        Tube(h=10, id=10, od=14, thk=3)  # 14 != 10 + 6


def test_tube_negative_id_from_bad_geometry_raises():
    """thk too large for od -> negative id; positive validator rejects."""
    with pytest.raises(ValidationError, match="must be positive"):
        Tube(h=10, od=4, thk=3)


def test_tube_emits_difference():
    t = Tube(h=10, id=8, od=10, fn=24)
    out = emit_str(t)
    assert "difference()" in out
    assert "cylinder(h=10, r=5" in out
    assert "cylinder(h=10, r=4" in out  # inner cutter; through() handles end-cap overlap
