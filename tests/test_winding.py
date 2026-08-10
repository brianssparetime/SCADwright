"""Face winding: classification, normalization, and the library invariant.

OpenSCAD orders a face clockwise seen from outside, so a correct mesh
has a negative signed volume. Getting it wrong is invisible to every
other check in this suite: CGAL ignores winding, so exact renders and
STL exports pass, and the emitted text is a valid polyhedron either
way. Only OpenCSG shows it, and only inside a boolean.
"""

from __future__ import annotations

import logging

import pytest

import scadwright.shapes as S
from scadwright._winding import orient_for_openscad, signed_volume
from scadwright.ast.primitives import Polyhedron
from scadwright.emit import emit_str
from scadwright.errors import ValidationError
from scadwright.primitives import polyhedron

# The square pyramid from OpenSCAD's own manual: the reference for what
# "correctly wound" means.
PYRAMID_PTS = [(10, 10, 0), (10, -10, 0), (-10, -10, 0), (-10, 10, 0), (0, 0, 10)]
PYRAMID_FCS = [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4], [1, 0, 3], [2, 1, 3]]


def test_openscad_reference_mesh_has_negative_volume():
    # Pins the convention the rest of the module is written against.
    assert signed_volume(PYRAMID_PTS, PYRAMID_FCS) < 0


# --- Classification ---


def test_correct_mesh_passes_through_untouched():
    faces, problem = orient_for_openscad(PYRAMID_PTS, PYRAMID_FCS)
    assert problem is None
    assert faces == tuple(tuple(f) for f in PYRAMID_FCS)


def test_backwards_mesh_is_turned_round():
    backwards = [list(reversed(f)) for f in PYRAMID_FCS]
    faces, problem = orient_for_openscad(PYRAMID_PTS, backwards)
    assert problem is None
    assert signed_volume(PYRAMID_PTS, faces) < 0


def test_normalizing_is_idempotent():
    once, _ = orient_for_openscad(PYRAMID_PTS, [list(reversed(f)) for f in PYRAMID_FCS])
    twice, _ = orient_for_openscad(PYRAMID_PTS, once)
    assert once == twice


def test_a_seam_vertex_emitted_twice_is_not_reported_as_open():
    # Same coordinates, different index. Matching on exact equality
    # settles it without a tolerance; without that step this mesh
    # reports four boundary edges and the open warning fires wrongly.
    pts = PYRAMID_PTS + [PYRAMID_PTS[4]]
    fcs = [[0, 1, 4], [1, 2, 4], [2, 3, 5], [3, 0, 5], [1, 0, 3], [2, 1, 3]]
    faces, problem = orient_for_openscad(pts, fcs)
    assert problem is None


def test_inconsistent_mesh_is_reported_not_flipped():
    one_flipped = [f[:] for f in PYRAMID_FCS]
    one_flipped[1] = list(reversed(one_flipped[1]))
    faces, problem = orient_for_openscad(PYRAMID_PTS, one_flipped)
    assert problem is not None and problem.kind == "inconsistent"
    assert faces == tuple(tuple(f) for f in one_flipped), "must not guess"


def test_open_mesh_is_reported_not_flipped():
    no_cap = PYRAMID_FCS[:-1]
    faces, problem = orient_for_openscad(PYRAMID_PTS, no_cap)
    assert problem is not None and problem.kind == "open"
    assert faces == tuple(tuple(f) for f in no_cap)


def test_zero_volume_mesh_is_reported():
    # A closed shell with coincident surfaces has no outside to face.
    pts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    fcs = [[0, 1, 2], [0, 2, 3], [2, 1, 0], [3, 2, 0]]
    _, problem = orient_for_openscad(pts, fcs)
    assert problem is not None and problem.kind in ("degenerate", "inconsistent")


