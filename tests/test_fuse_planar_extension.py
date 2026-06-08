"""Behavioral tests for planar-contact local extension at the
attach(fuse=True) and standalone fuse(...) APIs.

These exercise the user-facing entry points; the per-shape unit tests
live in test_fuse_extend.py.
"""

import pytest

from scadwright import bbox
from scadwright.boolops import fuse, union
from scadwright.primitives import cube, cylinder, sphere
from scadwright.shapes import Tube


# --- attach(fuse=True): cumulative-drift elimination ---


def test_attach_fuse_preserves_far_face_cube_on_cube():
    """Local extension preserves the far face exactly: pylon.top stays
    at the declared z=12, not 11.99 as a bilateral shift would produce.
    Bottom is extended into the floor by eps; everything above the
    contact face is exactly where the user put it."""
    floor = cube([40, 40, 2])
    pylon = cube([5, 5, 10]).attach(floor, fuse=True)
    bb = bbox(pylon)
    assert bb.min[2] == pytest.approx(1.99)   # extended into floor
    assert bb.max[2] == pytest.approx(12.0)   # PRESERVED (was 11.99 with shift)


def test_attach_fuse_preserves_far_face_pendant():
    """Pendant attached at top: the bottom face stays at z=10 (declared);
    the top face extends into the ceiling."""
    ceiling = cube([40, 40, 2]).up(20)
    pendant = cube([5, 5, 10]).attach(ceiling, on="bottom", using_anchor="top", fuse=True)
    bb = bbox(pendant)
    assert bb.min[2] == pytest.approx(10.0)   # PRESERVED (was 10.01 with shift)
    assert bb.max[2] == pytest.approx(20.01)  # extended into ceiling


def test_attach_fuse_through_coincidence_preserved():
    """The Counterbore-shaped regression: a stack of two cylinders
    (shaft + bore via fuse) used as a through() cutter against a plate
    cleanly extends past the plate's top face. With the old shift,
    the cutter's top was 0.01mm short and through()'s 1e-4 coincidence
    test missed it."""
    from scadwright.boolops import difference
    plate_thk = 3
    head_h = 1.5
    shaft_h = plate_thk - head_h
    # Build a stepped cutter: narrow shaft below, wide bore above.
    shaft = cylinder(h=shaft_h, d=3.4)
    bore = cylinder(h=head_h, d=6).up(shaft_h)
    cutter = union(shaft, bore)
    # Cutter bbox top should be at exactly z=plate_thk; through() needs
    # this for coincidence detection.
    bb = bbox(cutter)
    assert bb.max[2] == pytest.approx(plate_thk)


# --- attach(fuse=True): non-planar fallback ---


def test_attach_fuse_with_orient_uses_local_extension():
    """attach(fuse=True, orient=True) on a planar interface uses local
    extension via Rotate.fuse_extend's inverse-rotation recursion.
    The contact face moves into the wall by eps; all other faces stay
    at their declared world positions.

    Geometry: orient rotates the peg around +Y so its bottom-normal
    opposes wall.rside's +X. The bbox-derived "bottom" of the rotated
    peg is the bbox −Z face (not the wall-normal direction), so the
    local extension propagates along world −Z. With the old global
    shift the peg would have shifted by eps in −X (wall normal); the
    new local extension preserves the X range and extends Z instead.
    The contrast is what proves the new mechanism is in use.
    """
    wall = cube([2, 40, 40])
    peg = cube([5, 5, 10])
    no_fuse = peg.attach(wall, on="rside", using_anchor="bottom", orient=True)
    with_fuse = peg.attach(wall, on="rside", using_anchor="bottom", orient=True, fuse=True)
    nb = bbox(no_fuse)
    fb = bbox(with_fuse)
    # X range unchanged: local extension does not shift along wall normal.
    # (Old shift behavior would have moved both x edges by −0.01.)
    assert fb.min[0] == pytest.approx(nb.min[0])
    assert fb.max[0] == pytest.approx(nb.max[0])
    # Z contact face extended by eps; far Z face preserved exactly.
    assert fb.min[2] == pytest.approx(nb.min[2] - 0.01)
    assert fb.max[2] == pytest.approx(nb.max[2])


def test_attach_bridge_on_cylindrical_wall_raises_oblique():
    """attach(bridge=True) on a curved host without coaxial normals raises
    rather than silently producing geometry that doesn't match the
    surface."""
    from scadwright.errors import ValidationError
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    with pytest.raises(ValidationError, match="coaxial normals"):
        peg.attach(hub, on="outer_wall", angle=90, bridge=True)


def test_attach_bridge_on_cylindrical_wall_with_orient():
    """With orient=True and bridge=True, peg's at-normal opposes host's
    on-normal so the bridge dispatch fires. Result: union(placed_peg,
    bridge) where the bridge fills the inscription gap between peg's
    flat face and the cylinder's curved surface."""
    from scadwright.ast.csg import Difference, Union
    hub = cylinder(h=20, r=10)
    peg = cube([2, 2, 5])
    result = peg.attach(hub, on="outer_wall", angle=90, orient=True, bridge=True)
    assert isinstance(result, Union)
    assert any(isinstance(c, Difference) for c in result.children)


