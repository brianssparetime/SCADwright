"""Edge-fillet sugar for ``Cube`` and ``Cylinder`` primitives.

Sugar over ``FilletMask`` for the case where edge identity is well-
defined: the 12 canonical edges of an axis-aligned cube and the two
rim edges of a non-cone cylinder. Replaces the manual pattern of

    mask = FilletMask(r=2, length=20, axis="y")
    part = difference(box, mask.translate([10, 0, 0]))

with a one-line method call::

    part = box.fillet("top_lside", r=2)

Out of scope (raise or absent by design):

- Edges of composed shapes (Union/Difference/Intersection results).
  Edge identity is lost in CSG; recovering it needs CGAL-level topology.
  Users keep using ``FilletMask`` manually.
- Non-axis-aligned primitives (``cube(...).rotate(...)``). Method lives
  on the primitive AST class only; rotated primitives don't have it
  (``Rotate`` doesn't define ``.fillet``), so calls produce a clear
  ``AttributeError`` from Python with the user's call site in the
  traceback.
- Cones (``cylinder(r1=A, r2=B)``). Slanted-wall rim geometry is more
  complex than this scope warrants; raise with a hint.
- Component-declared edges. Could be a follow-on; not in this scope.
- Inside-corner fillets (union with FilletMask). Subtract-only.
"""

from __future__ import annotations

import math

from scadwright.errors import ValidationError


# Edge metadata: name -> (direction_axis, into_cube_signs).
#
# direction_axis: "x", "y", or "z" — the axis along which the edge runs.
#
# into_cube_signs: 3-tuple. Component for the direction axis is 0; the other
#   two are +1 if the cube's interior lies in the +direction of that axis
#   from the edge corner, -1 if it lies in the -direction.
#
# Face name conventions match the framework's anchor system: top=+Z,
# bottom=-Z, front=-Y, back=+Y, lside=-X, rside=+X.
_CUBE_EDGES: dict[str, tuple[str, tuple[int, int, int]]] = {
    # Edges along x
    "top_front":    ("x", (0, +1, -1)),
    "top_back":     ("x", (0, -1, -1)),
    "bottom_front": ("x", (0, +1, +1)),
    "bottom_back":  ("x", (0, -1, +1)),
    # Edges along y
    "top_lside":    ("y", (+1, 0, -1)),
    "top_rside":    ("y", (-1, 0, -1)),
    "bottom_lside": ("y", (+1, 0, +1)),
    "bottom_rside": ("y", (-1, 0, +1)),
    # Edges along z
    "front_lside":  ("z", (+1, +1, 0)),
    "front_rside":  ("z", (-1, +1, 0)),
    "back_lside":   ("z", (+1, -1, 0)),
    "back_rside":   ("z", (-1, -1, 0)),
}


_CUBE_GROUPS: dict[str, list[str]] = {
    "top": ["top_front", "top_back", "top_lside", "top_rside"],
    "bottom": ["bottom_front", "bottom_back", "bottom_lside", "bottom_rside"],
    "vertical": ["front_lside", "front_rside", "back_lside", "back_rside"],
}


_CYLINDER_RIMS = {"top_rim", "bottom_rim"}


def _resolve_cube_edges(edges) -> list[str]:
    """Resolve a string or list of strings/groups to a flat list of edge names.

    Accepts a single name, a group selector (``"top"``/``"bottom"``/
    ``"vertical"``), or a list mixing the two. Deduplicates while
    preserving the user's order.
    """
    if isinstance(edges, str):
        edges = [edges]
    elif not isinstance(edges, (list, tuple)):
        raise ValidationError(
            f"fillet/chamfer: edges must be a string or list of strings, "
            f"got {type(edges).__name__}"
        )
    result: list[str] = []
    seen: set[str] = set()
    for entry in edges:
        if not isinstance(entry, str):
            raise ValidationError(
                f"fillet/chamfer: every entry must be a string, "
                f"got {type(entry).__name__} in {edges!r}"
            )
        if entry in _CUBE_GROUPS:
            for name in _CUBE_GROUPS[entry]:
                if name not in seen:
                    result.append(name)
                    seen.add(name)
        elif entry in _CUBE_EDGES:
            if entry not in seen:
                result.append(entry)
                seen.add(entry)
        else:
            valid_edges = sorted(_CUBE_EDGES.keys())
            valid_groups = sorted(_CUBE_GROUPS.keys())
            raise ValidationError(
                f"fillet/chamfer: unknown edge name {entry!r}. "
                f"Valid edge names: {', '.join(valid_edges)}. "
                f"Valid group selectors: {', '.join(valid_groups)}."
            )
    return result