def test_scale_does_not_change_the_verdict():
    # The degeneracy threshold is relative to the mesh's own size, so a
    # part measured in microns isn't mistaken for a flat one.
    tiny = [(x * 1e-4, y * 1e-4, z * 1e-4) for x, y, z in PYRAMID_PTS]
    _, problem = orient_for_openscad(tiny, PYRAMID_FCS)
    assert problem is None


# --- The factory ---


def test_factory_emits_openscad_winding_whichever_way_it_goes_in():
    forward = polyhedron(PYRAMID_PTS, PYRAMID_FCS)
    backward = polyhedron(PYRAMID_PTS, [list(reversed(f)) for f in PYRAMID_FCS])
    assert forward.faces == backward.faces
    assert signed_volume(forward.points, forward.faces) < 0


def test_factory_raises_on_an_inconsistent_mesh():
    one_flipped = [f[:] for f in PYRAMID_FCS]
    one_flipped[1] = list(reversed(one_flipped[1]))
    with pytest.raises(ValidationError, match="not wound consistently"):
        polyhedron(PYRAMID_PTS, one_flipped)


def test_inconsistent_error_names_the_edge_and_both_faces():
    one_flipped = [f[:] for f in PYRAMID_FCS]
    one_flipped[1] = list(reversed(one_flipped[1]))
    with pytest.raises(ValidationError) as exc:
        polyhedron(PYRAMID_PTS, one_flipped)
    msg = str(exc.value)
    assert "faces[" in msg and "points[" in msg


def test_factory_warns_but_proceeds_on_an_open_mesh(caplog):
    from scadwright.primitives import _reset_mesh_warn_state_for_tests

    _reset_mesh_warn_state_for_tests()
    with caplog.at_level(logging.WARNING, logger="scadwright.polyhedron"):
        node = polyhedron(PYRAMID_PTS, PYRAMID_FCS[:-1])
    msgs = [r.getMessage() for r in caplog.records]
    assert any("not closed" in m for m in msgs), msgs
    assert any("almost always a mistake" in m for m in msgs), msgs
    assert node.faces == tuple(tuple(f) for f in PYRAMID_FCS[:-1])


def test_open_mesh_warns_once_per_site(caplog):
    from scadwright.primitives import _reset_mesh_warn_state_for_tests

    _reset_mesh_warn_state_for_tests()
    with caplog.at_level(logging.WARNING, logger="scadwright.polyhedron"):
        for _ in range(4):
            polyhedron(PYRAMID_PTS, PYRAMID_FCS[:-1])
    opens = [r for r in caplog.records if "not closed" in r.getMessage()]
    assert len(opens) == 1, f"expected one warning, got {len(opens)}"


# --- The library invariant ---
#
# Guards against the drift that had eight of the library's twelve
# polyhedron sites wound backwards. Every polyhedron the library emits
# must be closed, consistent, and wound OpenSCAD's way.


def _polyhedra_in(node):
    emit_str(node)
    found, stack, seen = [], [node], set()
    while stack:
        n = stack.pop()
        if id(n) in seen:
            continue
        seen.add(id(n))
        if isinstance(n, Polyhedron):
            found.append(n)
        for attr in ("child", "children", "source", "_built_tree"):
            v = getattr(n, attr, None)
            if v is not None:
                stack.extend(v if isinstance(v, (list, tuple)) else [v])
    return found