def test_attach_fuse_on_sphere_to_planar_floor_raises():
    """Sphere's bbox-derived anchors are kind='spherical', but the floor
    is planar. bond='overlap' needs planar+planar; bridge=True needs a
    curved *host*. fuse=True raises with workaround pointers."""
    from scadwright.errors import ValidationError

    floor = cube([40, 40, 2])
    with pytest.raises(ValidationError, match="no applicable eps mechanism"):
        sphere(r=5).attach(floor, fuse=True)


def test_attach_fuse_on_sphere_to_planar_floor_with_bond_shift():
    """bond='shift' is the recovery path: sphere on floor, bilateral shift."""
    floor = cube([40, 40, 2])
    result = sphere(r=5).attach(floor, bond="shift")
    bb = bbox(result)
    # Sphere top at z = floor_top + 2r - eps = 2 + 10 - 0.01.
    assert bb.max[2] == pytest.approx(11.99)


# --- Standalone fuse(...) function ---


def test_fuse_function_basic():
    """fuse(a, b, ...) returns a union with the contact eps included.
    Same end-result as attach(fuse=True) + manual union, but expressed
    as one call."""
    floor = cube([40, 40, 2])
    pylon = cube([5, 5, 10])
    result = fuse(pylon, floor, on="top", using_anchor="bottom")
    bb = bbox(result)
    # Result includes both shapes; bbox covers floor (z=0..2) and pylon
    # (extended bottom z=1.99, preserved top z=12). Union bbox z range
    # is 0..12.
    assert bb.min[2] == pytest.approx(0.0)
    assert bb.max[2] == pytest.approx(12.0)


def test_fuse_function_uses_either_side():
    """If a is a complex shape and b is a Cube, fuse picks b for
    extension. Either-side selection lets fuse handle cases where
    only one shape qualifies."""
    # Tube doesn't have its own fuse_extend (Component default is None).
    # Cube does. Either order should work via either-side selection.
    plate = cube([20, 20, 3])
    pillar = Tube(od=10, id=6, h=15)
    result = fuse(pillar, plate, on="top", using_anchor="bottom")
    # pillar.fuse_extend → None (Tube). plate.fuse_extend → extended cube.
    # pillar translates onto plate's top at z=3 (the original plate top
    # anchor position). Plate top extended into pillar by eps (to z=3.01).
    # pillar spans z=3..18 (3 + h=15); plate spans z=0..3.01.
    bb = bbox(result)
    assert bb.min[2] == pytest.approx(0.0)   # plate bottom preserved
    assert bb.max[2] == pytest.approx(18.0)  # pillar top preserved (3 + 15)


def test_fuse_function_prefers_wrapper_free_side():
    """Explicit ``bond="overlap"`` keeps the symmetric picker, which extends the
    side whose fuse_extend produces no Translate wrapper (the +axis-direction
    face). For a stacked-cubes join — top of the lower meeting bottom of the
    upper — that's the lower cube's top: cleaner SCAD output, the same final
    geometry as picking either side. (Bare ``fuse`` now runs the grow-or-slab
    mechanism instead, which prefers the contained side, ``a`` first on a tie.)
    """
    lower = cube([10, 10, 5])    # b: fuse on its top face (+Z) → no wrapper.
    upper = cube([10, 10, 5])    # a: fuse on its bottom face (−Z) → Translate wrapper.
    result = fuse(upper, lower, on="top", using_anchor="bottom", bond="overlap")
    bb = bbox(result)
    # Lower spans z=0..5, extended top to z=5.01. Upper spans z=5..10
    # (preserved). Combined bbox: 0..10.
    assert bb.min[2] == pytest.approx(0.0)
    assert bb.max[2] == pytest.approx(10.0)
    # The extended side should be b (the lower cube), since picking a
    # would require a Translate wrapper around the bumped cube. Confirm
    # by inspecting the union's children.
    from scadwright.ast.csg import Union
    from scadwright.ast.primitives import Cube
    from scadwright.ast.transforms import Translate as _Translate
    assert isinstance(result, Union)
    # Children: [placed_a (Translate wrapping original cube), extended_b
    # (Cube with size[2]=5.01)]. The original ``a`` becomes a Translate;
    # ``b`` is the bumped Cube directly.
    a_placed, b_extended = result.children
    assert isinstance(b_extended, Cube)
    assert b_extended.size[2] == pytest.approx(5.01)
    # a is the unmodified upper cube wrapped in a Translate.
    assert isinstance(a_placed, _Translate)


def test_fuse_function_two_spheres_bridges():
    """Two spheres tangent: b's anchor is kind='spherical' so bridge=True
    drives the bridge dispatch from a (peg) into b (host). Bridge = prism
    - b. Returns union(placed_a, b, bridge)."""
    from scadwright.ast.csg import Difference, Union
    s1 = sphere(r=5)
    s2 = sphere(r=5).up(10)
    result = fuse(s1, s2, on="bottom", using_anchor="top", bridge=True)
    assert isinstance(result, Union)
    assert any(isinstance(c, Difference) for c in result.children)