def _cube_extents(cube_node):
    """Return ``((min_x, min_y, min_z), (max_x, max_y, max_z))`` for a Cube
    node, accounting for its per-axis ``center`` flags.
    """
    sx, sy, sz = cube_node.size
    cx, cy, cz = cube_node.center
    min_x = -sx / 2.0 if cx else 0.0
    max_x = sx / 2.0 if cx else float(sx)
    min_y = -sy / 2.0 if cy else 0.0
    max_y = sy / 2.0 if cy else float(sy)
    min_z = -sz / 2.0 if cz else 0.0
    max_z = sz / 2.0 if cz else float(sz)
    return ((min_x, min_y, min_z), (max_x, max_y, max_z))


def _validate_cube_radius(cube_node, edge_name: str, r: float) -> None:
    """Verify that the fillet/chamfer ``r`` doesn't exceed half of either
    perpendicular dimension of the cube.
    """
    direction, _signs = _CUBE_EDGES[edge_name]
    sx, sy, sz = cube_node.size
    perps = [s for s, ax in zip((sx, sy, sz), ("x", "y", "z")) if ax != direction]
    smallest_perp = min(perps)
    if r > smallest_perp / 2.0 + 1e-9:
        raise ValidationError(
            f"fillet/chamfer: r={r} exceeds half of the smallest perpendicular "
            f"cube dimension ({smallest_perp / 2.0}) for edge {edge_name!r}. "
            f"Use a smaller radius or a larger cube."
        )


def _build_cube_edge_mask(cube_node, edge_name: str, mask_factory, size_kw: str, size_value: float):
    """Build a positioned mask for one cube edge.

    Strategy: instantiate the mask in its native orientation (sharp edge
    at the local origin's corner along the chosen axis, body extending
    in the +ve perpendicular directions), apply mirror(s) for any
    perpendicular axis where the cube's interior is in the -ve
    direction, then translate to the cube's edge corner.
    """
    direction, signs = _CUBE_EDGES[edge_name]
    extents_min, extents_max = _cube_extents(cube_node)
    dir_idx = {"x": 0, "y": 1, "z": 2}[direction]

    length = extents_max[dir_idx] - extents_min[dir_idx]

    mask = mask_factory(length=length, axis=direction, **{size_kw: size_value})

    translate = [0.0, 0.0, 0.0]
    for i in range(3):
        if i == dir_idx:
            translate[i] = extents_min[i]
            continue
        sign = signs[i]
        if sign == +1:
            translate[i] = extents_min[i]
        else:  # sign == -1
            normal = [0, 0, 0]
            normal[i] = 1
            mask = mask.mirror(tuple(normal))
            translate[i] = extents_max[i]

    return mask.translate(tuple(translate))


def cube_fillet(cube_node, edges, *, r: float):
    """Implementation of ``Cube.fillet(edges, r=...)``.

    Resolves the edge selector, builds a FilletMask for each edge,
    positions it via mirror+translate, and subtracts the union of all
    masks from the cube. ``through()`` is applied to each mask so the
    cuts clear the cube faces.
    """
    from scadwright.boolops import difference
    from scadwright.shapes.fillets.masks import FilletMask

    if r <= 0:
        raise ValidationError(f"fillet: r must be positive, got {r}")

    edge_names = _resolve_cube_edges(edges)
    if not edge_names:
        return cube_node

    masks = []
    for name in edge_names:
        _validate_cube_radius(cube_node, name, r)
        m = _build_cube_edge_mask(cube_node, name, FilletMask, "r", r)
        masks.append(m.through(cube_node))

    return difference(cube_node, *masks)


def cube_chamfer(cube_node, edges, *, size: float):
    """Implementation of ``Cube.chamfer(edges, size=...)``.

    Same as ``cube_fillet`` but uses ``ChamferMask`` (45° bevel)
    instead of ``FilletMask`` (rounded).
    """
    from scadwright.boolops import difference
    from scadwright.shapes.fillets.masks import ChamferMask

    if size <= 0:
        raise ValidationError(f"chamfer: size must be positive, got {size}")

    edge_names = _resolve_cube_edges(edges)
    if not edge_names:
        return cube_node

    masks = []
    for name in edge_names:
        _validate_cube_radius(cube_node, name, size)
        m = _build_cube_edge_mask(cube_node, name, ChamferMask, "size", size)
        masks.append(m.through(cube_node))

    return difference(cube_node, *masks)


# --- cylinder rim fillet/chamfer ---


