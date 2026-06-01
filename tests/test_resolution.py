from scadwright import resolution
from scadwright.primitives import circle, cylinder, sphere


def test_resolution_fa_fs_independent():
    with resolution(fa=5):
        with resolution(fn=32):
            s = sphere(r=1)
    # fa inherited from outer, fn from inner
    assert s.fa == 5
    assert s.fn == 32


def test_resolution_applies_to_cylinder_and_circle():
    with resolution(fn=48):
        cyl = cylinder(h=10, r=3)
        circ = circle(r=2)
    assert cyl.fn == 48
    assert circ.fn == 48
