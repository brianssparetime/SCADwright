"""Tests for wrap_2d: place a 2D profile on a host as raised or inset relief.

Structural tests run without OpenSCAD. One watertight check renders a planar
inset (straight edges, where the ASCII edge counter is exact) and is gated on
the integration marker. Curved-surface watertightness is verified manually with
trimesh and recorded in the design notes, since the in-suite counter over-counts
curved-facet tessellation.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from scadwright._custom_transforms.base import get_transform
from scadwright.anchor import get_node_anchors
from scadwright.ast.csg import Difference, Union
from scadwright.bbox import bbox
from scadwright.emit import emit, emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import cube, cylinder, scad_import, sphere, square


def _profile(w=10.0, h=6.0):
    """A filled rectangle with an exact, known bbox so sizing is deterministic."""
    return square([w, h], center=True)


def _expand(node):
    return get_transform(node.name).expand(node.child, **node.kwargs_dict())


# --- raised vs inset ---


def test_raised_is_union():
    n = cube([40, 40, 6], center=True).wrap_2d(profile=_profile(), relief=1.0, on="top", size=20)
    assert isinstance(_expand(n), Union)


def test_inset_is_difference():
    n = cube([40, 40, 6], center=True).wrap_2d(profile=_profile(), relief=-1.0, on="top", size=20)
    assert isinstance(_expand(n), Difference)


def test_inset_difference_keeps_host_first():
    host = cube([40, 40, 6], center=True)
    n = host.wrap_2d(profile=_profile(), relief=-1.0, on="top", size=20)
    diff = _expand(n)
    # First child is the host, so bbox(difference) stays the host's bbox.
    assert bbox(diff).max == pytest.approx(bbox(host).max)
    assert bbox(diff).min == pytest.approx(bbox(host).min)


# --- projection dispatch and defaults ---


def test_cylinder_defaults_to_wrap():
    cyl = cylinder(h=40, r=15)
    default = emit_str(cyl.wrap_2d(profile=_profile(), relief=1.0, on="outer_wall", size=20))
    wrap = emit_str(cyl.wrap_2d(profile=_profile(), relief=1.0, on="outer_wall", size=20, projection="wrap"))
    flat = emit_str(cyl.wrap_2d(profile=_profile(), relief=1.0, on="outer_wall", size=20, projection="flat"))
    assert default == wrap
    assert default != flat


def test_sphere_defaults_to_flat():
    sph = sphere(r=20)
    default = emit_str(sph.wrap_2d(profile=_profile(), relief=-1.0, on="+z", size=14))
    flat = emit_str(sph.wrap_2d(profile=_profile(), relief=-1.0, on="+z", size=14, projection="flat"))
    assert default == flat


def test_cone_defaults_to_flat():
    cone = cylinder(h=40, r1=20, r2=12)
    default = emit_str(cone.wrap_2d(profile=_profile(), relief=-1.0, on="outer_wall", size=14))
    flat = emit_str(cone.wrap_2d(profile=_profile(), relief=-1.0, on="outer_wall", size=14, projection="flat"))
    assert default == flat


def test_planar_defaults_to_flat():
    host = cube([40, 40, 6], center=True)
    default = emit_str(host.wrap_2d(profile=_profile(), relief=1.0, on="top", size=20))
    flat = emit_str(host.wrap_2d(profile=_profile(), relief=1.0, on="top", size=20, projection="flat"))
    assert default == flat


# --- segments knob (wrap only) ---


@pytest.mark.parametrize("n", [4, 12, 30])
def test_segments_sets_column_count(n):
    cyl = cylinder(h=40, r=15)
    scad = emit_str(cyl.wrap_2d(profile=_profile(), relief=1.0, on="outer_wall", size=20, segments=n))
    # One placement multmatrix per column.
    assert scad.count("multmatrix") == n


def test_segments_rejects_non_positive():
    cyl = cylinder(h=40, r=15)
    with pytest.raises(ValidationError, match="segments must be a positive"):
        emit_str(cyl.wrap_2d(profile=_profile(), relief=1.0, on="outer_wall", size=20, segments=0))


# --- size scaling ---


def test_size_scalar_sets_width_keeps_aspect():
    geom = cube([40, 40, 6], center=True).wrap_2d_geometry(
        profile=_profile(10, 6), relief=1.0, on="top", size=20
    )
    bb = bbox(geom)
    assert bb.max[0] - bb.min[0] == pytest.approx(20.0)
    assert bb.max[1] - bb.min[1] == pytest.approx(12.0)  # aspect preserved (6/10 * 20)


def test_size_pair_sets_both():
    geom = cube([40, 40, 6], center=True).wrap_2d_geometry(
        profile=_profile(10, 6), relief=1.0, on="top", size=(30, 10)
    )
    bb = bbox(geom)
    assert bb.max[0] - bb.min[0] == pytest.approx(30.0)
    assert bb.max[1] - bb.min[1] == pytest.approx(10.0)


def test_size_none_uses_profile_extent():
    geom = cube([40, 40, 6], center=True).wrap_2d_geometry(
        profile=_profile(8, 5), relief=1.0, on="top"
    )
    bb = bbox(geom)
    assert bb.max[0] - bb.min[0] == pytest.approx(8.0)
    assert bb.max[1] - bb.min[1] == pytest.approx(5.0)


# --- geometry sibling returns relief without the host ---


def test_geometry_sibling_excludes_host():
    host = cube([40, 40, 6], center=True)
    full = host.wrap_2d(profile=_profile(), relief=-1.0, on="top", size=20)
    geom = host.wrap_2d_geometry(profile=_profile(), relief=-1.0, on="top", size=20)
    assert isinstance(_expand(full), Difference)
    # The sibling is just the cutter, not a difference against the host.
    assert not isinstance(_expand(geom), Difference)


# --- decoration preserves host anchors ---


def test_decoration_preserves_anchors():
    cyl = cylinder(h=40, r=15)
    decorated = cyl.wrap_2d(profile=_profile(), relief=1.0, on="outer_wall", size=20)
    anchors = get_node_anchors(decorated)
    assert "outer_wall" in anchors
    assert anchors["outer_wall"].kind == "cylindrical"
    assert "top" in anchors


# --- errors as the documentation surface ---


def test_wrap_on_sphere_rejected():
    with pytest.raises(ValidationError, match="developable"):
        emit_str(sphere(r=20).wrap_2d(profile=_profile(), relief=1.0, on="+z", size=10, projection="wrap"))


def test_wrap_on_cone_rejected():
    with pytest.raises(ValidationError, match="non-manifold seams"):
        emit_str(cylinder(h=40, r1=20, r2=12).wrap_2d(
            profile=_profile(), relief=1.0, on="outer_wall", size=10, projection="wrap"))


def test_wrap_on_planar_rejected():
    with pytest.raises(ValidationError, match="nothing to wrap"):
        emit_str(cube([40, 40, 6], center=True).wrap_2d(
            profile=_profile(), relief=1.0, on="top", size=10, projection="wrap"))


def test_relief_zero_rejected():
    with pytest.raises(ValidationError, match="relief must be non-zero"):
        emit_str(cube([40, 40, 6], center=True).wrap_2d(profile=_profile(), relief=0, on="top", size=10))


def test_three_d_profile_rejected():
    with pytest.raises(ValidationError, match="must be 2D"):
        emit_str(cube([40, 40, 6], center=True).wrap_2d(
            profile=cube([5, 5, 5]), relief=1.0, on="top", size=10))


def test_hintless_import_rejected():
    with pytest.raises(ValidationError, match="no measurable 2D extent"):
        emit_str(cube([40, 40, 6], center=True).wrap_2d(
            profile=scad_import("logo.svg"), relief=1.0, on="top", size=10))


def test_angle_on_sphere_rejected():
    with pytest.raises(ValidationError, match="angle"):
        emit_str(sphere(r=20).wrap_2d(profile=_profile(), relief=1.0, on="+z", size=10, angle=30))


def test_bad_projection_rejected():
    with pytest.raises(ValidationError, match="projection must be"):
        emit_str(cube([40, 40, 6], center=True).wrap_2d(
            profile=_profile(), relief=1.0, on="top", projection="stamp"))


def test_bad_size_rejected():
    with pytest.raises(ValidationError, match="size must be"):
        emit_str(cube([40, 40, 6], center=True).wrap_2d(
            profile=_profile(), relief=1.0, on="top", size=(1, 2, 3)))


def test_placement_errors_are_relabeled():
    # The placement resolver is shared with add_text; the message names wrap_2d.
    with pytest.raises(ValidationError, match="wrap_2d: no anchor") as exc:
        emit_str(cube([40, 40, 6], center=True).wrap_2d(
            profile=_profile(), relief=1.0, on="nope", size=10))
    assert "add_text" not in str(exc.value)


# --- barrels and inner walls ---


def test_barrel_defaults_to_flat():
    from scadwright.shapes import Barrel

    bar = Barrel(h=40, end_r=15, bulge=6)
    default = emit_str(bar.wrap_2d(profile=_profile(), relief=-1.0, on="outer_wall", size=12))
    flat = emit_str(bar.wrap_2d(profile=_profile(), relief=-1.0, on="outer_wall", size=12, projection="flat"))
    assert default == flat


@pytest.mark.parametrize("bulge", [6, -5])
def test_barrel_flat_emits(bulge):
    from scadwright.shapes import Barrel

    bar = Barrel(h=40, end_r=15, bulge=bulge)
    for relief in (1.0, -1.0):
        node = bar.wrap_2d(profile=_profile(), relief=relief, on="outer_wall", size=12)
        assert "rotate_extrude" in emit_str(node)


def test_barrel_inner_wall_emits():
    from scadwright.shapes import Barrel

    bar = Barrel(h=40, end_r=15, bulge=6, thk=3)
    node = bar.wrap_2d(profile=_profile(), relief=-0.8, on="inner_wall", size=10)
    assert isinstance(_expand(node), Difference)


def test_inner_cylindrical_wall_flat_and_wrap():
    from scadwright.shapes import Tube

    tube = Tube(h=40, od=30, thk=6)
    # Inner cylindrical defaults to wrap (developable), like its outer twin.
    assert isinstance(_expand(tube.wrap_2d(profile=_profile(), relief=0.6, on="inner_wall", size=10)), Union)
    flat = tube.wrap_2d(profile=_profile(), relief=-0.6, on="inner_wall", size=10, projection="flat")
    assert isinstance(_expand(flat), Difference)


def test_barrel_relief_past_curvature_rejected():
    from scadwright.shapes import Barrel

    bar = Barrel(h=40, end_r=15, bulge=6)  # meridian_r ~= 36
    with pytest.raises(ValidationError, match="radius of curvature"):
        emit_str(bar.wrap_2d(profile=_profile(), relief=40.0, on="outer_wall", size=12))


def test_barrel_at_z_out_of_range_rejected():
    from scadwright.shapes import Barrel

    bar = Barrel(h=40, end_r=15, bulge=6)
    with pytest.raises(ValidationError, match="outside the barrel wall"):
        emit_str(bar.wrap_2d(profile=_profile(), relief=-1.0, on="outer_wall", size=12, at_z=40))


# --- integration: rendered planar inset is watertight (opt-in) ---


def _find_openscad():
    cmd = shutil.which("openscad")
    if cmd:
        return cmd
    mac = "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"
    return mac if Path(mac).exists() else None


def _stl_boundary_edge_count(stl_path):
    from collections import Counter

    verts = []
    for line in stl_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("vertex"):
            _, x, y, z = line.split()
            verts.append((round(float(x), 4), round(float(y), 4), round(float(z), 4)))
    edges = Counter()
    for i in range(0, len(verts), 3):
        tri = verts[i:i + 3]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            edges[tuple(sorted((tri[a], tri[b])))] += 1
    return sum(1 for cnt in edges.values() if cnt != 2)


@pytest.mark.integration
def test_planar_inset_renders_watertight(tmp_path):
    binary = _find_openscad()
    if binary is None:
        pytest.skip("openscad not found")
    # Axis-aligned cube + rectangular inset keeps integer vertex coords, so the
    # naive edge counter is exact.
    node = cube([40, 40, 6], center=True).wrap_2d(
        profile=_profile(12, 8), relief=-1.0, on="top", size=24
    )
    scad = tmp_path / "m.scad"
    stl = tmp_path / "m.stl"
    with open(scad, "w") as f:
        emit(node, f)
    subprocess.run(
        [binary, "--export-format", "asciistl", "-o", str(stl), str(scad)],
        capture_output=True, timeout=120,
    )
    assert stl.exists(), "openscad produced no STL"
    assert _stl_boundary_edge_count(stl) == 0