def _cylinder_extents(cyl_node) -> tuple[float, float, float]:
    """Return ``(r, z_min, z_max)`` for a non-cone Cylinder. Raises on cone."""
    if cyl_node.r1 != cyl_node.r2:
        raise ValidationError(
            f"fillet/chamfer: cone cylinders (r1={cyl_node.r1} != r2={cyl_node.r2}) "
            f"are not supported. Slanted-wall rim geometry is out of scope; use "
            f"a custom rotate_extrude profile instead."
        )
    R = cyl_node.r1
    H = cyl_node.h
    if cyl_node.center:
        return R, -H / 2.0, H / 2.0
    return R, 0.0, H


def _validate_cylinder_radius(cyl_node, r: float) -> None:
    """Rim fillet/chamfer must fit inside both the radius and half the height."""
    R = cyl_node.r1  # known equal to r2 by _cylinder_extents check
    H = cyl_node.h
    if r > R + 1e-9 or r > H / 2.0 + 1e-9:
        raise ValidationError(
            f"fillet/chamfer: r={r} exceeds the cylinder's radius ({R}) "
            f"or half its height ({H/2.0}). Use a smaller radius."
        )


def _cylinder_fillet_profile(R: float, z_corner: float, z_bite: float, rho: float, segments: int = 16):
    """Build the rotate_extrude profile that, after subtraction, produces
    a quarter-circle fillet at the cylinder's top or bottom rim.

    The profile is an L-shape in the (r, z) plane: the rectangular
    corner of size ``rho`` at (``R``, ``z_corner``) with a
    quarter-circle bite taken out of the interior corner at
    (``R - rho``, ``z_bite``). After ``rotate_extrude`` around z, the
    revolved shape is a torus-quadrant ring whose subtraction from
    the cylinder rounds the rim.
    """
    from scadwright.primitives import polygon

    # Decide arc direction: top rim arcs from +r to +z; bottom from +r to -z.
    top = z_bite < z_corner  # top: the bite is below the corner
    cx, cz = R - rho, z_bite
    points: list[tuple[float, float]] = [(R, z_corner)]
    points.append((R, z_bite))
    if top:
        start_angle, end_angle = 0.0, math.pi / 2.0
    else:
        start_angle, end_angle = 0.0, -math.pi / 2.0
    for i in range(1, segments):
        t = i / segments
        angle = start_angle + t * (end_angle - start_angle)
        points.append((cx + rho * math.cos(angle), cz + rho * math.sin(angle)))
    points.append((R - rho, z_corner))
    return polygon(points=points)


def _cylinder_chamfer_profile(R: float, z_corner: float, z_bite: float, size: float):
    """Triangular profile for a 45° rim chamfer. Three points: outer corner,
    outer wall ending, top inner edge.
    """
    from scadwright.primitives import polygon
    return polygon(points=[
        (R, z_corner),
        (R, z_bite),
        (R - size, z_corner),
    ])


def cylinder_fillet(cyl_node, rim: str, *, r: float):
    """Implementation of ``Cylinder.fillet(rim, r=...)``."""
    from scadwright.boolops import difference
    from scadwright.extrusions import rotate_extrude

    if r <= 0:
        raise ValidationError(f"fillet: r must be positive, got {r}")
    if rim not in _CYLINDER_RIMS:
        raise ValidationError(
            f"Cylinder.fillet: rim must be 'top_rim' or 'bottom_rim', got {rim!r}"
        )
    R, z_min, z_max = _cylinder_extents(cyl_node)
    _validate_cylinder_radius(cyl_node, r)

    if rim == "top_rim":
        profile = _cylinder_fillet_profile(R, z_max, z_max - r, r)
    else:  # bottom_rim
        profile = _cylinder_fillet_profile(R, z_min, z_min + r, r)

    cutter = rotate_extrude(profile)
    return difference(cyl_node, cutter)


def cylinder_chamfer(cyl_node, rim: str, *, size: float):
    """Implementation of ``Cylinder.chamfer(rim, size=...)``."""
    from scadwright.boolops import difference
    from scadwright.extrusions import rotate_extrude

    if size <= 0:
        raise ValidationError(f"chamfer: size must be positive, got {size}")
    if rim not in _CYLINDER_RIMS:
        raise ValidationError(
            f"Cylinder.chamfer: rim must be 'top_rim' or 'bottom_rim', got {rim!r}"
        )
    R, z_min, z_max = _cylinder_extents(cyl_node)
    _validate_cylinder_radius(cyl_node, size)

    if rim == "top_rim":
        profile = _cylinder_chamfer_profile(R, z_max, z_max - size, size)
    else:
        profile = _cylinder_chamfer_profile(R, z_min, z_min + size, size)

    cutter = rotate_extrude(profile)
    return difference(cyl_node, cutter)