# Every shape in the library that emits a polyhedron. Keep this in step
# with the `polyhedron(` call sites under src/scadwright/shapes/ —
# test_every_polyhedron_source_is_covered below fails if one is missed,
# which is how the original drift went unnoticed.
LIBRARY_SHAPES = [
    ("Prism", lambda: S.Prism(r=10, sides=6, h=5)),
    ("Prism(tapered)", lambda: S.Prism(r=10, top_r=6, sides=5, h=8)),
    ("Pyramid", lambda: S.Pyramid(r=10, sides=5, h=8)),
    ("Prismoid", lambda: S.Prismoid(bot_w=20, bot_d=20, top_w=10, top_d=10, h=8)),
    ("ChamferedBox", lambda: S.ChamferedBox(size=(20, 20, 20), chamfer=2)),
    ("Tetrahedron", lambda: S.Tetrahedron(r=10)),
    ("Octahedron", lambda: S.Octahedron(r=10)),
    ("Dodecahedron", lambda: S.Dodecahedron(r=10)),
    ("Icosahedron", lambda: S.Icosahedron(r=10)),
    ("SnapHook", lambda: S.SnapHook(width=6, thk=2, arm_length=12,
                                    hook_depth=1.5, hook_height=2)),
    ("Helix", lambda: S.Helix(r=10, pitch=5, turns=2, wire_r=1, points_per_turn=12)),
    ("Spring", lambda: S.Spring(r=10, pitch=5, turns=2, wire_r=1, points_per_turn=12)),
    ("path_extrude", lambda: S.path_extrude(
        profile=S.circle_profile(r=2, segments=8),
        path=S.helix_path(r=10, pitch=5, turns=1, points_per_turn=12))),
    ("SnapPin", lambda: S.SnapPin(d=6, h=12, barb_depth=1, barb_height=1.5,
                                  slot_width=1.2, slot_depth=8, clearance=0.1)),
    ("loft", lambda: S.loft(
        sections=[S.circle_profile(r=6, segments=8), S.circle_profile(r=3, segments=8)],
        path=[(0, 0, 0), (0, 0, 10)])),
]


@pytest.mark.parametrize("name,make", LIBRARY_SHAPES, ids=[n for n, _ in LIBRARY_SHAPES])
def test_library_shapes_are_wound_for_openscad(name, make):
    polys = _polyhedra_in(make())
    assert polys, f"{name} emitted no polyhedron; the check would pass vacuously"
    for p in polys:
        pts = [tuple(x) for x in p.points]
        _, problem = orient_for_openscad(pts, [list(f) for f in p.faces])
        assert problem is None, f"{name}: {problem.kind} — {problem.message}"
        assert signed_volume(pts, p.faces) < 0, (
            f"{name} is wound backwards: it will vanish from OpenCSG "
            f"preview inside a difference() or intersection()"
        )


def test_every_polyhedron_call_site_in_the_library_is_covered():
    """No shape may emit a polyhedron that nothing above measures.

    The original drift went unnoticed across eight shapes because the
    survey that found it was partial. Counting call sites in the source
    and checking each one is reached closes that: a new generator that
    isn't added to LIBRARY_SHAPES fails here rather than shipping
    unmeasured.
    """
    import inspect
    import re
    from pathlib import Path

    import scadwright.primitives as prim
    from scadwright.shapes.curves import sweep
    from scadwright.shapes.fillets import chamfered_box
    from scadwright.shapes.joints import snap
    from scadwright.shapes.polyhedra import prism, regular
    from scadwright.shapes import three_d

    modules = [prism, regular, three_d, chamfered_box, snap, sweep]

    expected = set()
    for mod in modules:
        path = Path(inspect.getfile(mod))
        for i, line in enumerate(path.read_text().splitlines(), start=1):
            if re.search(r"\b_?polyhedron\(", line) and "def " not in line:
                expected.add((path.name, i))

    reached = set()
    original = prim.polyhedron

    def recorder(*args, **kwargs):
        frame = inspect.stack()[1]
        reached.add((Path(frame.filename).name, frame.lineno))
        return original(*args, **kwargs)

    patched = []
    for mod in modules:
        for attr in ("polyhedron", "_polyhedron"):
            if getattr(mod, attr, None) is original:
                setattr(mod, attr, recorder)
                patched.append((mod, attr))
    try:
        for _, make in LIBRARY_SHAPES:
            emit_str(make())
    finally:
        for mod, attr in patched:
            setattr(mod, attr, original)

    missed = expected - reached
    assert not missed, (
        f"these polyhedron call sites are never exercised by "
        f"LIBRARY_SHAPES, so their winding is unmeasured: {sorted(missed)}"
    )
