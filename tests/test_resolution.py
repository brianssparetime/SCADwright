from scadwright import resolution
from scadwright.primitives import circle, cylinder, sphere
def test_resolution_sets_fn_on_sphere():
    with resolution(fn=64):
        s = sphere(r=5)
    assert s.fn == 64


def test_explicit_kwarg_beats_context():
    with resolution(fn=64):
        s = sphere(r=5, fn=16)
    assert s.fn == 16


def test_nested_resolution_inner_overrides():
    with resolution(fn=64):
        outer = sphere(r=5)
        with resolution(fn=16):
            inner = sphere(r=1)
        after_inner = sphere(r=5)
    assert outer.fn == 64
    assert inner.fn == 16
    assert after_inner.fn == 64


def test_resolution_fa_fs_independent():
    with resolution(fa=5):
        with resolution(fn=32):
            s = sphere(r=1)
    # fa inherited from outer, fn from inner
    assert s.fa == 5
    assert s.fn == 32


def test_no_context_leaves_fn_none():
    s = sphere(r=5)
    assert s.fn is None
    assert s.fa is None
    assert s.fs is None


def test_resolution_applies_to_cylinder_and_circle():
    with resolution(fn=48):
        cyl = cylinder(h=10, r=3)
        circ = circle(r=2)
    assert cyl.fn == 48
    assert circ.fn == 48
