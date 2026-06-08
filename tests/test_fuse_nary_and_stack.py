"""N-ary ``fuse(*parts)`` and the ``stack`` / ``place_stack`` helpers.

The pure-Python tests cover the contact graph, the connectivity and
ambiguity raises, the eps-application structure, and the stack fold. The
opt-in integration tests (``-m integration`` / ``SCADWRIGHT_TEST_OPENSCAD=1``)
render to STL and check the result is watertight.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scadwright import emit, emit_str
from scadwright.api.fuse_mode import disable_eps_fuse
from scadwright.ast.csg import Union
from scadwright.boolops import fuse, union
from scadwright.composition_helpers import place_stack, stack
from scadwright.errors import ValidationError
from scadwright.ast.primitives import Cube
from scadwright.primitives import cube, cylinder
from scadwright.shapes import Tube
from scadwright import bbox


def _tube(z=0.0, od=20.0, id=10.0, h=10.0):
    return Tube(od=od, id=id, h=h).up(z)


# =====================================================================
# fuse(*parts): arity and kwarg gating
# =====================================================================


def test_fuse_three_parts_returns_union():
    result = fuse(cube([10, 10, 10]), cube([10, 10, 10]).up(10), cube([10, 10, 10]).up(20))
    assert isinstance(result, Union)


def test_fuse_one_part_raises():
    with pytest.raises(ValidationError, match="at least two parts"):
        fuse(cube([10, 10, 10]))


def test_fuse_flattens_list_args():
    parts = [cube([10, 10, 10]).up(10 * i) for i in range(3)]
    result = fuse(parts)  # one list arg, flattened to three parts
    assert isinstance(result, Union)


@pytest.mark.parametrize("kwargs", [
    {"on": "top"},
    {"using_anchor": "bottom"},
    {"from_anchor": "bottom"},
    {"bond": "overlap"},
    {"bridge": True},
])
def test_fuse_nary_rejects_single_contact_kwargs(kwargs):
    a = cube([10, 10, 10])
    b = cube([10, 10, 10]).up(10)
    c = cube([10, 10, 10]).up(20)
    with pytest.raises(ValidationError, match="don't apply to fuse"):
        fuse(a, b, c, **kwargs)


# =====================================================================
# fuse(*parts): connectivity and ambiguity
# =====================================================================


def test_fuse_nary_disconnected_raises():
    a = cube([10, 10, 10])
    b = cube([10, 10, 10]).up(10)      # touches a
    c = cube([10, 10, 10]).up(50)      # floats free
    with pytest.raises(ValidationError, match="do not form one connected body"):
        fuse(a, b, c)


def test_fuse_nary_disconnected_message_names_groups_and_tolerance():
    a = cube([10, 10, 10])
    b = cube([10, 10, 10]).up(50)
    c = cube([10, 10, 10]).up(100)
    with pytest.raises(ValidationError) as exc:
        fuse(a, b, c)
    msg = str(exc.value)
    assert "3 groups" in msg
    assert "coincidence tolerance" in msg
    assert "union(*parts)" in msg


def test_fuse_nary_same_plane_multi_anchor_fuses_once():
    """Two anchor pairs on the same contact plane (a custom anchor alongside
    the bbox face anchor) describe one surface. fuse should fuse it once, not
    raise and not emit a duplicate slab."""
    a = (cube([10, 10, 10])
         .with_anchor("extra", at=(2, 2, 10), normal=(0, 0, 1)))
    b = (cube([10, 10, 10]).up(10)
         .with_anchor("extra", at=(2, 2, 10), normal=(0, 0, -1)))
    c = cube([10, 10, 10]).up(20)
    result = fuse(a, b, c)
    assert isinstance(result, Union)
    # Two interfaces (a-b, b-c) of equal cubes: each grows exactly one side by
    # eps (the contained-footprint fast path), so two cubes carry a 10.01
    # dimension. If the a-b pair's two coincident anchors weren't deduped to one
    # contact, a-b would grow both its sides and the count would be three.
    assert emit_str(result).count("10.01") == 2


def test_distinct_contacts_collapses_same_surface_keeps_distinct():
    """The dedup that backs the multi-contact behavior: anchor pairs on one
    surface collapse to one contact; genuinely different surfaces stay."""
    from scadwright.anchor import get_node_anchors
    from scadwright.ast._surface_match import ContactMatch, distinct_contacts
    from scadwright.shapes import Tube

    a = (cube([10, 10, 10])
         .with_anchor("p1", at=(2, 2, 10), normal=(0, 0, 1))     # plane z=10
         .with_anchor("p2", at=(8, 8, 10), normal=(0, 0, 1))     # same plane z=10
         .with_anchor("side", at=(10, 5, 5), normal=(1, 0, 0)))  # plane x=10
    aa = get_node_anchors(a)

    def planar(name):
        return ContactMatch(name, aa[name], name, aa[name], "planar", False)

    # Two anchors on the same plane are one contact.
    assert len(distinct_contacts([planar("p1"), planar("p2")])) == 1
    # Different planes are two contacts.
    assert len(distinct_contacts([planar("p1"), planar("side")])) == 2

    # A planar and a curved surface are two contacts (never merged).
    ta = get_node_anchors(Tube(od=20, id=10, h=10))
    curved = ContactMatch(
        "outer_wall", ta["outer_wall"], "outer_wall", ta["outer_wall"],
        "cylindrical", True,
    )
    assert len(distinct_contacts([planar("p1"), curved])) == 2


def test_fuse_nary_off_center_contact_names_the_real_cause():
    """A part resting off-center on another touches it, but its bbox face
    center doesn't coincide, so it reads as disconnected. The error should
    name the coplanar-offset cause, not blame drift, and must not point at
    `attach` (which would reposition the deliberately-placed part)."""
    plate = cube([40, 40, 4])
    block_a = cube([10, 10, 10]).up(4).right(10)    # on the plate, off-center
    block_b = cube([10, 10, 10]).up(14).right(10)   # on block_a
    with pytest.raises(ValidationError) as exc:
        fuse(plate, block_a, block_b)
    msg = str(exc.value)
    assert "on the same plane but their reference points don't coincide" in msg
    assert "offset" in msg
    assert "attach" not in msg          # attach would reposition; wrong here
    assert "union(*parts)" in msg
    # Positioned parts are named by their shape, not the outer transform.
    assert "Cube" in msg
    assert "Translate" not in msg


# =====================================================================
# fuse(*parts): eps application structure
# =====================================================================


def test_fuse_nary_planar_grows_equal_footprints_no_slab():
    a = cube([10, 10, 10])
    b = cube([10, 10, 10]).up(10)
    c = cube([10, 10, 10]).up(20)
    fused = fuse(a, b, c)
    # Equal-footprint interfaces grow the contained side; no projection slab is
    # emitted, and the result is just the three parts (two of them grown).
    scad = emit_str(fused)
    assert scad.count("linear_extrude") == 0
    assert len(fused.children) == 3
    assert scad.count("10.01") == 2


def test_fuse_nary_planar_slabs_when_no_lever():
    # Annular tube caps have no parametric planar lever, so each interface falls
    # to the centered slab.
    a = Tube(od=10, id=4, h=10)
    b = Tube(od=10, id=4, h=10).up(10)
    c = Tube(od=10, id=4, h=10).up(20)
    scad = emit_str(fuse(a, b, c))
    assert scad.count("linear_extrude") == 2


# --- The grow fast path: containment decides the grown side, no shelf ---


def _grown_cube_dims(node):
    """Collect the size tuples of every Cube in the tree (depth-first)."""
    out = []
    if isinstance(node, Cube):
        out.append(node.size)
    for attr in ("child", "children"):
        v = getattr(node, attr, None)
        if isinstance(v, tuple):
            for c in v:
                out.extend(_grown_cube_dims(c))
        elif v is not None:
            out.extend(_grown_cube_dims(v))
    return out


def test_fuse_grows_the_contained_side_no_shelf():
    """A smaller cube centered on a larger one grows the *contained* side, so no
    eps shelf rings the joint. The larger cube keeps its declared size."""
    big = cube([20, 20, 10], center="xy")
    small = cube([10, 10, 10], center="xy").up(10)
    result = fuse(big, small)
    dims = _grown_cube_dims(result)
    # The 20x20 cube is untouched; the 10x10 cube grew on z to 10.01.
    assert (20.0, 20.0, 10.0) in dims
    assert any(
        abs(d[0] - 10.0) < 1e-9 and abs(d[1] - 10.0) < 1e-9 and abs(d[2] - 10.01) < 1e-6
        for d in dims
    )
    assert emit_str(result).count("linear_extrude") == 0


def test_fuse_disc_in_rect_grows_the_disc():
    """A small solid cylinder on a larger cube: the disc footprint is contained
    in the rect, so the cylinder grows and no slab is laid."""
    plate = cube([20, 20, 10], center="xy")
    pin = cylinder(d=8, h=10).up(10)
    assert emit_str(fuse(plate, pin)).count("linear_extrude") == 0


def test_fuse_off_axis_rotated_cube_falls_to_slab():
    """A cube rotated within the contact plane has no analytic footprint, so the
    contact falls to the sound centered slab rather than risking a shelf."""
    base = cube([10, 10, 10], center="xy")
    spun = cube([10, 10, 10], center="xy").rotate([0, 0, 30]).up(10)
    assert emit_str(fuse(base, spun)).count("linear_extrude") == 1


def test_fuse_pair_and_named_anchor_run_the_same_mechanism():
    """fuse(a, b) and fuse(a, b, on=..., using_anchor=...) are look-alike calls
    and must run the same grow-or-slab mechanism: equal cubes grow either way,
    with no slab."""
    a = cube([10, 10, 10])
    b = cube([10, 10, 10]).up(10)
    bare = fuse(a, b)
    # Name the same contact the auto-match finds: a's top against b's bottom.
    named = fuse(a, b, on="bottom", using_anchor="top")
    assert emit_str(bare).count("linear_extrude") == 0
    assert emit_str(named).count("linear_extrude") == 0
    assert emit_str(bare) == emit_str(named)


def test_fuse_nary_disable_eps_fuse_is_plain_union():
    a = cube([10, 10, 10])
    b = cube([10, 10, 10]).up(10)
    c = cube([10, 10, 10]).up(20)
    with disable_eps_fuse():
        fused = fuse(a, b, c)
    assert len(fused.children) == 3  # no slabs


def test_fuse_nary_eps_overlap_false_is_plain_union_but_still_validates():
    a = cube([10, 10, 10])
    b = cube([10, 10, 10]).up(10)
    c = cube([10, 10, 10]).up(20)
    fused = fuse(a, b, c, eps_overlap=False)
    assert len(fused.children) == 3
    # Validation still runs: a disconnected set raises even with eps off.
    with pytest.raises(ValidationError, match="connected body"):
        fuse(a, b, cube([10, 10, 10]).up(50), eps_overlap=False)


# =====================================================================
# fuse(*parts): curved concentric contacts
# =====================================================================


def test_fuse_nary_concentric_chain_rebuilds_in_place():
    """Three nested coaxial tubes: two cylindrical-wall contacts, no planar
    ones. Curved contacts rebuild one side per edge, so the result is a
    union of the (rebuilt) parts with no extra slab children."""
    outer = Tube(od=30, id=20, h=20)
    mid = Tube(od=20, id=10, h=20)
    inner = Tube(od=10, id=4, h=20)
    result = fuse(outer, mid, inner)
    assert isinstance(result, Union)
    assert len(result.children) == 3  # rebuilds, no slabs


def test_fuse_nary_two_curved_rebuilds_on_one_part_raises():
    """A central tube whose outer wall contacts two surrounding rings would
    need two rebuilds of itself; that does not compose and must raise."""
    mid = Tube(od=20, id=10, h=30)
    ring_a = Tube(od=30, id=20, h=10).up(0)
    ring_b = Tube(od=30, id=20, h=10).up(20)
    with pytest.raises(ValidationError, match="second curved-contact rebuild"):
        fuse(mid, ring_a, ring_b)


# =====================================================================
# stack / place_stack
# =====================================================================


def test_stack_returns_fused_union():
    result = stack(_tube(), _tube(), _tube())
    assert isinstance(result, Union)


def test_stack_heights_along_z():
    result = stack(_tube(), _tube(), _tube())
    bb = bbox(result)
    assert bb.min[2] == pytest.approx(0.0)
    assert bb.max[2] == pytest.approx(30.0)


def test_stack_single_part_returns_it():
    c = cube([10, 10, 10])
    assert stack(c) is c


def test_stack_zero_parts_raises():
    with pytest.raises(ValidationError, match="at least one operand"):
        stack()


def test_stack_axis_x():
    result = stack(cube([10, 10, 10]), cube([10, 10, 10]), cube([10, 10, 10]), axis="x")
    bb = bbox(result)
    assert bb.max[0] == pytest.approx(30.0)
    assert bb.max[2] == pytest.approx(10.0)


def test_stack_explicit_anchor_override():
    # rside/lside stacks along x without naming the axis.
    result = stack(
        cube([10, 10, 10]), cube([10, 10, 10]),
        on="rside", using_anchor="lside",
    )
    assert bbox(result).max[0] == pytest.approx(20.0)


def test_stack_bad_axis_raises():
    with pytest.raises(ValidationError, match="axis must be"):
        stack(cube([5, 5, 5]), cube([5, 5, 5]), axis="w")


def test_stack_half_given_anchor_pair_raises():
    # Passing only one of on=/using_anchor= would silently mix with the axis
    # default; require both or neither.
    with pytest.raises(ValidationError, match="both on= and using_anchor="):
        stack(cube([5, 5, 5]), cube([5, 5, 5]), on="rside")


def test_stack_unattachable_pair_raises_through_attach():
    # A nonexistent anchor name is rejected by attach; stack surfaces it.
    with pytest.raises(ValidationError):
        stack(cube([5, 5, 5]), cube([5, 5, 5]), on="nope", using_anchor="bottom")


def test_place_stack_returns_tuple_of_placed_parts():
    parts = place_stack(_tube(), _tube(), _tube())
    assert isinstance(parts, tuple)
    assert len(parts) == 3
    zmins = [round(bbox(p).min[2], 6) for p in parts]
    zmaxs = [round(bbox(p).max[2], 6) for p in parts]
    assert zmins == [0.0, 10.0, 20.0]
    assert zmaxs == [10.0, 20.0, 30.0]


def test_place_stack_is_exact_no_eps_overlap():
    # place_stack uses exact contact: each part keeps its own height, no
    # eps slab pokes past the mating face.
    a, b = place_stack(cube([10, 10, 10]), cube([10, 10, 10]))
    assert bbox(b).min[2] == pytest.approx(10.0)  # exactly on a's top, not 10 - eps


def test_place_stack_single_part_one_tuple():
    c = cube([10, 10, 10])
    parts = place_stack(c)
    assert parts == (c,)


# =====================================================================
# Integration: rendered output is watertight (opt-in)
# =====================================================================


def _find_openscad() -> str | None:
    cmd = shutil.which("openscad")
    if cmd:
        return cmd
    mac = "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"
    return mac if Path(mac).exists() else None


def _stl_boundary_edge_count(stl_path: Path) -> int:
    """Count edges incident to other than exactly two triangles in an ASCII
    STL (non-manifold or boundary edges). Zero means a closed, manifold mesh.
    """
    from collections import Counter

    verts: list[tuple] = []
    for line in stl_path.read_text().splitlines():
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


def _render_boundary_edges(node, tmp_path: Path) -> int:
    binary = _find_openscad()
    if binary is None:
        pytest.skip("openscad not found")
    scad = tmp_path / "m.scad"
    stl = tmp_path / "m.stl"
    with open(scad, "w") as f:
        emit(node, f)
    subprocess.run(
        [binary, "--export-format", "asciistl", "-o", str(stl), str(scad)],
        capture_output=True, timeout=120,
    )
    if not stl.exists():
        pytest.fail("openscad produced no STL")
    return _stl_boundary_edge_count(stl)


# Axis-aligned cubes keep exact integer vertex coordinates, so the simple
# vertex-quantizing edge count is reliable (curved-facet tessellation needs
# a tolerance-aware merge the naive checker doesn't do).


@pytest.mark.integration
def test_fuse_nary_planar_renders_watertight(tmp_path):
    fused = fuse(
        cube([10, 10, 10]), cube([10, 10, 10]).up(10), cube([10, 10, 10]).up(20),
    ).halve([0, 1, 0])
    assert _render_boundary_edges(fused, tmp_path) == 0


@pytest.mark.integration
def test_stack_renders_watertight(tmp_path):
    column = stack(
        cube([10, 10, 10]), cube([10, 10, 10]), cube([10, 10, 10]),
    ).halve([0, 1, 0])
    assert _render_boundary_edges(column, tmp_path) == 0
