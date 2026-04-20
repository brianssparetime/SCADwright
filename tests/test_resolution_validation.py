"""fn/fa/fs must be positive in every factory that accepts them (Group 1a/1b).

Pre-MajorReview2 only `sphere` validated `fn`. `fa`, `fs` were never
validated anywhere. This file pins the new rule: any factory that takes
fn/fa/fs rejects non-positive values, including ones inherited from a
resolution() context.
"""

import pytest

from scadwright import resolution
from scadwright.errors import ValidationError
from scadwright.extrusions import linear_extrude, rotate_extrude
from scadwright.primitives import (
    circle,
    cylinder,
    scad_import,
    sphere,
    text,
)


# --- fn must be positive on every factory ---


@pytest.mark.parametrize("name,call", [
    ("sphere",          lambda fn: sphere(r=1, fn=fn)),
    ("cylinder",        lambda fn: cylinder(h=1, r=1, fn=fn)),
    ("circle",          lambda fn: circle(r=1, fn=fn)),
    ("text",            lambda fn: text("x", fn=fn)),
    ("scad_import",     lambda fn: scad_import("x.stl", fn=fn)),
    ("linear_extrude",  lambda fn: linear_extrude(circle(r=1), height=1, fn=fn)),
    ("rotate_extrude",  lambda fn: rotate_extrude(circle(r=1).translate([5, 0, 0]), fn=fn)),
    ("offset",          lambda fn: circle(r=1).offset(r=1, fn=fn)),
])
def test_factory_rejects_negative_fn(name, call):
    with pytest.raises(ValidationError, match=f"{name} fn"):
        call(-5)


@pytest.mark.parametrize("name,call", [
    ("sphere",          lambda fn: sphere(r=1, fn=fn)),
    ("cylinder",        lambda fn: cylinder(h=1, r=1, fn=fn)),
    ("circle",          lambda fn: circle(r=1, fn=fn)),
])
def test_factory_rejects_zero_fn(name, call):
    with pytest.raises(ValidationError, match=f"{name} fn"):
        call(0)


# --- fa and fs must be positive ---


def test_sphere_rejects_negative_fa():
    with pytest.raises(ValidationError, match="sphere fa"):
        sphere(r=1, fa=-10)


def test_sphere_rejects_negative_fs():
    with pytest.raises(ValidationError, match="sphere fs"):
        sphere(r=1, fs=-1)


def test_cylinder_rejects_negative_fa():
    with pytest.raises(ValidationError, match="cylinder fa"):
        cylinder(h=1, r=1, fa=-5)


def test_circle_rejects_negative_fs():
    with pytest.raises(ValidationError, match="circle fs"):
        circle(r=1, fs=-0.1)


def test_linear_extrude_rejects_negative_fa():
    with pytest.raises(ValidationError, match="linear_extrude fa"):
        linear_extrude(circle(r=1), height=1, fa=-1)


# --- Context-inherited negatives are rejected too ---


def test_negative_fn_from_outer_resolution_rejected():
    with pytest.raises(ValidationError, match="sphere fn"):
        with resolution(fn=-10):
            sphere(r=1)


def test_negative_fa_from_outer_resolution_rejected():
    with pytest.raises(ValidationError, match="cylinder fa"):
        with resolution(fa=-5):
            cylinder(h=1, r=1)


# --- Valid values still work ---


def test_positive_resolution_accepted():
    s = sphere(r=5, fn=64)
    assert s.fn == 64


def test_resolution_none_stays_none():
    s = sphere(r=5)
    assert s.fn is None and s.fa is None and s.fs is None


def test_explicit_wins_over_negative_context():
    # If context has a bad value but the user passes a good one, the good
    # one wins and no error.
    with resolution(fn=-100):
        s = sphere(r=1, fn=32)
    assert s.fn == 32


# --- Bool guard still in effect ---


def test_fn_bool_rejected():
    with pytest.raises(ValidationError):
        sphere(r=1, fn=True)
