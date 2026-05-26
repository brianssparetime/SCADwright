"""Unit tests for _alignment_translate.

Covers the three branches:
- concentric=True → return self unchanged
- shift magnitude under coincidence_tol() → return self unchanged
- otherwise → wrap in Translate by (host_pos - self_pos)
"""

from __future__ import annotations

import pytest

from scadwright.anchor import Anchor
from scadwright.ast.base import SourceLocation
from scadwright.ast.placement import _alignment_translate
from scadwright.ast.transforms import Translate
from scadwright.primitives import cube


def _loc():
    return SourceLocation.from_caller()


def _planar(pos, normal):
    return Anchor(position=pos, normal=normal, kind="planar")


def _cyl(pos, normal, *, length=10.0, radius=5.0, axis=(0.0, 0.0, 1.0), inner=False):
    return Anchor(
        position=pos, normal=normal, kind="cylindrical",
        axis=axis, length=length, radius=radius, inner=inner,
    )


def test_alignment_concentric_returns_self_unchanged():
    """For curved coaxial contact (concentric=True), no translate."""
    c = cube([5, 5, 5])
    s = _cyl((5, 0, 5), (1, 0, 0))
    h = _cyl((5, 0, 15), (-1, 0, 0), inner=True)
    result = _alignment_translate(c, s, h, concentric=True, loc=_loc())
    assert result is c


def test_alignment_zero_shift_returns_self_unchanged():
    """Planar contact where positions already coincide: no translate
    wrapper even though concentric is False."""
    c = cube([5, 5, 5])
    s = _planar((1.0, 2.0, 3.0), (0, 0, -1))
    h = _planar((1.0, 2.0, 3.0), (0, 0, 1))
    result = _alignment_translate(c, s, h, concentric=False, loc=_loc())
    assert result is c


def test_alignment_non_zero_shift_wraps_in_translate():
    """When self and host anchors don't coincide and contact isn't
    concentric: wrap in Translate by (host_pos - self_pos)."""
    c = cube([5, 5, 5])
    s = _planar((0, 0, 0), (0, 0, -1))
    h = _planar((3, 4, 5), (0, 0, 1))
    result = _alignment_translate(c, s, h, concentric=False, loc=_loc())
    assert isinstance(result, Translate)
    assert result.v == pytest.approx((3.0, 4.0, 5.0))
    assert result.child is c
