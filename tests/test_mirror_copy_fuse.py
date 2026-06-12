"""Opt-in ``mirror_copy(fuse=True)``: overlap the reflected copy by eps instead
of letting it abut, so a reflected seam doesn't export non-manifold after a
later cut. Off by default, so plain ``mirror_copy`` is unchanged.
"""

from __future__ import annotations

import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from scadwright import emit
from scadwright.api.fuse_mode import disable_eps_fuse
from scadwright.api.tolerances import default_eps
from scadwright.ast.csg import Union
from scadwright.ast.transforms import Mirror, Translate
from scadwright.composition_helpers import mirror_copy
from scadwright.errors import ValidationError
from scadwright.primitives import cube


# --- default (fuse=False) is unchanged: a plain union of original + bare Mirror ---


def test_default_is_plain_union_free_function():
    u = mirror_copy(cube([10, 10, 10], center="xy"), normal=[0, 0, 1])
    assert isinstance(u, Union)
    assert len(u.children) == 2
    assert isinstance(u.children[1], Mirror)


def test_default_is_plain_union_method():
    u = cube([10, 10, 10], center="xy").mirror_copy(normal=[0, 0, 1])
    assert isinstance(u.children[1], Mirror)


# --- fuse=True overlaps the reflection by eps toward the original's side ---


def test_fuse_shifts_mirror_toward_original_positive_side():
    # cube on the +z side of the plane -> its mirror shifts +eps along z to overlap.
    u = mirror_copy(cube([10, 10, 10], center="xy"), normal=[0, 0, 1], fuse=True)
    mc = u.children[1]
    assert isinstance(mc, Translate) and isinstance(mc.child, Mirror)
    assert mc.v == pytest.approx((0.0, 0.0, default_eps()))


def test_fuse_shifts_mirror_toward_original_negative_side():
    # cube on the -z side (the report's flipped-half orientation) -> shift -eps.
    u = mirror_copy(cube([10, 10, 10], center="xy").down(10), normal=[0, 0, 1], fuse=True)
    assert u.children[1].v == pytest.approx((0.0, 0.0, -default_eps()))


def test_fuse_method_form_shifts():
    u = cube([10, 10, 10], center="xy").mirror_copy(normal=[0, 0, 1], fuse=True)
    assert isinstance(u.children[1], Translate)
    assert u.children[1].v == pytest.approx((0.0, 0.0, default_eps()))


def test_fuse_multi_child_group_shifts_each():
    a = cube([6, 6, 10], center="xy").left(8)    # +z side
    b = cube([6, 6, 10], center="xy").right(8)
    u = mirror_copy(a, b, normal=[0, 0, 1], fuse=True)
    # 2 originals + 2 reflected; both reflected are shifted overlaps.
    assert len(u.children) == 4
    assert all(isinstance(c, Translate) for c in u.children[2:])


def test_fuse_explicit_eps():
    u = mirror_copy(cube([10, 10, 10], center="xy"), normal=[0, 0, 1], fuse=True, eps=0.05)
    assert u.children[1].v == pytest.approx((0.0, 0.0, 0.05))


def test_fuse_centered_child_is_not_shifted():
    # A child centered on the plane already overlaps its own mirror; no shift.
    u = mirror_copy(cube([10, 10, 10], center=True), normal=[0, 0, 1], fuse=True)
    assert isinstance(u.children[1], Mirror)


def test_fuse_normal_direction_is_arbitrary_axis():
    u = mirror_copy(cube([10, 10, 10], center="xy").right(10), normal=[1, 0, 0], fuse=True)
    # cube on +x side -> shift +eps along x.
    assert u.children[1].v == pytest.approx((default_eps(), 0.0, 0.0))


# --- disable_eps_fuse() suppresses the overlap ---


def test_disable_eps_fuse_suppresses_overlap():
    with disable_eps_fuse():
        u = mirror_copy(cube([10, 10, 10], center="xy"), normal=[0, 0, 1], fuse=True)
    assert isinstance(u.children[1], Mirror)


# --- a zero mirror normal raises (both forms) ---


def test_zero_normal_raises_free_function():
    with pytest.raises(ValidationError, match="non-zero vector"):
        mirror_copy(cube(5), normal=[0, 0, 0])


def test_zero_normal_raises_method():
    with pytest.raises(ValidationError, match="non-zero vector"):
        cube(5).mirror_copy(normal=[0, 0, 0])


# --- preservation: the overlap doesn't break a manifold cut (cubes are exact) ---


def _find_openscad():
    for name in ("openscad", "OpenSCAD"):
        p = shutil.which(name)
        if p:
            return p
    mac = "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"
    return mac if Path(mac).exists() else None


def _boundary_edges(node, tmp_path) -> int:
    binary = _find_openscad()
    if binary is None:
        pytest.skip("openscad not found")
    scad, stl = tmp_path / "m.scad", tmp_path / "m.stl"
    with open(scad, "w") as f:
        emit(node, f)
    subprocess.run(
        [binary, "--export-format", "asciistl", "-o", str(stl), str(scad)],
        capture_output=True, timeout=120,
    )
    if not stl.exists():
        pytest.fail("openscad produced no STL")
    verts = []
    for line in stl.read_text().splitlines():
        line = line.strip()
        if line.startswith("vertex"):
            _, x, y, z = line.split()
            verts.append((round(float(x), 4), round(float(y), 4), round(float(z), 4)))
    edges: Counter = Counter()
    for i in range(0, len(verts), 3):
        tri = verts[i:i + 3]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            edges[tuple(sorted((tri[a], tri[b])))] += 1
    return sum(1 for n in edges.values() if n != 2)


@pytest.mark.integration
def test_fuse_cube_mirror_cut_is_manifold(tmp_path):
    half = cube([10, 10, 10], center="xy").down(10)
    fused = mirror_copy(half, normal=[0, 0, 1], fuse=True).halve([0, 1, 0])
    assert _boundary_edges(fused, tmp_path) == 0
